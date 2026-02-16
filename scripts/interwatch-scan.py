#!/usr/bin/env python3
"""Pre-compute drift signals for interwatch doc-watch skill.

Reads watchables.yaml, evaluates signals using shell commands,
and outputs JSON with drift scores and confidence tiers.

Usage:
    python3 interwatch-scan.py                          # Use config/watchables.yaml
    python3 interwatch-scan.py --config path/to/w.yaml  # Custom config
    python3 interwatch-scan.py --check docs/roadmap.md  # Check single doc
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def run_cmd(cmd: list[str], cwd: str | None = None) -> str:
    """Run a command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=cwd)
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def get_doc_mtime(path: str) -> float:
    """Get file modification time as epoch seconds, or 0 if missing."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def get_doc_date(mtime: float) -> str:
    """Convert epoch to YYYY-MM-DD."""
    if mtime == 0:
        return "1970-01-01"
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


# ─── Signal evaluators ──────────────────────────────────────────────


def eval_bead_closed(doc_path: str, mtime: float) -> int:
    """Count beads closed since doc was last modified."""
    doc_date = get_doc_date(mtime)
    output = run_cmd(["bd", "list", "--status=closed"])
    if not output:
        return 0
    # Count lines with closed beads — rough proxy for "closed since doc_date"
    # bd doesn't support date filtering, so we count all closed beads
    # and compare against a snapshot (if available)
    lines = [l for l in output.splitlines() if l.startswith("✓")]
    return min(len(lines), 10)  # Cap at 10 to avoid score explosion


def eval_bead_created(doc_path: str, mtime: float) -> int:
    """Count open beads (proxy for new beads since doc update)."""
    output = run_cmd(["bd", "list", "--status=open"])
    if not output:
        return 0
    lines = [l for l in output.splitlines() if l.strip() and not l.startswith("⚠")]
    return min(len(lines), 10)  # Cap at 10 to match bead_closed


def eval_version_bump(doc_path: str, mtime: float) -> int:
    """Check if plugin.json version differs from doc header."""
    # Read plugin version
    for manifest in [".claude-plugin/plugin.json", "plugin.json"]:
        if os.path.exists(manifest):
            try:
                with open(manifest) as f:
                    plugin_version = json.load(f).get("version", "")
                break
            except (json.JSONDecodeError, OSError):
                plugin_version = ""
    else:
        return 0

    # Read doc version (look for "Version: X.Y.Z" in first 10 lines)
    try:
        with open(doc_path) as f:
            for i, line in enumerate(f):
                if i >= 10:
                    break
                if "version:" in line.lower():
                    # Extract version number
                    import re
                    match = re.search(r"[\d]+\.[\d]+\.[\d]+", line)
                    if match and match.group() != plugin_version:
                        return 1
                    elif match:
                        return 0
    except OSError:
        pass
    return 0


def eval_component_count_changed(doc_path: str, mtime: float) -> int:
    """Check if actual component counts differ from doc claims."""
    changes = 0
    actual = {}

    # Count actual components
    for kind, pattern in [
        ("skills", "skills/*/SKILL.md"),
        ("commands", "commands/*.md"),
        ("agents", "agents/*/*.md"),
    ]:
        from glob import glob
        actual[kind] = len(glob(pattern))

    # Read doc and look for count claims
    try:
        with open(doc_path) as f:
            content = f.read()
    except OSError:
        return 0

    import re
    for kind, count in actual.items():
        # Match patterns like "41 commands" or "23 skills"
        pattern = rf"(\d+)\s+{kind}"
        for match in re.finditer(pattern, content):
            claimed = int(match.group(1))
            if claimed != count:
                changes += 1
                break

    return min(changes, 3)  # Cap at 3


def eval_file_changed(doc_path: str, mtime: float, change_type: str) -> int:
    """Count file renames/deletes/creates since doc was modified."""
    if mtime == 0:
        return 0
    doc_commit = run_cmd([
        "git", "log", "-1", "--format=%H",
        f"--until=@{int(mtime)}"
    ])
    if not doc_commit:
        return 0

    status_map = {"file_renamed": "R", "file_deleted": "D", "file_created": "A"}
    prefix = status_map.get(change_type, "")

    output = run_cmd([
        "git", "diff", "--name-status",
        f"{doc_commit}..HEAD", "--",
        "skills/", "commands/", "agents/", "hooks/"
    ])
    if not output:
        return 0

    count = sum(1 for line in output.splitlines() if line.startswith(prefix))
    return min(count, 5)


def eval_commits_since_update(doc_path: str, mtime: float, threshold: int = 20) -> int:
    """Count commits since doc was modified."""
    if mtime == 0:
        return 0
    output = run_cmd([
        "git", "rev-list", "--count", "HEAD",
        f"--since=@{int(mtime)}"
    ])
    try:
        count = int(output)
        return 1 if count >= threshold else 0
    except (ValueError, TypeError):
        return 0


def eval_brainstorm_created(doc_path: str, mtime: float) -> int:
    """Count brainstorms newer than doc."""
    if mtime == 0:
        return 0
    count = 0
    brainstorm_dir = Path("docs/brainstorms")
    if brainstorm_dir.exists():
        for f in brainstorm_dir.glob("*.md"):
            if f.stat().st_mtime > mtime:
                count += 1
    return min(count, 5)


def eval_companion_extracted(doc_path: str, mtime: float) -> int:
    """Check for companion plugins not mentioned in doc."""
    companions = [
        "interphase", "interline", "interflux", "interwatch", "interdoc",
        "interpath", "interlock", "interslack", "interform", "intercraft",
        "interdev", "intercheck", "interject", "internext", "interpub",
        "intersearch", "tldr-swinton", "tool-time", "tuivision",
    ]
    try:
        with open(doc_path) as f:
            content = f.read().lower()
    except OSError:
        return 0

    missing = sum(1 for c in companions if c not in content)
    return min(missing, 5)


def eval_research_completed(doc_path: str, mtime: float) -> int:
    """Count research docs newer than doc."""
    if mtime == 0:
        return 0
    count = 0
    research_dir = Path("docs/research")
    if research_dir.exists():
        for f in research_dir.glob("*.md"):
            if f.stat().st_mtime > mtime:
                count += 1
    return min(count, 3)


# ─── Signal dispatch ─────────────────────────────────────────────────

SIGNAL_EVALUATORS = {
    "bead_closed": eval_bead_closed,
    "bead_created": eval_bead_created,
    "version_bump": eval_version_bump,
    "component_count_changed": eval_component_count_changed,
    "file_renamed": lambda p, m: eval_file_changed(p, m, "file_renamed"),
    "file_deleted": lambda p, m: eval_file_changed(p, m, "file_deleted"),
    "file_created": lambda p, m: eval_file_changed(p, m, "file_created"),
    "commits_since_update": eval_commits_since_update,
    "brainstorm_created": eval_brainstorm_created,
    "companion_extracted": eval_companion_extracted,
    "research_completed": eval_research_completed,
}


# ─── Confidence tier mapping ─────────────────────────────────────────

def score_to_tier(score: int, has_deterministic: bool = False, stale: bool = False) -> str:
    """Map drift score to confidence tier (per confidence-tiers.md reference)."""
    if has_deterministic:
        return "Certain"
    if stale:
        return "High"
    if score == 0:
        return "Green"
    if score <= 2:
        return "Low"
    if score <= 5:
        return "Medium"
    return "High"


def tier_to_action(tier: str) -> str:
    """Map confidence tier to recommended action."""
    return {
        "Green": "none",
        "Low": "report-only",
        "Medium": "suggest-refresh",
        "High": "auto-refresh",
        "Certain": "auto-refresh-silent",
    }.get(tier, "none")


# ─── Main scan ────────────────────────────────────────────────────────

def scan_watchable(watchable: dict) -> dict:
    """Evaluate all signals for a single watchable."""
    name = watchable["name"]
    path = watchable["path"]
    staleness_days = watchable.get("staleness_days", 14)

    exists = os.path.exists(path)
    mtime = get_doc_mtime(path) if exists else 0

    # Check staleness
    stale = False
    if exists and staleness_days > 0:
        age_days = (time.time() - mtime) / 86400
        stale = age_days > staleness_days

    signals = {}
    total_score = 0
    has_deterministic = False

    for signal_def in watchable.get("signals", []):
        sig_type = signal_def["type"]
        weight = signal_def.get("weight", 1)

        evaluator = SIGNAL_EVALUATORS.get(sig_type)
        if evaluator is None:
            continue

        # Handle threshold parameter for commits_since_update
        if sig_type == "commits_since_update" and "threshold" in signal_def:
            count = eval_commits_since_update(path, mtime, signal_def["threshold"])
        else:
            count = evaluator(path, mtime)

        score = weight * count
        total_score += score

        # version_bump and component_count_changed are deterministic
        if sig_type in ("version_bump", "component_count_changed") and count > 0:
            has_deterministic = True

        signals[sig_type] = {
            "count": count,
            "weight": weight,
            "score": score,
        }

    tier = score_to_tier(total_score, has_deterministic, stale)
    action = tier_to_action(tier)

    return {
        "path": path,
        "exists": exists,
        "score": total_score,
        "confidence": tier,
        "stale": stale,
        "signals": signals,
        "recommended_action": action,
        "generator": watchable.get("generator", ""),
        "generator_args": watchable.get("generator_args", {}),
    }


def load_config(config_path: str | None = None) -> dict:
    """Load watchables config from YAML."""
    # Search order: explicit path, project .interwatch, plugin config
    candidates = []
    if config_path:
        candidates.append(config_path)
    candidates.extend([
        ".interwatch/watchables.yaml",
        "config/watchables.yaml",
    ])

    for path in candidates:
        if os.path.exists(path):
            with open(path) as f:
                return yaml.safe_load(f)

    print("Error: no watchables.yaml found", file=sys.stderr)
    sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="Pre-compute interwatch drift signals")
    parser.add_argument("--config", help="Path to watchables.yaml")
    parser.add_argument("--check", help="Check single doc path (filter output)")
    args = parser.parse_args()

    config = load_config(args.config)
    watchables = config.get("watchables", [])

    result = {
        "scan_date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "watchables": {},
    }

    for w in watchables:
        if args.check and w["path"] != args.check:
            continue
        result["watchables"][w["name"]] = scan_watchable(w)

    json.dump(result, sys.stdout, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
