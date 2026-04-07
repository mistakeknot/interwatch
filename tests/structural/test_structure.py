"""Tests for interwatch plugin structure."""

import json
import subprocess
import sys
from pathlib import Path

# Add interverse/ to path so _shared package is importable
_interverse = Path(__file__).resolve().parents[3]
if str(_interverse) not in sys.path:
    sys.path.insert(0, str(_interverse))

from _shared.tests.structural.test_base import StructuralTests


class TestStructure(StructuralTests):
    """Structural tests -- inherits shared base, adds plugin-specific checks."""

    def test_plugin_name(self, plugin_json):
        assert plugin_json["name"] == "interwatch"

    def test_marker_file_exists(self, project_root):
        """scripts/interwatch.sh marker file exists."""
        marker = project_root / "scripts" / "interwatch.sh"
        assert marker.exists(), "Missing scripts/interwatch.sh marker file"

    def test_required_directories_exist(self, project_root):
        """All expected directories exist."""
        for d in ["skills", "commands", "hooks", "config", "scripts", "tests"]:
            assert (project_root / d).is_dir(), f"Missing directory: {d}"

    def test_lib_watch_syntax(self, project_root):
        """hooks/lib-watch.sh passes bash syntax check."""
        result = subprocess.run(
            ["bash", "-n", str(project_root / "hooks" / "lib-watch.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error in lib-watch.sh: {result.stderr}"

    def test_watchables_yaml_valid(self, project_root):
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

    def test_agents_md_exists(self, project_root):
        """AGENTS.md exists."""
        assert (project_root / "AGENTS.md").exists()
