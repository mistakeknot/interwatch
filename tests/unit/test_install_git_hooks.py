from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = PLUGIN_ROOT / "scripts" / "install-git-hooks.sh"


def test_generated_hook_is_posix_sh_compatible(tmp_path: Path) -> None:
    dash = shutil.which("dash")
    if dash is None:
        pytest.skip("dash is required to exercise the hook's sh shebang")

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "core.hooksPath", ".beads/hooks"],
        check=True,
    )

    hooks_dir = tmp_path / ".beads" / "hooks"
    hooks_dir.mkdir(parents=True)
    hook = hooks_dir / "post-merge"
    hook.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)

    for _ in range(2):
        subprocess.run(
            ["bash", str(INSTALLER), "--repo", str(tmp_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    result = subprocess.run(
        [dash, str(hook)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stderr == ""
