#!/usr/bin/env python3
"""PreToolUse hook: surface drift on doc access; auto-fire on Certain.

Reads stdin JSON from Claude Code (PreToolUse event for Read|Edit|Write|
MultiEdit), looks up the target file in .interwatch/drift.json, and emits
hook output:

- Green/Low: silent (no output, exit 0).
- Medium/High: one-line advisory in additionalContext.
- Certain (with cooldown + budget guards passing): advisory + an instruction
  to dispatch /interwatch:refresh <name> via additionalContext, and append a
  fired event to .interwatch/auto-refresh.log.

Goodhart guardrails (per sylveste-wdf2.2):
- Cooldown: do not auto-fire if a fired event for this watchable exists in
  the last 24h (configurable).
- Budget: do not auto-fire if the daily-fired count meets the cap (default 5,
  configurable in .interwatch/project.yaml).
- Master kill-switch: auto_refresh.enabled = false disables auto-fire entirely
  (advisory still emitted).
- High confidence never auto-fires; only Certain does.
- Generator must be present (non-null) for auto-fire — otherwise advisory only.
- No-op refreshes are detected in --record-refresh (interwatch-scan.py) and do
  not consume budget; they are logged with outcome=no-op.

Failure mode: fail-open. Any error reading drift.json, parsing input, or
locating the project root → silently exit 0 (no decision, no context).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_DIR = ".interwatch"
DRIFT_FILE = "drift.json"
LOG_FILE = "auto-refresh.log"
PROJECT_CONFIG = "project.yaml"

DEFAULT_DAILY_CAP = 5
DEFAULT_COOLDOWN_HOURS = 24

ADVISORY_TIERS = {"Medium", "High", "Certain"}
AUTOFIRE_TIERS = {"Certain"}


def _emit(payload: dict) -> None:
    """Write hook output JSON to stdout and exit 0."""
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
    sys.exit(0)


def _silent() -> None:
    """Emit no hook output."""
    sys.exit(0)


def _read_input() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        _silent()


def _resolve_project_root() -> Path | None:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".git").exists() or (parent / STATE_DIR / DRIFT_FILE).exists():
            return parent
    return None


def _load_drift(root: Path) -> dict:
    path = root / STATE_DIR / DRIFT_FILE
    try:
        with path.open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _load_project_config(root: Path) -> dict:
    """Load .interwatch/project.yaml. Returns empty dict on miss/error.

    Schema:
      auto_refresh:
        enabled: true              # master kill-switch (default true)
        daily_cap: 5                # max auto-fires per UTC day
        cooldown_hours: 24          # hours between auto-fires per watchable
        watchables:                 # optional per-watchable overrides
          claude-md:
            enabled: false          # opt out of auto-fire
    """
    cfg_path = root / STATE_DIR / PROJECT_CONFIG
    if not cfg_path.exists():
        return {}
    try:
        import yaml
        with cfg_path.open() as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except (OSError, ImportError, Exception):
        return {}


def _autofire_settings(cfg: dict, name: str) -> dict:
    """Resolve effective auto-fire settings for a watchable name."""
    section = cfg.get("auto_refresh", {}) if isinstance(cfg, dict) else {}
    if not isinstance(section, dict):
        section = {}

    enabled = section.get("enabled", True)
    daily_cap = section.get("daily_cap", DEFAULT_DAILY_CAP)
    cooldown_hours = section.get("cooldown_hours", DEFAULT_COOLDOWN_HOURS)

    per_watchable = section.get("watchables", {})
    if isinstance(per_watchable, dict):
        override = per_watchable.get(name, {})
        if isinstance(override, dict):
            enabled = override.get("enabled", enabled)
            daily_cap = override.get("daily_cap", daily_cap)
            cooldown_hours = override.get("cooldown_hours", cooldown_hours)

    try:
        daily_cap = int(daily_cap)
    except (TypeError, ValueError):
        daily_cap = DEFAULT_DAILY_CAP
    try:
        cooldown_hours = float(cooldown_hours)
    except (TypeError, ValueError):
        cooldown_hours = DEFAULT_COOLDOWN_HOURS

    return {
        "enabled": bool(enabled),
        "daily_cap": daily_cap,
        "cooldown_hours": cooldown_hours,
    }


def _extract_file_path(payload: dict) -> str | None:
    """Pull file_path out of tool_input regardless of which Read/Edit/Write/MultiEdit fired."""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return None
    fp = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path")
    if not isinstance(fp, str) or not fp:
        return None
    return fp


def _match_watchable(rel_path: str, drift: dict) -> tuple[str, dict] | None:
    """Find the watchable whose path covers rel_path.

    Match rules:
    - Exact path match wins first.
    - Directory watchables (path ends in '/' OR points at a real dir): match
      if rel_path startswith the directory prefix.
    """
    watchables = drift.get("watchables", {})
    if not isinstance(watchables, dict):
        return None

    rel_norm = rel_path.replace("\\", "/").lstrip("./")

    for name, w in watchables.items():
        if not isinstance(w, dict):
            continue
        wpath = (w.get("path") or "").replace("\\", "/").lstrip("./")
        if not wpath:
            continue
        if wpath == rel_norm:
            return name, w

    for name, w in watchables.items():
        if not isinstance(w, dict):
            continue
        wpath = (w.get("path") or "").replace("\\", "/").lstrip("./")
        if not wpath:
            continue
        is_dir_pattern = wpath.endswith("/")
        if is_dir_pattern and rel_norm.startswith(wpath):
            return name, w

    return None


def _load_log(root: Path) -> list[dict]:
    """Read auto-refresh.log (JSONL). Returns list of entries, oldest first."""
    log_path = root / STATE_DIR / LOG_FILE
    if not log_path.exists():
        return []
    entries: list[dict] = []
    try:
        with log_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return entries


def _append_log(root: Path, entry: dict) -> None:
    """Append one JSONL entry to auto-refresh.log. Best-effort."""
    log_path = root / STATE_DIR / LOG_FILE
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _last_fired(entries: list[dict], name: str) -> datetime | None:
    """Most recent 'fired' timestamp for this watchable, or None."""
    for entry in reversed(entries):
        if entry.get("name") != name or entry.get("outcome") != "fired":
            continue
        ts = entry.get("ts")
        if not isinstance(ts, str):
            continue
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            continue
    return None


def _fired_today(entries: list[dict]) -> int:
    """Count of 'fired' events with UTC date == today."""
    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    count = 0
    for entry in entries:
        if entry.get("outcome") != "fired":
            continue
        ts = entry.get("ts")
        if not isinstance(ts, str):
            continue
        try:
            if datetime.fromisoformat(ts).date() == today:
                count += 1
        except ValueError:
            continue
    return count


def decide(
    payload: dict,
    drift: dict,
    cfg: dict,
    log_entries: list[dict],
    now: datetime | None = None,
) -> tuple[dict | None, dict | None]:
    """Pure decision function: returns (hook_output, log_entry).

    Either or both may be None. Tested directly by the test harness.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)

    file_path = _extract_file_path(payload)
    if not file_path:
        return None, None

    rel = file_path
    cwd = str(Path.cwd())
    if rel.startswith(cwd + "/"):
        rel = rel[len(cwd) + 1:]
    rel = rel.lstrip("./")

    match = _match_watchable(rel, drift)
    if match is None:
        return None, None

    name, watchable = match
    confidence = watchable.get("confidence")
    if confidence not in ADVISORY_TIERS:
        return None, None

    score = watchable.get("score", 0)
    generator = watchable.get("generator")
    tool_name = payload.get("tool_name", "?")

    advisory = (
        f"INTERWATCH: '{name}' ({watchable.get('path')}) is at {confidence} drift "
        f"(score={score}). Run /interwatch:refresh {name} when ready."
    )

    log_entry: dict | None = None

    if confidence in AUTOFIRE_TIERS:
        settings = _autofire_settings(cfg, name)

        if not settings["enabled"]:
            log_entry = {
                "ts": now.isoformat(timespec="seconds"),
                "name": name,
                "tool": tool_name,
                "outcome": "disabled",
            }
        elif not generator:
            log_entry = {
                "ts": now.isoformat(timespec="seconds"),
                "name": name,
                "tool": tool_name,
                "outcome": "no_generator",
            }
        else:
            last = _last_fired(log_entries, name)
            cooldown = timedelta(hours=settings["cooldown_hours"])
            if last is not None and (now - last) < cooldown:
                log_entry = {
                    "ts": now.isoformat(timespec="seconds"),
                    "name": name,
                    "tool": tool_name,
                    "outcome": "cooldown",
                    "last_fired": last.isoformat(timespec="seconds"),
                }
            elif _fired_today(log_entries) >= settings["daily_cap"]:
                log_entry = {
                    "ts": now.isoformat(timespec="seconds"),
                    "name": name,
                    "tool": tool_name,
                    "outcome": "budget",
                    "daily_cap": settings["daily_cap"],
                }
            else:
                advisory = (
                    f"INTERWATCH AUTO-FIRE: '{name}' ({watchable.get('path')}) is at "
                    f"Certain drift (score={score}, generator={generator}). "
                    f"Run /interwatch:refresh {name} now before continuing — this doc "
                    f"is provably out of sync with the codebase."
                )
                log_entry = {
                    "ts": now.isoformat(timespec="seconds"),
                    "name": name,
                    "tool": tool_name,
                    "outcome": "fired",
                    "generator": generator,
                }

    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": advisory}}, log_entry


def main() -> None:
    payload = _read_input()
    root = _resolve_project_root()
    if root is None:
        _silent()

    os.chdir(root)
    drift = _load_drift(root)
    if not drift.get("watchables"):
        _silent()

    cfg = _load_project_config(root)
    log_entries = _load_log(root)

    output, log_entry = decide(payload, drift, cfg, log_entries)

    if log_entry is not None:
        _append_log(root, log_entry)

    if output is None:
        _silent()

    _emit(output)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
