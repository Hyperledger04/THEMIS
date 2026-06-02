# phase-03-skills / 03_skill_loader.py
# ═══════════════════════════════════════════════════════════════════════════════
# THE SKILL LOADER — scans the skills/ directory, indexes all skills, matches
# the right one for each incoming matter
# ═══════════════════════════════════════════════════════════════════════════════
# Requires: pip install pyyaml

import tempfile
from pathlib import Path
from typing import Optional

import yaml

# ── SECTION 1: THE SKILLLOADER CLASS ────────────────────────────────────────
#
# SkillLoader is instantiated once at agent startup and kept in memory.
# It reads every *.md file in the skills directory, parses each one with
# parse_skill_file(), and stores the result in a dict called _index.
#
# WHY not re-read files on every request?
# File I/O on every call would slow the agent down.  Skills change rarely
# (a lawyer might add one new skill per quarter).  A simple restart reloads
# everything.  Good enough for v1.
#
# The class is intentionally stateless after __init__ completes —
# _index is populated once and never mutated, so it is safe to share
# across async tasks without a lock.

print("── SECTION 1: THE SKILLLOADER CLASS ────────────────────────────────")
print("SkillLoader loads all .md files on startup → builds an in-memory index.")
print()

# ── SECTION 2: THE INDEX STRUCTURE ──────────────────────────────────────────
#
# _index maps   skill_name  →  (frontmatter_dict, body_str)
#
#   {
#     "writ_petition":  ({"name": "writ_petition", "trigger_keywords": [...], ...},
#                        "## Writ Petition Skill\n..."),
#     "legal_notice":   ({"name": "legal_notice",  "trigger_keywords": [...], ...},
#                        "## Legal Notice Skill\n..."),
#   }
#
# Using a dict keyed by name gives O(1) lookup and makes it easy to list or
# introspect all loaded skills (useful for the lex setup wizard).

print("── SECTION 2: THE INDEX STRUCTURE ──────────────────────────────────")
print("_index = { skill_name: (frontmatter_dict, body_str) }")
print()


# ── SECTION 3: match_skill() ─────────────────────────────────────────────────
#
# Priority 1 (highest): matter_type is in the skill's  matter_types  list.
#   Example: matter_type="writ" matches a skill with matter_types=["writ"]
#
# Priority 2 (fallback): any keyword from trigger_keywords appears in the
#   lowercased user input string.
#   Example: user says "I need a writ petition against Delhi police" →
#            "writ petition" is in writ_petition.trigger_keywords → match.
#
# Priority 3 (no match): return None.  Caller handles gracefully.
#
# WHY this order?  matter_type is explicit — the intake node already asked
# the lawyer what kind of matter it is, so that answer is reliable.
# trigger_keywords is a softer signal (substring match on free text).

print("── SECTION 3: match_skill() MATCHING PRIORITY ───────────────────────")
print("  1. Exact matter_type match  (most reliable — intake asked explicitly)")
print("  2. Keyword in user_input    (fallback for free-text briefs)")
print("  3. None                     (no skill; agent uses base instructions)")
print()


# ── SECTION 4: FULL IMPLEMENTATION ──────────────────────────────────────────

print("── SECTION 4: FULL IMPLEMENTATION ─────────────────────────────────")


def parse_skill_file(content: str) -> tuple[dict, str]:
    """Reused from 02_yaml_frontmatter.py — split on ---, parse YAML."""
    parts = content.strip().split("---")
    if len(parts) < 3:
        return {}, content
    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}, content
    body = "---".join(parts[2:]).strip()
    return frontmatter, body


class SkillLoader:
    """
    Loads all .md skill files from a directory and matches the best one
    for a given matter type and user input.
    """

    def __init__(self, skills_dir: Path):
        # _index: skill_name → (frontmatter_dict, body_str)
        self._index: dict[str, tuple[dict, str]] = {}
        self._load_all(skills_dir)

    def _load_all(self, directory: Path) -> None:
        """Scan directory for *.md files and index each valid skill."""
        if not directory.exists():
            # WHY silently return? Skills dir may not exist in CI or on first
            # run.  The agent still works — it just has no active skill.
            return

        for path in directory.glob("*.md"):
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue  # skip unreadable files

            frontmatter, body = parse_skill_file(content)
            if not frontmatter:
                # No frontmatter → not a skill file (could be README.md)
                continue

            name = frontmatter.get("name", path.stem)
            self._index[name] = (frontmatter, body)

        print(f"  SkillLoader: indexed {len(self._index)} skill(s): "
              f"{list(self._index.keys())}")

    def match_skill(self, matter_type: str, user_input: str) -> Optional[str]:
        """
        Return the body of the best matching skill, or None.

        Priority: matter_type match > keyword match > None.
        """
        user_lower = user_input.lower()

        # Priority 1: explicit matter_type match
        for name, (fm, body) in self._index.items():
            if matter_type in fm.get("matter_types", []):
                return body

        # Priority 2: keyword in user_input
        for name, (fm, body) in self._index.items():
            keywords = fm.get("trigger_keywords", [])
            if any(kw.lower() in user_lower for kw in keywords):
                return body

        return None

    def list_skills(self) -> list[str]:
        """Return all loaded skill names — useful for the setup wizard."""
        return list(self._index.keys())


# ── SECTION 5: LIVE DEMO ─────────────────────────────────────────────────────

print("── SECTION 5: LIVE DEMO ────────────────────────────────────────────")

WRIT_SKILL_CONTENT = """---
name: writ_petition
trigger_keywords: ["writ petition", "article 226", "high court", "fundamental rights"]
matter_types: ["writ", "constitutional"]
jurisdiction: india
---
## Writ Petition Skill

### Structure
1. Court heading
2. Most Respectfully Showeth

### Key Cases to Research
- Maneka Gandhi v. Union of India, AIR 1978 SC 597
"""

NOTICE_SKILL_CONTENT = """---
name: legal_notice
trigger_keywords: ["legal notice", "demand notice", "section 80 cpc", "notice period"]
matter_types: ["notice", "demand"]
jurisdiction: india
---
## Legal Notice Skill

### Structure
1. Sender details
2. Recipient details
3. Subject of notice
4. Facts and grievance
5. Legal demand
6. Consequence of non-compliance
"""

# Write temp skill files so we can demo the file-based loader
with tempfile.TemporaryDirectory() as tmpdir:
    skills_dir = Path(tmpdir)
    (skills_dir / "writ_petition.md").write_text(WRIT_SKILL_CONTENT)
    (skills_dir / "legal_notice.md").write_text(NOTICE_SKILL_CONTENT)
    (skills_dir / "README.md").write_text("# Skills Directory\nDrop .md skills here.")

    loader = SkillLoader(skills_dir)
    print(f"\n  Available skills: {loader.list_skills()}")

    # Test 1: exact matter_type match
    result = loader.match_skill("writ", "I need help with my petition")
    print(f"\n  match_skill('writ', 'I need help with my petition')")
    print(f"  → matched skill body starts with: {result.splitlines()[0]!r}" if result else "  → None")

    # Test 2: keyword match (no explicit matter_type)
    result = loader.match_skill("unknown", "File a legal notice against landlord")
    print(f"\n  match_skill('unknown', 'File a legal notice against landlord')")
    print(f"  → matched skill body starts with: {result.splitlines()[0]!r}" if result else "  → None")

    # Test 3: no match at all
    result = loader.match_skill("tax", "Income tax appeal to ITAT")
    print(f"\n  match_skill('tax', 'Income tax appeal to ITAT')")
    print(f"  → {result!r} (no skill — agent uses base instructions)")

    # Test 4: README.md is NOT indexed (no frontmatter)
    print(f"\n  README.md was {'NOT ' if 'README' not in loader.list_skills() else ''}indexed ✓")

# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
print()
print("── PAUSE AND THINK ──────────────────────────────────────────────────")
questions = [
    "The loader is built once at startup.  If a lawyer drops a new skill file "
    "into lexagent/skills/ while the agent is running, it won't be picked up "
    "until restart.  What would a 'hot reload' implementation look like?",

    "_load_all() silently skips files with no frontmatter.  A README.md in "
    "the skills directory is therefore harmless.  Is there a downside to this "
    "silent-skip behaviour?  What would you log?",

    "match_skill() iterates the dict in insertion order (Python 3.7+).  "
    "If two skills both have matter_type='writ', the first one always wins.  "
    "How would you add a priority field to the frontmatter to control this?",

    "The keyword match is a simple substring check.  'article 226' in "
    "'I want to file article 226 petition' works fine.  Does it still work "
    "for 'Article 226' (capital A)?  Fix it if not.",

    "SkillLoader is instantiated in graph.py at build time.  Where in "
    "lexagent/nodes/draft.py should match_skill() be called, and how does "
    "the result get into the system prompt?",
]
for i, q in enumerate(questions, 1):
    print(f"\n  Q{i}. {q}")
print()
