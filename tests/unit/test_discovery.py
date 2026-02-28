"""Unit tests for interwatch auto-discovery logic and new signal evaluators."""

import json
import os
import time
from pathlib import Path

import pytest
import yaml


# ─── detect_module_name ──────────────────────────────────────────────


def test_detect_module_name_from_plugin_json(scan_module, tmp_path):
    """Reads name from .claude-plugin/plugin.json."""
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(json.dumps({"name": "mymodule", "version": "1.0.0"}))

    assert scan_module.detect_module_name(str(tmp_path)) == "mymodule"


def test_detect_module_name_fallback_dirname(scan_module, tmp_path):
    """Falls back to directory basename when no plugin.json."""
    assert scan_module.detect_module_name(str(tmp_path)) == tmp_path.name


# ─── discover_watchables ─────────────────────────────────────────────


def _make_config_with_templates():
    """Build a minimal config with templates and rules for testing."""
    return {
        "signal_templates": {
            "agents-md": {
                "generator": "interdoc:interdoc",
                "generator_args": {},
                "staleness_days": 14,
                "signals": [
                    {"type": "file_renamed", "weight": 3},
                    {"type": "commits_since_update", "weight": 1, "threshold": 20},
                ],
            },
            "vision": {
                "generator": "interpath:artifact-gen",
                "generator_args": {"type": "vision"},
                "staleness_days": 30,
                "signals": [
                    {"type": "companion_extracted", "weight": 2},
                ],
            },
            "roadmap": {
                "generator": "interpath:artifact-gen",
                "generator_args": {"type": "roadmap"},
                "staleness_days": 7,
                "signals": [
                    {"type": "bead_closed", "weight": 2},
                ],
            },
            "distillation-candidates": {
                "generator": None,
                "generator_args": {},
                "staleness_days": 30,
                "signals": [
                    {"type": "unsynthesized_doc_count", "weight": 2, "threshold": 5},
                ],
            },
        },
        "discovery_rules": [
            {"pattern": "AGENTS.md", "template": "agents-md", "name_format": "agents-md"},
            {
                "pattern": "docs/{module}-vision.md",
                "template": "vision",
                "name_format": "{module}-vision",
            },
            {
                "pattern": "docs/vision.md",
                "template": "vision",
                "name_format": "vision",
                "skip_if_exists": "docs/{module}-vision.md",
            },
            {
                "pattern": "docs/{module}-roadmap.md",
                "template": "roadmap",
                "name_format": "{module}-roadmap",
            },
            {
                "pattern": "docs/roadmap.md",
                "template": "roadmap",
                "name_format": "roadmap",
                "skip_if_exists": "docs/{module}-roadmap.md",
            },
            {
                "pattern": "docs/solutions/",
                "template": "distillation-candidates",
                "name_format": "distillation-candidates",
            },
        ],
    }


def test_discover_finds_agents_md(scan_module, tmp_path):
    """Discovers AGENTS.md when it exists."""
    (tmp_path / "AGENTS.md").write_text("# Agents")
    config = _make_config_with_templates()

    result = scan_module.discover_watchables(config, str(tmp_path))

    names = [w["name"] for w in result]
    assert "agents-md" in names

    agents_entry = [w for w in result if w["name"] == "agents-md"][0]
    assert agents_entry["discovered"] is True
    assert agents_entry["path"] == "AGENTS.md"


def test_discover_dedup_vision(scan_module, tmp_path):
    """Skips docs/vision.md when namespaced version exists."""
    docs = tmp_path / "docs"
    docs.mkdir()
    # Create both generic and namespaced
    (docs / "vision.md").write_text("# Vision")
    (docs / f"{tmp_path.name}-vision.md").write_text("# Vision")

    config = _make_config_with_templates()
    result = scan_module.discover_watchables(config, str(tmp_path))

    vision_entries = [w for w in result if "vision" in w["name"]]
    assert len(vision_entries) == 1, f"Expected 1 vision entry, got {len(vision_entries)}: {vision_entries}"
    assert vision_entries[0]["name"] == f"{tmp_path.name}-vision"


def test_discover_dedup_roadmap(scan_module, tmp_path):
    """Skips docs/roadmap.md when namespaced version exists."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "roadmap.md").write_text("# Roadmap")
    (docs / f"{tmp_path.name}-roadmap.md").write_text("# Roadmap")

    config = _make_config_with_templates()
    result = scan_module.discover_watchables(config, str(tmp_path))

    roadmap_entries = [w for w in result if "roadmap" in w["name"]]
    assert len(roadmap_entries) == 1
    assert roadmap_entries[0]["name"] == f"{tmp_path.name}-roadmap"


def test_discover_skips_missing_docs(scan_module, tmp_path):
    """Non-existent paths produce no entries."""
    config = _make_config_with_templates()
    result = scan_module.discover_watchables(config, str(tmp_path))
    assert len(result) == 0, f"Expected 0 discovered entries, got {result}"


# ─── merge / write ───────────────────────────────────────────────────


def test_merge_preserves_manual(scan_module, tmp_path):
    """Manual entries survive rediscovery."""
    existing_path = tmp_path / "watchables.yaml"
    existing_data = {
        "watchables": [
            {"name": "custom-doc", "path": "docs/custom.md", "generator": None,
             "generator_args": {}, "signals": [], "staleness_days": 30},
            {"name": "agents-md", "path": "AGENTS.md", "generator": "interdoc:interdoc",
             "generator_args": {}, "signals": [], "staleness_days": 14, "discovered": True},
        ]
    }
    existing_path.write_text(yaml.dump(existing_data))

    new_discovered = [
        {"name": "agents-md", "path": "AGENTS.md", "generator": None,
         "generator_args": {}, "signals": [], "staleness_days": 14, "discovered": True},
    ]

    merged = scan_module.merge_discovered_with_manual(new_discovered, str(existing_path))

    names = [w["name"] for w in merged]
    assert "custom-doc" in names, "Manual entry was lost"
    assert names.count("agents-md") == 1, "Discovered entry duplicated"


def test_write_config_has_header(scan_module, tmp_path):
    """Generated file has auto-generated comment header."""
    watchables = [
        {"name": "test", "path": "test.md", "discovered": True},
    ]
    out = scan_module.write_discovered_config(watchables, str(tmp_path))

    content = Path(out).read_text()
    assert "Auto-generated by interwatch discovery" in content
    assert "--rediscover" in content


# ─── New signal evaluators ───────────────────────────────────────────


def test_eval_unsynthesized_doc_count(scan_module, tmp_path, monkeypatch):
    """Counts old docs without synthesized_into."""
    monkeypatch.chdir(tmp_path)

    solutions = tmp_path / "docs" / "solutions"
    solutions.mkdir(parents=True)

    # Old doc without frontmatter — should count
    old_doc = solutions / "problem-1.md"
    old_doc.write_text("# Problem 1\nSome content")
    # Make it older than 14 days
    old_time = time.time() - (20 * 86400)
    os.utime(old_doc, (old_time, old_time))

    # Old doc with synthesized_into — should NOT count
    synth_doc = solutions / "problem-2.md"
    synth_doc.write_text("---\nsynthesized_into: patterns/foo.md\n---\n# Problem 2")
    os.utime(synth_doc, (old_time, old_time))

    # Recent doc — should NOT count (too new)
    new_doc = solutions / "problem-3.md"
    new_doc.write_text("# Problem 3\nRecent")

    # INDEX.md — should be skipped
    index = solutions / "INDEX.md"
    index.write_text("# Index")
    os.utime(index, (old_time, old_time))

    # threshold=1 → 1 qualifying doc → should fire
    assert scan_module.eval_unsynthesized_doc_count("", 0, threshold=1) == 1
    # threshold=5 → only 1 qualifying doc → should not fire
    assert scan_module.eval_unsynthesized_doc_count("", 0, threshold=5) == 0


def test_eval_skills_without_compact(scan_module, tmp_path, monkeypatch):
    """Counts SKILL.md >90 lines without compact."""
    monkeypatch.chdir(tmp_path)

    skills = tmp_path / "skills"

    # Skill with >90 lines, no compact — should count
    s1 = skills / "skill-a"
    s1.mkdir(parents=True)
    (s1 / "SKILL.md").write_text("# Skill A\n" + "line\n" * 100)

    # Skill with >90 lines, HAS compact — should NOT count
    s2 = skills / "skill-b"
    s2.mkdir()
    (s2 / "SKILL.md").write_text("# Skill B\n" + "line\n" * 100)
    (s2 / "SKILL-compact.md").write_text("# Skill B compact")

    # Skill with <90 lines, no compact — should NOT count
    s3 = skills / "skill-c"
    s3.mkdir()
    (s3 / "SKILL.md").write_text("# Skill C\n" + "short\n" * 10)

    # threshold=1 → 1 qualifying skill → should fire
    assert scan_module.eval_skills_without_compact("", 0, threshold=1) == 1
    # threshold=5 → only 1 qualifying skill → should not fire
    assert scan_module.eval_skills_without_compact("", 0, threshold=5) == 0


def test_eval_roadmap_bead_coverage_graceful(scan_module):
    """Returns 0 when lib-watch.sh is not at expected path."""
    # When running from a temp dir, lib-watch.sh won't be at the relative path
    # The function resolves from __file__ which is the real scanner location,
    # so it will find lib-watch.sh. But if bd/audit script is missing, it
    # should still gracefully return 0.
    result = scan_module.eval_roadmap_bead_coverage("/nonexistent/doc.md", 0)
    assert result == 0
