"""Tests for interwatch plugin structure."""

import json
import subprocess
from pathlib import Path


def test_plugin_json_valid(project_root):
    """plugin.json is valid JSON with required fields."""
    path = project_root / ".claude-plugin" / "plugin.json"
    assert path.exists(), "Missing .claude-plugin/plugin.json"
    data = json.loads(path.read_text())
    assert data["name"] == "interwatch"
    assert "version" in data
    assert "description" in data


def test_marker_file_exists(project_root):
    """scripts/interwatch.sh marker file exists."""
    marker = project_root / "scripts" / "interwatch.sh"
    assert marker.exists(), "Missing scripts/interwatch.sh marker file"


def test_required_directories_exist(project_root):
    """All expected directories exist."""
    for d in ["skills", "commands", "hooks", "config", "scripts", "tests"]:
        assert (project_root / d).is_dir(), f"Missing directory: {d}"


def test_lib_watch_syntax(project_root):
    """hooks/lib-watch.sh passes bash syntax check."""
    result = subprocess.run(
        ["bash", "-n", str(project_root / "hooks" / "lib-watch.sh")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Syntax error in lib-watch.sh: {result.stderr}"


def test_watchables_yaml_valid(project_root):
    """config/watchables.yaml is valid YAML with expected structure."""
    import yaml
    path = project_root / "config" / "watchables.yaml"
    assert path.exists(), "Missing config/watchables.yaml"
    data = yaml.safe_load(path.read_text())
    assert "watchables" in data
    assert len(data["watchables"]) > 0
    for w in data["watchables"]:
        assert "name" in w, f"Watchable missing 'name': {w}"
        assert "path" in w, f"Watchable missing 'path': {w}"
        assert "generator" in w, f"Watchable missing 'generator': {w}"
        assert "signals" in w, f"Watchable missing 'signals': {w}"
        assert "staleness_days" in w, f"Watchable missing 'staleness_days': {w}"

    # Validate signal_templates section
    assert "signal_templates" in data, "Missing signal_templates section"
    templates = data["signal_templates"]
    assert len(templates) > 0, "signal_templates is empty"

    # Load the scanner to get valid signal types
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "interwatch_scan",
        str(project_root / "scripts" / "interwatch-scan.py"),
    )
    scan_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scan_mod)
    valid_signals = set(scan_mod.SIGNAL_EVALUATORS.keys())

    for tname, template in templates.items():
        assert "staleness_days" in template, f"Template '{tname}' missing staleness_days"
        assert "signals" in template, f"Template '{tname}' missing signals"
        for sig in template["signals"]:
            assert sig["type"] in valid_signals, (
                f"Template '{tname}' references unknown signal '{sig['type']}'"
            )

    # Validate discovery_rules section
    assert "discovery_rules" in data, "Missing discovery_rules section"
    rules = data["discovery_rules"]
    assert len(rules) > 0, "discovery_rules is empty"
    for rule in rules:
        assert "pattern" in rule, f"Discovery rule missing 'pattern': {rule}"
        assert "template" in rule, f"Discovery rule missing 'template': {rule}"
        assert rule["template"] in templates, (
            f"Discovery rule references unknown template '{rule['template']}'"
        )


def test_claude_md_exists(project_root):
    """CLAUDE.md exists."""
    assert (project_root / "CLAUDE.md").exists()


def test_agents_md_exists(project_root):
    """AGENTS.md exists."""
    assert (project_root / "AGENTS.md").exists()


def test_license_exists(project_root):
    """LICENSE exists."""
    assert (project_root / "LICENSE").exists()
