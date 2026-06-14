"""
Tests for the .skill ZIP package and skill-directory loading formats.

Covers:
- _parse_skill_package: valid ZIP, missing manifest, missing SKILL.md, corrupt ZIP
- _parse_skill_directory: valid dir, missing manifest, missing SKILL.md
- _skills_from_dir: picks up .md, .skill ZIP, and sub-directories in one pass
- build(): round-trip (build then load matches source)
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from themis.skills.build_skill import build
from themis.skills.loader import (
    _parse_skill_directory,
    _parse_skill_package,
    _skills_from_dir,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MANIFEST = """\
name: test_skill
description: A test skill
trigger_keywords:
  - test
  - demo
matter_types:
  - test_matter
min_inference_tier: 2
"""

SKILL_MD = """\
# Test Skill

This is the test skill body.
"""

REF_MD = """\
# Reference A

Reference content.
"""

LEARNINGS_MD = """\
## Rules

[2026-01-01] Always test.
"""


def _make_skill_zip(
    tmp_path: Path,
    manifest: str = MANIFEST,
    skill_md: str = SKILL_MD,
    include_refs: bool = True,
    include_learnings: bool = True,
) -> Path:
    """Write a .skill ZIP to tmp_path and return its path."""
    skill_path = tmp_path / "test_skill.skill"
    with zipfile.ZipFile(skill_path, "w") as zf:
        zf.writestr("manifest.yaml", manifest)
        zf.writestr("SKILL.md", skill_md)
        if include_refs:
            zf.writestr("references/ref_a.md", REF_MD)
        if include_learnings:
            zf.writestr("learnings.md", LEARNINGS_MD)
    return skill_path


def _make_skill_dir(
    tmp_path: Path,
    manifest: str = MANIFEST,
    skill_md: str = SKILL_MD,
    include_refs: bool = True,
    include_learnings: bool = True,
) -> Path:
    """Create a skill source directory in tmp_path and return its path."""
    skill_dir = tmp_path / "test_skill"
    skill_dir.mkdir()
    (skill_dir / "manifest.yaml").write_text(manifest)
    (skill_dir / "SKILL.md").write_text(skill_md)
    if include_refs:
        refs = skill_dir / "references"
        refs.mkdir()
        (refs / "ref_a.md").write_text(REF_MD)
    if include_learnings:
        (skill_dir / "learnings.md").write_text(LEARNINGS_MD)
    return skill_dir


# ---------------------------------------------------------------------------
# _parse_skill_package
# ---------------------------------------------------------------------------


class TestParseSkillPackage:
    def test_valid_zip_returns_expected_fields(self, tmp_path):
        path = _make_skill_zip(tmp_path)
        result = _parse_skill_package(path)

        assert result is not None
        assert result["name"] == "test_skill"
        assert result["description"] == "A test skill"
        assert "test" in result["trigger_keywords"]
        assert "test_matter" in result["matter_types"]
        assert result["min_tier"] == 2

    def test_body_contains_skill_md(self, tmp_path):
        path = _make_skill_zip(tmp_path)
        result = _parse_skill_package(path)
        assert "This is the test skill body." in result["body"]

    def test_body_contains_reference_content(self, tmp_path):
        path = _make_skill_zip(tmp_path)
        result = _parse_skill_package(path)
        assert "Reference content." in result["body"]

    def test_body_contains_learnings(self, tmp_path):
        path = _make_skill_zip(tmp_path)
        result = _parse_skill_package(path)
        assert "Always test." in result["body"]

    def test_without_refs_and_learnings(self, tmp_path):
        path = _make_skill_zip(tmp_path, include_refs=False, include_learnings=False)
        result = _parse_skill_package(path)
        assert result is not None
        assert "This is the test skill body." in result["body"]

    def test_missing_manifest_returns_none(self, tmp_path):
        skill_path = tmp_path / "bad.skill"
        with zipfile.ZipFile(skill_path, "w") as zf:
            zf.writestr("SKILL.md", SKILL_MD)
        assert _parse_skill_package(skill_path) is None

    def test_corrupt_zip_returns_none(self, tmp_path):
        skill_path = tmp_path / "corrupt.skill"
        skill_path.write_bytes(b"this is not a zip file")
        assert _parse_skill_package(skill_path) is None

    def test_default_min_tier_when_absent(self, tmp_path):
        manifest_no_tier = "name: test_skill\ndescription: x\n"
        path = _make_skill_zip(tmp_path, manifest=manifest_no_tier)
        result = _parse_skill_package(path)
        assert result["min_tier"] == 4  # default


# ---------------------------------------------------------------------------
# _parse_skill_directory
# ---------------------------------------------------------------------------


class TestParseSkillDirectory:
    def test_valid_dir_returns_expected_fields(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        result = _parse_skill_directory(skill_dir)

        assert result is not None
        assert result["name"] == "test_skill"
        assert result["description"] == "A test skill"
        assert "demo" in result["trigger_keywords"]
        assert result["min_tier"] == 2

    def test_body_contains_skill_md(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        result = _parse_skill_directory(skill_dir)
        assert "This is the test skill body." in result["body"]

    def test_body_contains_reference_content(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        result = _parse_skill_directory(skill_dir)
        assert "Reference content." in result["body"]

    def test_body_contains_learnings(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        result = _parse_skill_directory(skill_dir)
        assert "Always test." in result["body"]

    def test_missing_manifest_returns_none(self, tmp_path):
        skill_dir = tmp_path / "no_manifest"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(SKILL_MD)
        assert _parse_skill_directory(skill_dir) is None

    def test_no_refs_no_learnings(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path, include_refs=False, include_learnings=False)
        result = _parse_skill_directory(skill_dir)
        assert result is not None
        assert "This is the test skill body." in result["body"]


# ---------------------------------------------------------------------------
# _skills_from_dir: unified scan
# ---------------------------------------------------------------------------


class TestSkillsFromDir:
    def test_picks_up_flat_md(self, tmp_path):
        (tmp_path / "flat.md").write_text(
            "---\nname: flat_skill\ndescription: flat\ntrigger_keywords: [flat]\nmatter_types: [flat]\n---\nFlat body.\n"
        )
        results = _skills_from_dir(tmp_path)
        names = [r["name"] for r in results]
        assert "flat_skill" in names

    def test_picks_up_skill_zip(self, tmp_path):
        _make_skill_zip(tmp_path)
        results = _skills_from_dir(tmp_path)
        names = [r["name"] for r in results]
        assert "test_skill" in names

    def test_picks_up_skill_directory(self, tmp_path):
        _make_skill_dir(tmp_path)
        results = _skills_from_dir(tmp_path)
        names = [r["name"] for r in results]
        assert "test_skill" in names

    def test_all_three_formats_in_same_dir(self, tmp_path):
        # flat .md
        (tmp_path / "flat.md").write_text(
            "---\nname: flat_skill\ndescription: flat\ntrigger_keywords: [flat]\nmatter_types: [flat]\n---\nFlat body.\n"
        )
        # .skill ZIP
        _make_skill_zip(tmp_path)
        # Skill directory with a different name to avoid collision
        dir_skill = tmp_path / "dir_skill"
        dir_skill.mkdir()
        (dir_skill / "manifest.yaml").write_text(
            "name: dir_skill\ndescription: dir\ntrigger_keywords: [dir]\nmatter_types: [dir]\n"
        )
        (dir_skill / "SKILL.md").write_text("Dir body.")

        results = _skills_from_dir(tmp_path)
        names = {r["name"] for r in results}
        assert {"flat_skill", "test_skill", "dir_skill"}.issubset(names)

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        results = _skills_from_dir(tmp_path / "does_not_exist")
        assert results == []

    def test_corrupt_skill_zip_is_skipped(self, tmp_path):
        (tmp_path / "bad.skill").write_bytes(b"not a zip")
        results = _skills_from_dir(tmp_path)
        assert all(r["name"] != "" for r in results)  # corrupt file doesn't crash


# ---------------------------------------------------------------------------
# build() round-trip
# ---------------------------------------------------------------------------


class TestBuildRoundTrip:
    def test_round_trip_body_matches(self, tmp_path):
        """build() then _parse_skill_package() should produce same body as _parse_skill_directory()."""
        source_dir = _make_skill_dir(tmp_path)
        out_dir = tmp_path / "dist"

        built_path = build(source_dir, out_dir)
        assert built_path.exists()
        assert built_path.suffix == ".skill"

        from_dir = _parse_skill_directory(source_dir)
        from_zip = _parse_skill_package(built_path)

        assert from_dir is not None
        assert from_zip is not None
        assert from_zip["name"] == from_dir["name"]
        assert from_zip["trigger_keywords"] == from_dir["trigger_keywords"]
        assert from_zip["matter_types"] == from_dir["matter_types"]
        assert from_zip["min_tier"] == from_dir["min_tier"]
        # Body content should contain same key pieces
        for fragment in ["This is the test skill body.", "Reference content.", "Always test."]:
            assert fragment in from_zip["body"]

    def test_build_raises_if_missing_manifest(self, tmp_path):
        skill_dir = tmp_path / "no_manifest"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(SKILL_MD)
        with pytest.raises(FileNotFoundError, match="manifest.yaml"):
            build(skill_dir, tmp_path)

    def test_build_raises_if_missing_skill_md(self, tmp_path):
        skill_dir = tmp_path / "no_skill_md"
        skill_dir.mkdir()
        (skill_dir / "manifest.yaml").write_text(MANIFEST)
        with pytest.raises(FileNotFoundError, match="SKILL.md"):
            build(skill_dir, tmp_path)
