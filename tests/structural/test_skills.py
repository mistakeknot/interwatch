"""Tests for Interwatch skill structure."""

from pathlib import Path

import pytest

from helpers import parse_frontmatter


SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"
SKILL_DIRS = sorted(
    d for d in SKILLS_DIR.iterdir()
    if d.is_dir() and (d / "SKILL.md").exists()
)


def test_skill_count(skills_dir):
    """Total skill count matches expected value."""
    dirs = sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )
    assert len(dirs) == 1, (
        f"Expected 1 skill, found {len(dirs)}: {[d.name for d in dirs]}"
    )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_has_frontmatter(skill_dir):
    """Each SKILL.md has valid YAML frontmatter with 'name' and 'description'."""
    fm, _ = parse_frontmatter(skill_dir / "SKILL.md")
    assert fm is not None, f"{skill_dir.name}/SKILL.md has no frontmatter"
    assert "name" in fm, f"{skill_dir.name}/SKILL.md frontmatter missing 'name'"
    assert "description" in fm, f"{skill_dir.name}/SKILL.md frontmatter missing 'description'"


def test_doc_watch_phases_exist(skills_dir):
    """doc-watch skill has all expected phase files."""
    phases_dir = skills_dir / "doc-watch" / "phases"
    expected = ["detect.md", "assess.md", "refresh.md"]
    for name in expected:
        assert (phases_dir / name).exists(), f"Missing phase: {name}"


def test_doc_watch_references_exist(skills_dir):
    """doc-watch skill has reference files."""
    refs_dir = skills_dir / "doc-watch" / "references"
    expected = ["signals.md", "confidence-tiers.md", "watchables.md"]
    for name in expected:
        assert (refs_dir / name).exists(), f"Missing reference: {name}"
