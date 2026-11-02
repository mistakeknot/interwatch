"""Provenance stamp in drift.json: the stamp must never carry a false label."""

import json
import subprocess

import pytest


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("one\n")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-q", "-m", "init")
    return r


def _head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def test_clean_tree_is_labelled_clean(scan_module, repo, tmp_path):
    p = scan_module.build_provenance(str(repo), str(repo))
    assert p["repo_commit"] == _head(repo)
    assert p["repo_dirty"] is False


def test_dirty_tree_is_never_labelled_clean(scan_module, repo):
    (repo / "a.txt").write_text("two\n")  # tracked edit
    assert scan_module.build_provenance(str(repo), str(repo))["repo_dirty"] is True


def test_untracked_file_is_dirty(scan_module, repo):
    (repo / "new.txt").write_text("x\n")
    assert scan_module.build_provenance(str(repo), str(repo))["repo_dirty"] is True


def test_own_output_dir_does_not_make_repo_dirty(scan_module, repo):
    (repo / ".interwatch").mkdir()
    (repo / ".interwatch" / "drift.json").write_text("{}")
    assert scan_module.build_provenance(str(repo), str(repo))["repo_dirty"] is False


def test_non_git_dir_is_unknown_not_clean(scan_module, tmp_path):
    p = scan_module.build_provenance(str(tmp_path), str(tmp_path))
    assert p["repo_commit"] is None
    assert p["repo_dirty"] is None  # unknown, never False


def test_save_drift_writes_stamp(scan_module, repo, monkeypatch):
    monkeypatch.chdir(repo)
    monkeypatch.setattr(scan_module, "STATE_DIR", ".interwatch")
    monkeypatch.setattr(scan_module, "DRIFT_FILE", ".interwatch/drift.json")
    scan_module.save_drift({"scan_date": "x", "watchables": {}})
    out = json.loads((repo / ".interwatch" / "drift.json").read_text())
    assert out["scan_date"] == "x"
    assert out["provenance"]["repo_commit"] == _head(repo)
    assert out["provenance"]["repo_dirty"] is False


def test_stamp_goes_stale_after_new_commit(scan_module, repo):
    """A saved stamp must differ from the current state once the repo moves on."""
    old = scan_module.build_provenance(str(repo), str(repo))
    (repo / "a.txt").write_text("three\n")
    _git(repo, "commit", "-qam", "next")
    new = scan_module.build_provenance(str(repo), str(repo))
    assert old["repo_commit"] != new["repo_commit"]
