"""
Phase 3 — Exercise 2: Build a SkillLoader from Scratch

Implement the SkillLoader class. When complete, the test block at the bottom
should pass without errors.
"""
import yaml
import tempfile
from pathlib import Path
from typing import Optional


# ── IMPLEMENT THESE ───────────────────────────────────────────────────────────

def parse_skill_file(content: str) -> tuple[dict, str]:
    """
    Parse a skill .md file into (frontmatter_dict, body_str).
    Split on '---', yaml.safe_load the first block, return rest as body.
    Return ({}, content) if parsing fails.
    """
    # TODO: implement
    pass


class SkillLoader:
    def __init__(self, skills_dir: Path):
        self._index: dict[str, tuple[dict, str]] = {}
        # TODO: call _load_all(skills_dir)

    def _load_all(self, directory: Path) -> None:
        """Scan directory for *.md files, parse each, store in self._index."""
        # TODO: glob("*.md"), parse each, store as {name: (frontmatter, body)}
        pass

    def match_skill(self, matter_type: str, user_input: str) -> Optional[str]:
        """
        Return skill body (str) or None.
        Priority: exact matter_type match > trigger_keyword match > None.
        """
        # TODO: implement — check matter_types list first, then trigger_keywords
        pass

    def list_skills(self) -> list[str]:
        """Return list of loaded skill names."""
        # TODO: return sorted list of self._index keys
        pass


# ── SAMPLE SKILL FILES (write these to a temp dir for testing) ────────────────

WRIT_SKILL = """---
name: writ_petition
trigger_keywords:
  - writ petition
  - article 226
  - high court
  - fundamental rights
matter_types:
  - writ
  - constitutional
jurisdiction: india
---
## Writ Petition Skill
Check alternative remedy first. Verify fundamental right violation.
"""

NOTICE_SKILL = """---
name: legal_notice
trigger_keywords:
  - legal notice
  - demand notice
  - notice period
matter_types:
  - legal_notice
  - demand
jurisdiction: india
---
## Legal Notice Skill
Notice period: 30 days civil, 60 days government. Use registered post.
"""


# ── TESTS ─────────────────────────────────────────────────────────────────────

def run_tests():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        (skills_dir / "writ_petition.md").write_text(WRIT_SKILL)
        (skills_dir / "legal_notice.md").write_text(NOTICE_SKILL)

        loader = SkillLoader(skills_dir)

        # Test 1: list_skills
        skills = loader.list_skills()
        assert len(skills) == 2, f"Expected 2 skills, got {len(skills)}"
        print(f"✓ list_skills: {skills}")

        # Test 2: match by matter_type
        result = loader.match_skill("writ", "")
        assert result is not None, "Should match 'writ' by matter_type"
        assert "Writ Petition" in result, "Body should contain skill content"
        print("✓ match_skill by matter_type works")

        # Test 3: match by keyword
        result = loader.match_skill("unknown", "I need a legal notice sent to my landlord")
        assert result is not None, "Should match by keyword 'legal notice'"
        print("✓ match_skill by keyword works")

        # Test 4: no match returns None
        result = loader.match_skill("criminal", "I need bail for my client")
        assert result is None, "Should return None when no skill matches"
        print("✓ no match returns None")

        # Test 5: matter_type takes priority over keyword
        # If input has "legal notice" keywords but matter_type is "writ"
        result = loader.match_skill("writ", "I need a writ about a legal notice")
        assert "Writ" in result, "matter_type match should take priority"
        print("✓ matter_type priority over keyword works")

        print("\n✅ All tests passed!")


if __name__ == "__main__":
    run_tests()

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
# 1. Open lexagent/skills/loader.py — how does the real SkillLoader differ from yours?
# 2. What happens if two skills both match the same matter_type? Which wins?
# 3. The _load_all runs once at startup (not on every request). Why does this matter
#    for performance? What is the downside of this design?
