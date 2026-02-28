#!/usr/bin/env python3
"""Stranger-perspective correctness audit for interwatch.

Validates user-facing documentation against project reality by gathering
ground truth (actual counts, existing files, build commands, versions)
and dispatching to a review agent that checks each doc from a context-free
perspective.

Complements interwatch-scan.py: scan measures freshness (has the world
changed?), audit measures correctness (does the doc match reality?).

Usage:
    python3 interwatch-audit.py                    # Audit all eligible docs
    python3 interwatch-audit.py --check README.md  # Audit a single doc
    python3 interwatch-audit.py --gather-only      # Print ground truth JSON, skip audit
"""

import argparse
import json
import os
import subprocess
import sys
from glob import glob
from pathlib import Path


def run_cmd(cmd: list[str], cwd: str | None = None) -> str:
    """Run a command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=cwd)
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


# ─── Ground truth gatherers ──────────────────────────────────────────


def gather_plugin_counts() -> dict:
    """Count plugins from agent-rig.json categories."""
    rig_paths = [
        ".claude/agent-rig.json",
        os.path.expanduser("~/.claude/agent-rig.json"),
    ]
    for rig_path in rig_paths:
        if os.path.exists(rig_path):
            try:
                with open(rig_path) as f:
                    rig = json.load(f)
                counts = {}
                total = 0
                for category, plugins in rig.items():
                    if isinstance(plugins, list):
                        counts[category] = len(plugins)
                        total += len(plugins)
                counts["total"] = total
                return counts
            except (json.JSONDecodeError, OSError):
                pass
    return {"total": 0, "error": "agent-rig.json not found"}


def gather_component_counts(project_root: str = ".") -> dict:
    """Count skills, commands, agents, hooks in the current project."""
    counts = {}
    for kind, pattern in [
        ("skills", "skills/*/SKILL.md"),
        ("commands", "commands/*.md"),
        ("agents", "agents/*/*.md"),
        ("hooks", "hooks/*.sh"),
    ]:
        counts[kind] = len(glob(os.path.join(project_root, pattern)))
    return counts


def gather_build_commands(project_root: str = ".") -> dict:
    """Detect which build systems exist."""
    build_systems = {}
    checks = {
        "makefile": ["Makefile", "makefile", "GNUmakefile"],
        "go_mod": ["go.mod"],
        "package_json": ["package.json"],
        "cargo_toml": ["Cargo.toml"],
        "pyproject_toml": ["pyproject.toml"],
        "setup_py": ["setup.py"],
    }
    for system, files in checks.items():
        for f in files:
            path = os.path.join(project_root, f)
            if os.path.exists(path):
                build_systems[system] = path
                break
    return build_systems


def gather_file_existence(doc_paths: list[str]) -> dict:
    """Check which referenced files actually exist."""
    existence = {}
    for path in doc_paths:
        existence[path] = os.path.exists(path)
    return existence


def gather_version_info() -> dict:
    """Gather version information from various sources."""
    info = {}

    # Plugin version from plugin.json
    for manifest in [".claude-plugin/plugin.json", "plugin.json"]:
        if os.path.exists(manifest):
            try:
                with open(manifest) as f:
                    data = json.load(f)
                info["plugin_version"] = data.get("version", "")
                info["plugin_name"] = data.get("name", "")
            except (json.JSONDecodeError, OSError):
                pass
            break

    # Go version
    go_ver = run_cmd(["go", "version"])
    if go_ver:
        info["go_version"] = go_ver

    # Node version
    node_ver = run_cmd(["node", "--version"])
    if node_ver:
        info["node_version"] = node_ver

    return info


def gather_directory_structure(project_root: str = ".") -> dict:
    """Gather top-level directory structure for architecture validation."""
    structure = {}
    try:
        for entry in sorted(os.listdir(project_root)):
            full = os.path.join(project_root, entry)
            if entry.startswith("."):
                continue
            if os.path.isdir(full):
                # Count immediate children
                try:
                    children = [c for c in os.listdir(full) if not c.startswith(".")]
                    structure[entry] = {"type": "dir", "children": len(children)}
                except OSError:
                    structure[entry] = {"type": "dir", "children": 0}
    except OSError:
        pass
    return structure


def gather_prerequisites() -> dict:
    """Check which common prerequisites are installed."""
    tools = {}
    for tool, cmd in [
        ("git", ["git", "--version"]),
        ("go", ["go", "version"]),
        ("node", ["node", "--version"]),
        ("python3", ["python3", "--version"]),
        ("jq", ["jq", "--version"]),
        ("tmux", ["tmux", "-V"]),
        ("bd", ["bd", "version"]),
    ]:
        output = run_cmd(cmd)
        tools[tool] = {"installed": bool(output), "version": output}
    return tools


# ─── Doc extraction ──────────────────────────────────────────────────


def extract_links_from_doc(doc_path: str) -> list[str]:
    """Extract markdown links and file references from a document."""
    import re
    links = []
    try:
        with open(doc_path) as f:
            content = f.read()
    except OSError:
        return links

    # Markdown links: [text](path)
    for match in re.finditer(r'\[([^\]]*)\]\(([^)]+)\)', content):
        links.append(match.group(2))

    # Code block file paths: `path/to/file`
    for match in re.finditer(r'`([a-zA-Z][\w/.-]+\.\w+)`', content):
        candidate = match.group(1)
        if "/" in candidate and not candidate.startswith("http"):
            links.append(candidate)

    return links


def find_audit_eligible_docs(project_root: str = ".") -> list[str]:
    """Find user-facing documentation files eligible for correctness audit.

    Looks for:
    - README.md (always user-facing)
    - docs/guide-*.md (user guides)
    - CONTRIBUTING.md
    - install scripts
    """
    candidates = [
        "README.md",
        "CONTRIBUTING.md",
        "docs/guide-power-user.md",
        "docs/guide-full-setup.md",
        "docs/guide-contributing.md",
    ]

    # Also discover any guide-*.md files
    for f in glob(os.path.join(project_root, "docs/guide-*.md")):
        rel = os.path.relpath(f, project_root)
        if rel not in candidates:
            candidates.append(rel)

    return [c for c in candidates if os.path.exists(os.path.join(project_root, c))]


# ─── Ground truth assembly ───────────────────────────────────────────


def gather_ground_truth(project_root: str = ".", doc_paths: list[str] | None = None) -> dict:
    """Assemble all ground truth data for the audit agent."""
    if doc_paths is None:
        doc_paths = find_audit_eligible_docs(project_root)

    # Collect all referenced files from docs
    all_links = {}
    for doc in doc_paths:
        links = extract_links_from_doc(os.path.join(project_root, doc))
        all_links[doc] = links

    # Resolve relative links to check existence
    referenced_files = set()
    for doc, links in all_links.items():
        doc_dir = os.path.dirname(doc)
        for link in links:
            if link.startswith("http"):
                continue
            # Resolve relative to doc location
            resolved = os.path.normpath(os.path.join(doc_dir, link))
            referenced_files.add(resolved)
            # Also try from project root
            referenced_files.add(link)

    return {
        "audit_docs": doc_paths,
        "plugin_counts": gather_plugin_counts(),
        "build_systems": gather_build_commands(project_root),
        "versions": gather_version_info(),
        "prerequisites": gather_prerequisites(),
        "directory_structure": gather_directory_structure(project_root),
        "referenced_files": gather_file_existence(list(referenced_files)),
        "doc_links": all_links,
    }


# ─── Agent prompt generation ─────────────────────────────────────────


def generate_audit_prompt(ground_truth: dict) -> str:
    """Generate the prompt for the stranger-perspective audit agent."""
    docs = ground_truth["audit_docs"]
    truth_json = json.dumps(ground_truth, indent=2)

    return f"""You are a stranger reading these docs for the first time. You have ZERO context
about this project beyond what the docs themselves say. Your job is to find every
place where the docs are wrong, misleading, or incomplete.

## Documents to audit

{chr(10).join(f"- {d}" for d in docs)}

## Ground truth

This JSON contains verified facts about the project's current state. Use it to
check every claim in the docs:

```json
{truth_json}
```

## What to check

For each document, verify:

1. **Stale counts** — Do hardcoded numbers (plugin counts, command counts, etc.)
   match the ground truth?

2. **Wrong commands** — Do build commands, install commands, and CLI examples
   actually work? Cross-reference against `build_systems` (e.g., if no Makefile
   exists, `make build` is wrong).

3. **Broken links** — Do referenced files and URLs exist? Check `referenced_files`
   in ground truth.

4. **Cross-doc consistency** — Do different docs agree on the same facts? (e.g.,
   if README says "5 pillars" and a guide says "4 pillars", flag it)

5. **Missing prerequisites** — Are all tools needed by install/build steps listed
   in prerequisites? Check `prerequisites` ground truth.

6. **Deprecated references** — Are there references to tools, commands, or
   patterns that no longer exist?

7. **Version/output staleness** — Do version numbers or expected output snippets
   match current reality?

8. **Ambiguous paths** — Are file paths clear about their starting directory?
   (e.g., `cd project/subdir` — from where?)

## Output format

Return a JSON array of findings:

```json
[
  {{
    "file": "path/to/doc.md",
    "line_hint": "approximate line or section",
    "drift_class": "stale_count|wrong_command|broken_link|cross_doc|missing_prereq|deprecated_ref|version_stale|ambiguous_path",
    "severity": "high|medium|low",
    "current": "what the doc says",
    "expected": "what it should say (based on ground truth)",
    "fix_suggestion": "concrete replacement text"
  }}
]
```

Be thorough. Check every claim, every number, every command, every link.
If something looks plausible but you can't verify it from ground truth, skip it.
Only flag things you can prove are wrong from the data provided."""


def main():
    parser = argparse.ArgumentParser(
        description="Stranger-perspective correctness audit for interwatch"
    )
    parser.add_argument("--check", help="Audit a single doc path")
    parser.add_argument(
        "--gather-only",
        action="store_true",
        help="Print ground truth JSON without dispatching audit agent",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root directory (default: current directory)",
    )
    args = parser.parse_args()

    doc_paths = None
    if args.check:
        if not os.path.exists(os.path.join(args.project_root, args.check)):
            print(f"Error: {args.check} not found", file=sys.stderr)
            sys.exit(1)
        doc_paths = [args.check]

    ground_truth = gather_ground_truth(args.project_root, doc_paths)

    if args.gather_only:
        json.dump(ground_truth, sys.stdout, indent=2)
        print()
        return

    # Output both ground truth and prompt for the skill/command to consume
    output = {
        "ground_truth": ground_truth,
        "audit_prompt": generate_audit_prompt(ground_truth),
        "doc_count": len(ground_truth["audit_docs"]),
    }
    json.dump(output, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
