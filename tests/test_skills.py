# Tests for the skill loader — written before the implementation (TDD).
# Run with: uv run pytest tests/test_skills.py -v

import textwrap
from pathlib import Path

import pytest

from lexagent.skills.loader import load_skill, _parse_frontmatter, _skills_from_dir


# ---------------------------------------------------------------------------
# Fixtures — build temporary skill files on disk so tests are self-contained
# ---------------------------------------------------------------------------


CIVIL_SKILL = textwrap.dedent("""\
    ---
    name: civil_litigation
    trigger_keywords: [plaint, injunction, civil suit, CPC, specific performance, recovery]
    matter_types: [civil_suit, injunction_application, execution_petition]
    ---

    # Civil Litigation Skill

    ## Structure Template
    1. In the Court of [Court Name]
    2. BETWEEN: [Parties]
    3. PRAYER
    4. VERIFICATION
""")

NOTICE_SKILL = textwrap.dedent("""\
    ---
    name: legal_notice
    trigger_keywords: [legal notice, demand notice, notice to pay, notice before suit]
    matter_types: [legal_notice, demand_notice]
    ---

    # Legal Notice Skill

    ## Structure Template
    1. FROM: [Sender]
    2. TO: [Recipient]
    3. NOTICE
    4. DEMAND
""")

CONTRACT_SKILL = textwrap.dedent("""\
    ---
    name: legal_contract
    trigger_keywords: [contract, agreement, MOU, NDA, deed, lease]
    matter_types: [contract_review, agreement_drafting, mou]
    ---

    # Legal Contract Skill

    ## Structure Template
    1. PARTIES
    2. RECITALS
    3. TERMS AND CONDITIONS
    4. SIGNATURES
""")

USER_OVERRIDE_SKILL = textwrap.dedent("""\
    ---
    name: civil_litigation
    trigger_keywords: [plaint, injunction, civil suit]
    matter_types: [civil_suit, injunction_application]
    ---

    # Civil Litigation Skill — Custom User Version
""")


@pytest.fixture()
def bundled_skills_dir(tmp_path):
    """A temporary directory acting as the bundled skills package dir."""
    d = tmp_path / "bundled"
    d.mkdir()
    (d / "civil_litigation.md").write_text(CIVIL_SKILL)
    (d / "legal_notice.md").write_text(NOTICE_SKILL)
    (d / "legal_contract.md").write_text(CONTRACT_SKILL)
    return d


@pytest.fixture()
def user_skills_dir(tmp_path):
    """A temporary directory acting as ~/.lexagent/skills (user-editable)."""
    d = tmp_path / "user"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# _parse_frontmatter tests
# ---------------------------------------------------------------------------


def test_parse_frontmatter_extracts_name():
    parsed = _parse_frontmatter(CIVIL_SKILL)
    assert parsed["name"] == "civil_litigation"


def test_parse_frontmatter_extracts_trigger_keywords():
    parsed = _parse_frontmatter(CIVIL_SKILL)
    assert "injunction" in parsed["trigger_keywords"]
    assert "plaint" in parsed["trigger_keywords"]


def test_parse_frontmatter_extracts_matter_types():
    parsed = _parse_frontmatter(CIVIL_SKILL)
    assert "injunction_application" in parsed["matter_types"]
    assert "civil_suit" in parsed["matter_types"]


def test_parse_frontmatter_body_returned():
    parsed = _parse_frontmatter(CIVIL_SKILL)
    assert "# Civil Litigation Skill" in parsed["body"]
    assert "PRAYER" in parsed["body"]


def test_parse_frontmatter_file_without_frontmatter():
    content = "# Just a markdown file with no YAML header"
    parsed = _parse_frontmatter(content)
    assert parsed["name"] == ""
    assert parsed["trigger_keywords"] == []
    assert parsed["matter_types"] == []
    assert "Just a markdown file" in parsed["body"]


# ---------------------------------------------------------------------------
# _skills_from_dir tests
# ---------------------------------------------------------------------------


def test_skills_from_dir_finds_all_md_files(bundled_skills_dir):
    skills = _skills_from_dir(bundled_skills_dir)
    names = [s["name"] for s in skills]
    assert "civil_litigation" in names
    assert "legal_notice" in names
    assert "legal_contract" in names


def test_skills_from_dir_empty_dir(tmp_path):
    skills = _skills_from_dir(tmp_path)
    assert skills == []


def test_skills_from_dir_nonexistent_path():
    skills = _skills_from_dir(Path("/this/does/not/exist"))
    assert skills == []


# ---------------------------------------------------------------------------
# load_skill — matching logic
# ---------------------------------------------------------------------------


def test_load_skill_by_exact_matter_type(bundled_skills_dir, user_skills_dir):
    result = load_skill("civil_suit", str(bundled_skills_dir), str(user_skills_dir))
    assert result is not None
    assert "Civil Litigation Skill" in result


def test_load_skill_by_trigger_keyword_injunction(bundled_skills_dir, user_skills_dir):
    result = load_skill("injunction application", str(bundled_skills_dir), str(user_skills_dir))
    assert result is not None
    assert "Civil Litigation Skill" in result


def test_load_skill_by_trigger_keyword_legal_notice(bundled_skills_dir, user_skills_dir):
    result = load_skill("legal notice for unpaid rent", str(bundled_skills_dir), str(user_skills_dir))
    assert result is not None
    assert "Legal Notice Skill" in result


def test_load_skill_by_trigger_keyword_contract(bundled_skills_dir, user_skills_dir):
    result = load_skill("contract review for software agreement", str(bundled_skills_dir), str(user_skills_dir))
    assert result is not None
    assert "Legal Contract Skill" in result


def test_load_skill_case_insensitive(bundled_skills_dir, user_skills_dir):
    result = load_skill("INJUNCTION APPLICATION", str(bundled_skills_dir), str(user_skills_dir))
    assert result is not None
    assert "Civil Litigation Skill" in result


def test_load_skill_returns_none_for_unknown_type(bundled_skills_dir, user_skills_dir):
    result = load_skill("tax advisory opinion", str(bundled_skills_dir), str(user_skills_dir))
    assert result is None


def test_load_skill_returns_none_for_empty_matter_type(bundled_skills_dir, user_skills_dir):
    result = load_skill("", str(bundled_skills_dir), str(user_skills_dir))
    assert result is None


# ---------------------------------------------------------------------------
# User skill overrides bundled skill with the same name
# ---------------------------------------------------------------------------


def test_user_skill_overrides_bundled(bundled_skills_dir, user_skills_dir):
    # Write a user override for civil_litigation
    (user_skills_dir / "civil_litigation.md").write_text(USER_OVERRIDE_SKILL)

    result = load_skill("injunction application", str(bundled_skills_dir), str(user_skills_dir))
    assert result is not None
    # Should get the user version, not the bundled one
    assert "Custom User Version" in result


def test_bundled_skill_used_when_no_user_override(bundled_skills_dir, user_skills_dir):
    # No user skills — bundled version should be returned
    result = load_skill("injunction application", str(bundled_skills_dir), str(user_skills_dir))
    assert result is not None
    assert "Custom User Version" not in result
    assert "Civil Litigation Skill" in result
