#!/usr/bin/env python3
"""Pre-compute drift signals for interwatch doc-watch skill.

Reads watchables.yaml, evaluates signals using shell commands,
and outputs JSON with drift scores and confidence tiers.

Uses .interwatch/last-scan.json as a baseline for snapshot-delta
signals (bead_closed, bead_created) to avoid false positives after
a refresh. Run with --save-state to persist baselines after scanning.

Usage:
    python3 interwatch-scan.py                          # Use config/watchables.yaml
    python3 interwatch-scan.py --config path/to/w.yaml  # Custom config
    python3 interwatch-scan.py --check docs/roadmap.md  # Check single doc
    python3 interwatch-scan.py --save-state             # Persist baselines after scan
    python3 interwatch-scan.py --record-refresh roadmap # Reset baselines for a doc
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


STATE_DIR = ".interwatch"
LAST_SCAN_FILE = os.path.join(STATE_DIR, "last-scan.json")
DRIFT_FILE = os.path.join(STATE_DIR, "drift.json")


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


# ─── State management ─────────────────────────────────────────────


def load_last_scan() -> dict:
    """Load baseline state from last-scan.json, or empty dict if missing."""
    try:
        with open(LAST_SCAN_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_last_scan(state: dict) -> None:
    """Write baseline state to last-scan.json."""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LAST_SCAN_FILE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def save_drift(result: dict) -> None:
    """Write full scan results to drift.json."""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(DRIFT_FILE, "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")


def _count_bd_lines(status: str) -> int:
    """Count beads with a given status by counting output lines."""
    output = run_cmd(["bd", "list", f"--status={status}"])
    if not output:
        return 0
    if status == "closed":
        return len([l for l in output.splitlines() if l.startswith("\u2713")])
    # open: non-empty, non-warning lines
    return len([l for l in output.splitlines() if l.strip() and not l.startswith("\u26a0")])


# ─── Signal evaluators ──────────────────────────────────────────────


def eval_bead_closed(doc_path: str, mtime: float, baseline: dict | None = None) -> int:
    """Count beads closed since last scan baseline.

    Uses snapshot delta: current closed count minus baseline closed count.
    If no baseline exists, falls back to capped total (conservative).
    """
    current_count = _count_bd_lines("closed")
    if baseline is not None:
        baseline_count = baseline.get("bead_closed_count", 0)
        delta = max(0, current_count - baseline_count)
        return min(delta, 10)
    return min(current_count, 10)


def eval_bead_created(doc_path: str, mtime: float, baseline: dict | None = None) -> int:
    """Count new open beads since last scan baseline.

    Uses snapshot delta: current open count minus baseline open count.
    If no baseline exists, falls back to capped total (conservative).
    """
    current_count = _count_bd_lines("open")
    if baseline is not None:
        baseline_count = baseline.get("bead_created_count", 0)
        delta = max(0, current_count - baseline_count)
        return min(delta, 10)
    return min(current_count, 10)


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


def eval_routing_override_applied(doc_path: str, mtime: float) -> int:
    """Check if routing-overrides.json has active exclusions newer than doc.

    When agents are excluded via interspect routing overrides, docs that
    reference agent capabilities (AGENTS.md, PRD) may be stale.
    """
    if mtime == 0:
        return 0
    overrides_path = Path(".claude/routing-overrides.json")
    if not overrides_path.exists():
        return 0
    try:
        if overrides_path.stat().st_mtime <= mtime:
            return 0
        data = json.loads(overrides_path.read_text())
        if not isinstance(data, dict):
            return 0
        # Count agents with "exclude" or "propose" action
        agents = data.get("agents", data)
        if isinstance(agents, dict):
            return min(sum(1 for v in agents.values()
                          if isinstance(v, dict) and v.get("action") in ("exclude", "propose")), 5)
        return 0
    except (OSError, json.JSONDecodeError, ValueError):
        return 0


def eval_roadmap_bead_coverage(doc_path: str, mtime: float, threshold_min: int = 95) -> int:
    """Check roadmap-bead coverage via lib-watch.sh.

    Sources _watch_roadmap_bead_coverage from the bash library and parses
    the JSON result. Returns 1 if coverage_pct < threshold_min, else 0.
    Graceful fallback: returns 0 if script or bd not found.
    """
    lib_path = Path(__file__).resolve().parent.parent / "hooks" / "lib-watch.sh"
    if not lib_path.exists():
        return 0

    cmd = f'source "{lib_path}" && _watch_roadmap_bead_coverage "{doc_path}"'
    output = run_cmd(["bash", "-c", cmd])
    if not output:
        return 0

    try:
        result = json.loads(output)
        coverage = result.get("coverage_pct", 100)
        if result.get("error"):
            return 0
        return 1 if coverage < threshold_min else 0
    except (json.JSONDecodeError, TypeError):
        return 0


def eval_unsynthesized_doc_count(doc_path: str, mtime: float, threshold: int = 5) -> int:
    """Count solution docs older than 14 days without synthesized_into frontmatter.

    Walks docs/solutions/ recursively for .md files, skips INDEX.md and
    TEMPLATE.md, skips files newer than 14 days, parses YAML frontmatter
    for synthesized_into field. Returns 1 if count >= threshold, else 0.
    """
    solutions_dir = Path("docs/solutions")
    if not solutions_dir.exists():
        return 0

    cutoff = time.time() - (14 * 86400)
    count = 0

    for md in solutions_dir.rglob("*.md"):
        if md.name in ("INDEX.md", "TEMPLATE.md"):
            continue
        try:
            if md.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue

        # Parse YAML frontmatter
        try:
            content = md.read_text(errors="replace")
        except OSError:
            continue

        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                try:
                    fm = yaml.safe_load(content[3:end])
                    if isinstance(fm, dict) and fm.get("synthesized_into"):
                        continue
                except yaml.YAMLError:
                    pass

        count += 1

    return 1 if count >= threshold else 0


def eval_skills_without_compact(doc_path: str, mtime: float, threshold: int = 3) -> int:
    """Count SKILL.md files >90 lines lacking a sibling SKILL-compact.md.

    Walks skills/*/SKILL.md, counts those with more than 90 lines that
    don't have a corresponding SKILL-compact.md. Returns 1 if count >=
    threshold, else 0.
    """
    skills_dir = Path("skills")
    if not skills_dir.exists():
        return 0

    count = 0
    for skill_md in skills_dir.glob("*/SKILL.md"):
        compact = skill_md.parent / "SKILL-compact.md"
        if compact.exists():
            continue
        try:
            lines = len(skill_md.read_text(errors="replace").splitlines())
        except OSError:
            continue
        if lines > 90:
            count += 1

    return 1 if count >= threshold else 0


def eval_bead_reference_stale(doc_path: str, mtime: float) -> int:
    """Count stale bead references in doc text.

    Scans the document for iv-[a-z0-9]+ bead ID patterns, checks each
    against `bd show`, and counts references to closed/deferred/missing
    beads. Caches bd show results to avoid duplicate subprocess calls.
    """
    try:
        with open(doc_path) as f:
            content = f.read()
    except OSError:
        return 0

    import re
    bead_ids = set(re.findall(r'\biv-[a-z0-9]+\b', content))
    if not bead_ids:
        return 0

    stale_count = 0
    for bead_id in bead_ids:
        output = run_cmd(["bd", "show", bead_id])
        if not output:
            # bd show failed — bead doesn't exist
            stale_count += 1
            continue
        # Check for closed/deferred status in the output
        output_upper = output.upper()
        if "CLOSED" in output_upper or "DEFERRED" in output_upper:
            stale_count += 1

    return min(stale_count, 10)


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
    "roadmap_bead_coverage": eval_roadmap_bead_coverage,
    "unsynthesized_doc_count": eval_unsynthesized_doc_count,
    "skills_without_compact": eval_skills_without_compact,
    "routing_override_applied": eval_routing_override_applied,
    "bead_reference_stale": eval_bead_reference_stale,
}

# Signals that accept a baseline dict as third argument
BASELINE_SIGNALS = {"bead_closed", "bead_created"}

# Signals that accept a threshold parameter as third argument
THRESHOLD_SIGNALS = {
    "commits_since_update": {"param": "threshold", "default": 20},
    "roadmap_bead_coverage": {"param": "threshold_min", "default": 95},
    "unsynthesized_doc_count": {"param": "threshold", "default": 5},
    "skills_without_compact": {"param": "threshold", "default": 3},
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

def scan_watchable(watchable: dict, baseline: dict | None = None) -> dict:
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

        if sig_type in THRESHOLD_SIGNALS:
            tinfo = THRESHOLD_SIGNALS[sig_type]
            threshold_val = signal_def.get(tinfo["param"], tinfo["default"])
            count = evaluator(path, mtime, threshold_val)
        elif sig_type in BASELINE_SIGNALS:
            count = evaluator(path, mtime, baseline)
        else:
            count = evaluator(path, mtime)

        score = weight * count
        total_score += score

        # Deterministic signals — doc is provably wrong when these fire
        if sig_type in ("version_bump", "component_count_changed", "bead_reference_stale") and count > 0:
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


def load_plugin_config() -> dict:
    """Load the plugin's built-in config (template source for discovery).

    Always resolves from __file__ to find the plugin's config/watchables.yaml,
    never reads project overrides — this is the authoritative template source.
    """
    config_path = Path(__file__).resolve().parent.parent / "config" / "watchables.yaml"
    if not config_path.exists():
        print(f"Error: plugin config not found at {config_path}", file=sys.stderr)
        sys.exit(2)
    with open(config_path) as f:
        return yaml.safe_load(f)


# ─── Discovery ────────────────────────────────────────────────────────


def detect_module_name(project_root: str) -> str:
    """Detect the module name for a project.

    Tries .claude-plugin/plugin.json 'name' field first,
    then falls back to the directory basename.
    """
    for manifest in [
        os.path.join(project_root, ".claude-plugin", "plugin.json"),
        os.path.join(project_root, "plugin.json"),
    ]:
        if os.path.exists(manifest):
            try:
                with open(manifest) as f:
                    name = json.load(f).get("name", "")
                if name:
                    return name
            except (json.JSONDecodeError, OSError):
                pass
    return os.path.basename(os.path.abspath(project_root))


def detect_generators() -> dict[str, bool]:
    """Check which generators are available in the plugin cache."""
    cache_dir = Path.home() / ".claude" / "plugins" / "cache"
    available = {
        "interpath:artifact-gen": False,
        "interdoc:interdoc": False,
    }
    if not cache_dir.exists():
        return available

    for entry in cache_dir.iterdir():
        if not entry.is_dir():
            continue
        if (entry / "interpath").exists():
            available["interpath:artifact-gen"] = True
        if (entry / "interdoc").exists():
            available["interdoc:interdoc"] = True

    return available


def discover_watchables(config: dict, project_root: str) -> list[dict]:
    """Auto-discover watchable docs by matching discovery rules against the project.

    1. Load signal_templates and discovery_rules from config
    2. Resolve {module} in each rule's pattern
    3. Check os.path.exists() for each resolved pattern (or glob for wildcard patterns)
    4. Apply dedup: skip if skip_if_exists path exists
    5. Build watchable entry from matched template with discovered: True
    6. Check generator availability — if not installed, set generator to null

    Supports glob patterns (containing '*') in discovery rules. When a pattern
    contains '*' and the name_format uses '{stem}', each matched file gets its
    own watchable entry with {stem} resolved to the filename without extension.
    """
    from glob import glob as glob_match

    templates = config.get("signal_templates", {})
    rules = config.get("discovery_rules", [])
    if not templates or not rules:
        return []

    module_name = detect_module_name(project_root)
    generators = detect_generators()
    discovered = []

    for rule in rules:
        pattern = rule["pattern"].replace("{module}", module_name)
        template_name = rule.get("template", "")
        name_format = rule.get("name_format", "").replace("{module}", module_name)

        # Dedup: skip if a preferred variant exists
        skip_if = rule.get("skip_if_exists", "")
        if skip_if:
            skip_path = os.path.join(project_root, skip_if.replace("{module}", module_name))
            if os.path.exists(skip_path):
                continue

        template = templates.get(template_name)
        if template is None:
            continue

        generator = template.get("generator")
        generator_args = dict(template.get("generator_args", {}))
        generator_note = None

        if generator and not generators.get(generator, False):
            generator_note = f"{generator} not installed"
            generator = None

        # Handle glob patterns (containing '*') for per-file watchable discovery
        resolved_path = os.path.join(project_root, pattern)
        if "*" in pattern:
            matched_files = glob_match(resolved_path)
            if not matched_files:
                continue
            for matched in sorted(matched_files):
                rel_path = os.path.relpath(matched, project_root)
                stem = Path(matched).stem
                entry_name = name_format.replace("{stem}", stem)
                entry = {
                    "name": entry_name,
                    "path": rel_path,
                    "generator": generator,
                    "generator_args": generator_args,
                    "staleness_days": template.get("staleness_days", 14),
                    "signals": list(template.get("signals", [])),
                    "discovered": True,
                }
                if generator_note:
                    entry["generator_note"] = generator_note
                discovered.append(entry)
        else:
            if not os.path.exists(resolved_path):
                continue
            entry = {
                "name": name_format,
                "path": pattern,
                "generator": generator,
                "generator_args": generator_args,
                "staleness_days": template.get("staleness_days", 14),
                "signals": list(template.get("signals", [])),
                "discovered": True,
            }
            if generator_note:
                entry["generator_note"] = generator_note
            discovered.append(entry)

    return discovered


def merge_discovered_with_manual(discovered: list[dict], existing_path: str) -> list[dict]:
    """Merge newly discovered watchables with manually added entries.

    Manual entries (those without discovered: True) are preserved.
    Discovered entries are replaced wholesale with new discovery results.
    """
    manual = []
    if os.path.exists(existing_path):
        try:
            with open(existing_path) as f:
                existing = yaml.safe_load(f)
            if existing and "watchables" in existing:
                for w in existing["watchables"]:
                    if not w.get("discovered", False):
                        manual.append(w)
        except (OSError, yaml.YAMLError):
            pass

    return discovered + manual


def write_discovered_config(watchables: list[dict], project_root: str) -> str:
    """Write discovered watchables to .interwatch/watchables.yaml.

    Returns the path to the written file.
    """
    state_dir = os.path.join(project_root, STATE_DIR)
    os.makedirs(state_dir, exist_ok=True)
    out_path = os.path.join(state_dir, "watchables.yaml")

    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    header = (
        f"# Auto-generated by interwatch discovery — {timestamp}\n"
        f"# Regenerate: python3 scripts/interwatch-scan.py --rediscover\n"
        f"# Manual entries (without 'discovered: true') are preserved on rediscovery.\n\n"
    )

    content = {"watchables": watchables}
    with open(out_path, "w") as f:
        f.write(header)
        yaml.dump(content, f, default_flow_style=False, sort_keys=False)

    return out_path


def record_refresh(doc_name: str) -> None:
    """Reset baselines for a specific doc after a generator refresh.

    Updates last-scan.json to record that the doc was just regenerated,
    so the next scan sees zero delta for bead counts.
    """
    state = load_last_scan()
    baselines = state.get("baselines", {})

    # Snapshot current bead counts as the new baseline for this doc
    baselines[doc_name] = {
        "refreshed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "bead_closed_count": _count_bd_lines("closed"),
        "bead_created_count": _count_bd_lines("open"),
    }

    state["baselines"] = baselines
    state["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    save_last_scan(state)


def main():
    parser = argparse.ArgumentParser(description="Pre-compute interwatch drift signals")
    parser.add_argument("--config", help="Path to watchables.yaml")
    parser.add_argument("--check", help="Check single doc path (filter output)")
    parser.add_argument("--save-state", action="store_true",
                        help="Write baselines to .interwatch/last-scan.json after scan")
    parser.add_argument("--record-refresh", metavar="DOC_NAME",
                        help="Reset baselines for a doc after refresh (e.g., 'roadmap')")
    parser.add_argument("--discover", action="store_true",
                        help="Auto-discover watchables, write .interwatch/watchables.yaml, then scan")
    parser.add_argument("--rediscover", action="store_true",
                        help="Force re-discovery even if .interwatch/watchables.yaml exists")
    parser.add_argument("--discover-only", action="store_true",
                        help="Run discovery without scanning (just write config)")
    args = parser.parse_args()

    # Handle --record-refresh: update baselines and exit
    if args.record_refresh:
        record_refresh(args.record_refresh)
        print(json.dumps({"recorded_refresh": args.record_refresh}))
        return

    # Handle discovery flags
    if args.discover or args.rediscover or args.discover_only:
        plugin_config = load_plugin_config()
        discovered_path = os.path.join(STATE_DIR, "watchables.yaml")
        project_root = os.getcwd()

        if args.rediscover or not os.path.exists(discovered_path):
            discovered = discover_watchables(plugin_config, project_root)
            merged = merge_discovered_with_manual(discovered, discovered_path)
            out = write_discovered_config(merged, project_root)

            summary = {
                "discovered": len(discovered),
                "manual_preserved": len(merged) - len(discovered),
                "written_to": out,
            }
            print(json.dumps(summary), file=sys.stderr)

        if args.discover_only:
            return

    config = load_config(args.config)
    watchables = config.get("watchables", [])

    # Load baseline state for snapshot-delta signals
    last_scan = load_last_scan()
    baselines = last_scan.get("baselines", {})

    result = {
        "scan_date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "watchables": {},
    }

    for w in watchables:
        if args.check and w["path"] != args.check:
            continue
        doc_baseline = baselines.get(w["name"])
        result["watchables"][w["name"]] = scan_watchable(w, doc_baseline)

    json.dump(result, sys.stdout, indent=2)
    print()  # trailing newline

    # Persist state if requested
    if args.save_state:
        # Update baselines with current bead counts for all scanned docs
        closed_count = _count_bd_lines("closed")
        open_count = _count_bd_lines("open")
        for w in watchables:
            if args.check and w["path"] != args.check:
                continue
            name = w["name"]
            if name not in baselines:
                baselines[name] = {}
            baselines[name]["bead_closed_count"] = closed_count
            baselines[name]["bead_created_count"] = open_count
            baselines[name]["scanned_at"] = result["scan_date"]

        state = {
            "last_updated": result["scan_date"],
            "baselines": baselines,
        }
        save_last_scan(state)
        save_drift(result)


if __name__ == "__main__":
    main()
