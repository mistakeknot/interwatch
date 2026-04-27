#!/usr/bin/env python3
"""Tests for pretool-doc-access hook.

Three test classes (per universal-gotchas guidance — must cover all three):

1. test_decide_unit — pure unit tests on decide() with controlled drift dicts
   and log entry lists. Fast, deterministic.

2. test_subprocess_synthetic — end-to-end test by running the bash hook
   wrapper as a subprocess against a synthetic project (tempdir with .git,
   .interwatch/drift.json, no real watchables.yaml). Catches PATH/permission
   bugs that unit tests miss.

3. test_real_environment — runs the hook against the actual Sylveste repo's
   live .interwatch/drift.json and verifies advisory output for the
   currently-High 'claude-md' watchable. Catches integration bugs that pass
   on synthetic input but fail in production (the four bug classes called
   out in universal-gotchas).

Run: python3 -m pytest interverse/interwatch/tests/test_pretool_doc_access.py -v
Or: python3 interverse/interwatch/tests/test_pretool_doc_access.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent
HOOK_SH = PLUGIN_ROOT / "hooks" / "pretool-doc-access.sh"
HOOK_PY = PLUGIN_ROOT / "hooks" / "pretool_doc_access.py"
SCAN_PY = PLUGIN_ROOT / "scripts" / "interwatch-scan.py"

sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))
import pretool_doc_access as hook  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────────


def _drift(watchables: dict) -> dict:
    return {
        "scan_date": "2026-04-27T20:00:00",
        "watchables": watchables,
    }


def _watchable(path: str, confidence: str, score: int = 1, generator: str | None = "interpath:roadmap") -> dict:
    return {
        "path": path,
        "exists": True,
        "score": score,
        "confidence": confidence,
        "stale": False,
        "signals": {},
        "recommended_action": "auto-refresh",
        "generator": generator,
        "generator_args": {},
    }


# ── 1. unit tests on decide() ──────────────────────────────────────────────


class DecideUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 4, 27, 22, 0, 0)
        self.cwd = Path.cwd()

    def _payload(self, file_path: str, tool: str = "Read") -> dict:
        return {"tool_name": tool, "tool_input": {"file_path": file_path}}

    def test_green_emits_nothing(self) -> None:
        drift = _drift({"a": _watchable("CLAUDE.md", "Green")})
        out, log = hook.decide(self._payload(str(self.cwd / "CLAUDE.md")), drift, {}, [], now=self.now)
        self.assertIsNone(out)
        self.assertIsNone(log)

    def test_low_emits_nothing(self) -> None:
        drift = _drift({"a": _watchable("CLAUDE.md", "Low")})
        out, log = hook.decide(self._payload(str(self.cwd / "CLAUDE.md")), drift, {}, [], now=self.now)
        self.assertIsNone(out)
        self.assertIsNone(log)

    def test_medium_emits_advisory_no_log(self) -> None:
        drift = _drift({"a": _watchable("CLAUDE.md", "Medium")})
        out, log = hook.decide(self._payload(str(self.cwd / "CLAUDE.md")), drift, {}, [], now=self.now)
        self.assertIsNotNone(out)
        self.assertIn("Medium", out["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(log)  # advisory-only, no log

    def test_high_emits_advisory_no_autofire(self) -> None:
        drift = _drift({"claude-md": _watchable("CLAUDE.md", "High", score=1)})
        out, log = hook.decide(self._payload(str(self.cwd / "CLAUDE.md")), drift, {}, [], now=self.now)
        self.assertIsNotNone(out)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("High", ctx)
        self.assertNotIn("AUTO-FIRE", ctx)
        self.assertIsNone(log)  # High never auto-fires

    def test_certain_fires_when_no_history(self) -> None:
        drift = _drift({"roadmap": _watchable("docs/roadmap.md", "Certain", score=5)})
        out, log = hook.decide(self._payload(str(self.cwd / "docs/roadmap.md")), drift, {}, [], now=self.now)
        self.assertIsNotNone(out)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("AUTO-FIRE", ctx)
        self.assertIn("/interwatch:refresh roadmap", ctx)
        self.assertEqual(log["outcome"], "fired")

    def test_certain_cooldown_blocks_second_fire(self) -> None:
        recent_iso = (self.now - timedelta(hours=2)).isoformat(timespec="seconds")
        prior_log = [{"ts": recent_iso, "name": "roadmap", "tool": "Read", "outcome": "fired"}]
        drift = _drift({"roadmap": _watchable("docs/roadmap.md", "Certain")})
        out, log = hook.decide(self._payload(str(self.cwd / "docs/roadmap.md")), drift, {}, prior_log, now=self.now)
        self.assertIsNotNone(out)
        # advisory degrades: still notes Certain but does NOT contain "AUTO-FIRE" (since gates blocked).
        self.assertNotIn("AUTO-FIRE", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(log["outcome"], "cooldown")

    def test_certain_after_cooldown_fires_again(self) -> None:
        old_iso = (self.now - timedelta(hours=25)).isoformat(timespec="seconds")
        prior_log = [{"ts": old_iso, "name": "roadmap", "tool": "Read", "outcome": "fired"}]
        drift = _drift({"roadmap": _watchable("docs/roadmap.md", "Certain")})
        out, log = hook.decide(self._payload(str(self.cwd / "docs/roadmap.md")), drift, {}, prior_log, now=self.now)
        self.assertEqual(log["outcome"], "fired")
        self.assertIn("AUTO-FIRE", out["hookSpecificOutput"]["additionalContext"])

    def test_daily_budget_caps_fires(self) -> None:
        # 5 fires today already, default cap is 5 → next one is budget-blocked.
        prior_log = [
            {"ts": self.now.replace(hour=h).isoformat(timespec="seconds"),
             "name": f"doc{h}", "tool": "Read", "outcome": "fired"}
            for h in range(1, 6)
        ]
        drift = _drift({"newdoc": _watchable("docs/newdoc.md", "Certain")})
        out, log = hook.decide(self._payload(str(self.cwd / "docs/newdoc.md")), drift, {}, prior_log, now=self.now)
        self.assertEqual(log["outcome"], "budget")
        self.assertNotIn("AUTO-FIRE", out["hookSpecificOutput"]["additionalContext"])

    def test_daily_budget_resets_at_utc_midnight(self) -> None:
        yesterday = self.now - timedelta(days=1)
        prior_log = [
            {"ts": yesterday.replace(hour=h).isoformat(timespec="seconds"),
             "name": f"doc{h}", "tool": "Read", "outcome": "fired"}
            for h in range(1, 10)  # 9 fires yesterday — does not count
        ]
        drift = _drift({"newdoc": _watchable("docs/newdoc.md", "Certain")})
        out, log = hook.decide(self._payload(str(self.cwd / "docs/newdoc.md")), drift, {}, prior_log, now=self.now)
        self.assertEqual(log["outcome"], "fired")

    def test_kill_switch_blocks_autofire(self) -> None:
        cfg = {"auto_refresh": {"enabled": False}}
        drift = _drift({"roadmap": _watchable("docs/roadmap.md", "Certain")})
        out, log = hook.decide(self._payload(str(self.cwd / "docs/roadmap.md")), drift, cfg, [], now=self.now)
        self.assertEqual(log["outcome"], "disabled")
        self.assertNotIn("AUTO-FIRE", out["hookSpecificOutput"]["additionalContext"])

    def test_per_watchable_opt_out(self) -> None:
        cfg = {"auto_refresh": {"watchables": {"roadmap": {"enabled": False}}}}
        drift = _drift({
            "roadmap": _watchable("docs/roadmap.md", "Certain"),
            "vision": _watchable("docs/vision.md", "Certain"),
        })
        # roadmap is opted out
        out, log = hook.decide(self._payload(str(self.cwd / "docs/roadmap.md")), drift, cfg, [], now=self.now)
        self.assertEqual(log["outcome"], "disabled")
        # vision still fires
        out2, log2 = hook.decide(self._payload(str(self.cwd / "docs/vision.md")), drift, cfg, [], now=self.now)
        self.assertEqual(log2["outcome"], "fired")

    def test_certain_without_generator_does_not_fire(self) -> None:
        drift = _drift({"orphan": _watchable("docs/orphan.md", "Certain", generator=None)})
        out, log = hook.decide(self._payload(str(self.cwd / "docs/orphan.md")), drift, {}, [], now=self.now)
        self.assertEqual(log["outcome"], "no_generator")
        self.assertNotIn("AUTO-FIRE", out["hookSpecificOutput"]["additionalContext"])

    def test_dir_watchable_matches_files_underneath(self) -> None:
        drift = _drift({"solutions": {**_watchable("docs/solutions/", "High"), "path": "docs/solutions/"}})
        # File inside the directory
        out, _log = hook.decide(
            self._payload(str(self.cwd / "docs/solutions/2026-04-27-foo.md")),
            drift, {}, [], now=self.now,
        )
        self.assertIsNotNone(out)
        self.assertIn("solutions", out["hookSpecificOutput"]["additionalContext"])

    def test_unwatched_file_silent(self) -> None:
        drift = _drift({"a": _watchable("CLAUDE.md", "Certain")})
        out, log = hook.decide(self._payload(str(self.cwd / "src/random.py")), drift, {}, [], now=self.now)
        self.assertIsNone(out)
        self.assertIsNone(log)

    def test_missing_file_path_silent(self) -> None:
        out, log = hook.decide({"tool_name": "Read", "tool_input": {}}, _drift({}), {}, [], now=self.now)
        self.assertIsNone(out)
        self.assertIsNone(log)


# ── 2. subprocess + synthetic project ──────────────────────────────────────


class SubprocessSyntheticTests(unittest.TestCase):
    """Run the actual bash hook entry point against a tempdir project.

    Catches: missing executable bit, wrong shebang resolution, python path
    issues, fail-open behavior on missing config.
    """

    def test_silent_on_unknown_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / ".git").mkdir()
            state = tmp / ".interwatch"
            state.mkdir()
            (state / "drift.json").write_text(json.dumps(_drift({
                "x": _watchable("watched.md", "High"),
            })))
            payload = {"tool_name": "Read", "tool_input": {"file_path": str(tmp / "unrelated.md")}}
            result = subprocess.run(
                ["bash", str(HOOK_SH)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                cwd=str(tmp),
                timeout=10,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "")

    def test_advisory_emitted_for_high_watchable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / ".git").mkdir()
            (tmp / "watched.md").write_text("contents\n")
            state = tmp / ".interwatch"
            state.mkdir()
            (state / "drift.json").write_text(json.dumps(_drift({
                "x": _watchable("watched.md", "High"),
            })))
            payload = {"tool_name": "Read", "tool_input": {"file_path": str(tmp / "watched.md")}}
            result = subprocess.run(
                ["bash", str(HOOK_SH)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                cwd=str(tmp),
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr}")
            out = json.loads(result.stdout)
            self.assertIn("additionalContext", out["hookSpecificOutput"])
            self.assertIn("High", out["hookSpecificOutput"]["additionalContext"])

    def test_fail_open_on_missing_drift_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / ".git").mkdir()
            payload = {"tool_name": "Read", "tool_input": {"file_path": str(tmp / "anything.md")}}
            result = subprocess.run(
                ["bash", str(HOOK_SH)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                cwd=str(tmp),
                timeout=10,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "")

    def test_certain_fires_writes_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / ".git").mkdir()
            (tmp / "doc.md").write_text("hi\n")
            state = tmp / ".interwatch"
            state.mkdir()
            (state / "drift.json").write_text(json.dumps(_drift({
                "doc": _watchable("doc.md", "Certain"),
            })))
            payload = {"tool_name": "Read", "tool_input": {"file_path": str(tmp / "doc.md")}}
            result = subprocess.run(
                ["bash", str(HOOK_SH)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                cwd=str(tmp),
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr}")
            out = json.loads(result.stdout)
            self.assertIn("AUTO-FIRE", out["hookSpecificOutput"]["additionalContext"])
            log_path = state / "auto-refresh.log"
            self.assertTrue(log_path.exists())
            entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["outcome"], "fired")


# ── 3. real environment integration ────────────────────────────────────────


class RealEnvironmentTests(unittest.TestCase):
    """Run the hook against the live Sylveste .interwatch/drift.json.

    These tests confirm the hook behaves correctly on production-shape data:
    real path lengths, real watchable names, real drift confidence values.
    Skipped if drift.json is missing.
    """

    @classmethod
    def setUpClass(cls) -> None:
        # Walk up from PLUGIN_ROOT to find a containing repo with .interwatch
        for parent in [PLUGIN_ROOT, *PLUGIN_ROOT.parents]:
            if (parent / ".interwatch" / "drift.json").exists():
                cls.repo_root = parent
                cls.drift = json.loads((parent / ".interwatch" / "drift.json").read_text())
                return
        cls.repo_root = None
        cls.drift = None

    def setUp(self) -> None:
        if self.drift is None:
            self.skipTest("no live .interwatch/drift.json available")

    def test_hook_recognizes_a_real_watchable(self) -> None:
        # Pick the first watchable with confidence != Green
        target_name = None
        target_path = None
        for name, w in self.drift["watchables"].items():
            if w.get("confidence") in {"Medium", "High", "Certain"} and w.get("path"):
                target_name = name
                target_path = w["path"]
                break
        if target_name is None:
            self.skipTest("no non-Green watchables in live drift.json (nothing to assert against)")

        abs_path = self.repo_root / target_path
        # For directory watchables, point at any file inside
        if target_path.endswith("/"):
            children = list(abs_path.glob("**/*.md"))
            if not children:
                self.skipTest(f"directory watchable {target_path} has no .md files")
            abs_path = children[0]

        payload = {"tool_name": "Read", "tool_input": {"file_path": str(abs_path)}}
        result = subprocess.run(
            ["bash", str(HOOK_SH)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=str(self.repo_root),
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr}")
        # Must have emitted advisory output (any non-Green tier produces it)
        self.assertTrue(
            result.stdout.strip(),
            msg=f"expected advisory for {target_name} ({target_path}) but got empty stdout",
        )
        out = json.loads(result.stdout)
        self.assertIn("additionalContext", out["hookSpecificOutput"])
        self.assertIn(target_name, out["hookSpecificOutput"]["additionalContext"])


# ── 4. record_refresh no-op detection ──────────────────────────────────────


class RecordRefreshNoopTests(unittest.TestCase):
    """Verify --record-refresh detects no-op refreshes via content_hash."""

    def test_noop_detected_when_hash_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "doc.md").write_text("hello world\n")
            state = tmp / ".interwatch"
            state.mkdir()
            # Write watchables.yaml so record_refresh can resolve the path.
            (state / "watchables.yaml").write_text(
                "watchables:\n  - name: doc\n    path: doc.md\n    signals: []\n"
            )
            # Pre-seed last-scan.json with the file's hash (simulating prior scan)
            import hashlib
            content_hash = hashlib.sha256((tmp / "doc.md").read_bytes()).hexdigest()
            (state / "last-scan.json").write_text(json.dumps({
                "last_updated": "2026-04-27T20:00:00",
                "baselines": {"doc": {"content_hash": content_hash}},
            }))

            # File is unchanged → record_refresh should detect no-op
            result = subprocess.run(
                ["python3", str(SCAN_PY), "--record-refresh", "doc"],
                cwd=str(tmp), capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output["outcome"], "no-op")
            self.assertFalse(output["baselines_updated"])

            # Log should have a no-op entry
            log_path = state / "auto-refresh.log"
            self.assertTrue(log_path.exists())
            entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
            self.assertEqual(entries[-1]["outcome"], "no-op")

    def test_real_refresh_detected_when_hash_differs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "doc.md").write_text("old\n")
            state = tmp / ".interwatch"
            state.mkdir()
            (state / "watchables.yaml").write_text(
                "watchables:\n  - name: doc\n    path: doc.md\n    signals: []\n"
            )
            import hashlib
            old_hash = hashlib.sha256(b"old\n").hexdigest()
            (state / "last-scan.json").write_text(json.dumps({
                "baselines": {"doc": {"content_hash": old_hash}},
            }))

            # Simulate a generator: rewrite doc.md
            (tmp / "doc.md").write_text("new content\n")

            result = subprocess.run(
                ["python3", str(SCAN_PY), "--record-refresh", "doc"],
                cwd=str(tmp), capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output["outcome"], "refreshed")
            self.assertTrue(output["baselines_updated"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
