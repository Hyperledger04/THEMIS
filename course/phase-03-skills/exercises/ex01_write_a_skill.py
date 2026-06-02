"""
Phase 3 — Exercise 1: Write a Legal Notice Skill

Your task: complete the LEGAL_NOTICE_SKILL_CONTENT string below, then run this
script to validate your skill file parses correctly.

A skill file has two parts:
  1. YAML frontmatter between --- markers
  2. Markdown body with guidance for the agent
"""
import yaml

# ── YOUR SKILL FILE ──────────────────────────────────────────────────────────
# Complete the TODOs. The validation block at the bottom will tell you if it's correct.

LEGAL_NOTICE_SKILL_CONTENT = """---
name: legal_notice
trigger_keywords:
  # TODO: add at least 3 keywords (e.g. "legal notice", "demand notice", "section 80")
  - legal notice

matter_types:
  # TODO: list matter types this skill applies to (at least 2)
  - legal_notice

jurisdiction: india
---
## Legal Notice Skill

### When to Use This Skill
# TODO: describe when a lawyer would send a legal notice

### Structure of a Legal Notice
# TODO: list the required sections (sender details, recipient, subject, facts, demand, time limit)
1. Sender details
2. ...

### Key Legal Requirements
# TODO: mention:
#   - Notice period (30 days for most civil matters, 60 days for government)
#   - Proper addressing to the right party
#   - Specific demand with deadline
#   - Mode of service (registered post / courier)

### Statutes to Check
# TODO: list at least 2 relevant statutes (e.g. Section 80 CPC for government notices)

### Drafting Notes
# TODO: add at least 2 drafting tips
"""

# ── VALIDATION ───────────────────────────────────────────────────────────────

def parse_skill_file(content: str) -> tuple[dict, str]:
    parts = content.strip().split("---")
    if len(parts) < 3:
        return {}, content
    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        print(f"YAML parse error: {e}")
        return {}, content
    body = "---".join(parts[2:]).strip()
    return frontmatter or {}, body


def validate_skill(content: str) -> bool:
    fm, body = parse_skill_file(content)
    errors = []

    if not fm.get("name"):
        errors.append("Missing 'name' in frontmatter")

    keywords = fm.get("trigger_keywords", [])
    if len(keywords) < 3:
        errors.append(f"Need at least 3 trigger_keywords, found {len(keywords)}")

    matter_types = fm.get("matter_types", [])
    if len(matter_types) < 2:
        errors.append(f"Need at least 2 matter_types, found {len(matter_types)}")

    if "# TODO" in body:
        todo_count = body.count("# TODO")
        errors.append(f"Body still has {todo_count} TODO(s) — complete them")

    if len(body) < 200:
        errors.append(f"Body too short ({len(body)} chars) — add more guidance")

    if errors:
        print("\n❌ Skill validation FAILED:")
        for e in errors:
            print(f"   - {e}")
        return False
    else:
        print("\n✅ Skill validation PASSED!")
        print(f"   Name: {fm['name']}")
        print(f"   Keywords: {keywords}")
        print(f"   Matter types: {matter_types}")
        print(f"   Body length: {len(body)} chars")
        return True


if __name__ == "__main__":
    print("Parsing your legal notice skill...")
    fm, body = parse_skill_file(LEGAL_NOTICE_SKILL_CONTENT)
    print(f"\nFrontmatter keys: {list(fm.keys())}")
    print(f"Body preview: {body[:100]}...")
    validate_skill(LEGAL_NOTICE_SKILL_CONTENT)

# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
# 1. Open lexagent/skills/ — what skill files already exist? What matter types do they cover?
# 2. Open lexagent/skills/loader.py — what happens when match_skill() finds no match?
# 3. The skill body goes into the system prompt. What happens if it's 10,000 chars long?
#    Hint: check lexagent/nodes/draft.py for any truncation logic.
