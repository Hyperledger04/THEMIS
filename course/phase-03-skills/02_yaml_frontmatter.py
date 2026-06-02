# phase-03-skills / 02_yaml_frontmatter.py
# ═══════════════════════════════════════════════════════════════════════════════
# YAML FRONTMATTER — machine-readable metadata at the top of a Markdown file
# ═══════════════════════════════════════════════════════════════════════════════
# Requires: pip install pyyaml   (already in LexAgent's pyproject.toml)

import yaml

# ── SECTION 1: WHAT YAML IS ──────────────────────────────────────────────────
#
# YAML = "YAML Ain't Markup Language"  (recursive acronym — yes, really)
# It is designed to be readable by humans and parseable by machines.
#
# Rules:
#   - Key: value  (colon + space)
#   - Lists start with  -  or use  [item, item]  inline syntax
#   - Indentation = 2 spaces (NOT tabs)
#   - Strings do not need quotes unless they contain special characters
#   - Comments start with  #

print("── SECTION 1: WHAT YAML IS ─────────────────────────────────────────")

YAML_EXAMPLE = """
name: writ_petition
trigger_keywords:
  - writ petition
  - article 226
matter_types: ["writ", "constitutional"]
jurisdiction: india
active: true
priority: 1
"""

parsed = yaml.safe_load(YAML_EXAMPLE)
print("Raw YAML string →")
print(YAML_EXAMPLE)
print("Parsed Python dict →")
for key, value in parsed.items():
    print(f"  {key!r:20s}: {value!r}  ({type(value).__name__})")
print()

# Notice:
#   - Both list syntaxes (block and inline) produce the same Python list
#   - "true" → Python True   (not the string "true")
#   - "1"    → Python int 1  (not the string "1")
#   YAML is strongly typed.  yaml.safe_load() handles the conversion.

# ── SECTION 2: THE FRONTMATTER PATTERN ──────────────────────────────────────
#
# Frontmatter is a YAML block at the very top of a Markdown file, wrapped in
# triple-dash markers.  Jekyll popularised it; Hugo, Gatsby, and many static
# site generators use the same convention.
#
# Layout:
#   ---           ← opening marker (line by itself)
#   key: value    ← YAML content
#   ---           ← closing marker (line by itself)
#   # Markdown body starts here
#
# Why triple dashes?  Because --- is not valid inside normal Markdown or YAML
# values, so it acts as an unambiguous delimiter.

print("── SECTION 2: THE FRONTMATTER PATTERN ─────────────────────────────")

SAMPLE_SKILL_FILE = """---
name: writ_petition
trigger_keywords: ["writ petition", "article 226", "high court", "fundamental rights"]
matter_types: ["writ", "constitutional"]
jurisdiction: india
---
## Writ Petition Skill

### Structure
1. Court heading (High Court / Supreme Court)
2. Writ Petition number
3. In the matter of [Parties]
4. Most Respectfully Showeth

### Key Cases to Research
- Maneka Gandhi v. Union of India, AIR 1978 SC 597 (Article 21 interpretation)
- L. Chandra Kumar v. Union of India, (1997) 3 SCC 261 (judicial review)

### Procedural Notes
- Check if alternative remedy exists (mandatory pre-condition)
- Limitation: generally 3 years but check laches doctrine
"""

print("Full skill file (frontmatter + body):")
print(SAMPLE_SKILL_FILE)

# ── SECTION 3: PARSING WITH PYYAML ──────────────────────────────────────────
#
# ALWAYS use  yaml.safe_load()  — NEVER  yaml.load()
#
# WHY: yaml.load() can execute arbitrary Python code embedded in the YAML.
# A malicious skill file could run  !!python/object/apply:os.system ["rm -rf /"]
# yaml.safe_load() refuses to deserialise any Python-specific tags — it only
# handles basic types (str, int, float, bool, list, dict, None).

print("── SECTION 3: PARSING WITH PYYAML — USE safe_load() ALWAYS ────────")

dangerous_yaml = "!!python/object/apply:os.system ['echo DANGER']"
try:
    yaml.safe_load(dangerous_yaml)
except yaml.YAMLError as e:
    print(f"safe_load() blocked dangerous tag: {type(e).__name__}")
print()

# ── SECTION 4: parse_skill_file() ───────────────────────────────────────────
#
# This function is the single entry point for reading any skill file.
# It splits the raw text on  ---  and handles edge cases gracefully.

print("── SECTION 4: parse_skill_file() ───────────────────────────────────")


def parse_skill_file(content: str) -> tuple[dict, str]:
    """
    Split a skill file into (frontmatter_dict, body_string).

    Returns ({}, content) if the file has no valid frontmatter — so the
    caller never has to handle None; it always gets a (dict, str) pair.
    """
    # WHY split on "---": the triple-dash is the conventional frontmatter
    # delimiter; splitting gives us at least 3 parts for a valid file:
    #   parts[0] = ""          (empty string before opening ---)
    #   parts[1] = YAML block
    #   parts[2] = Markdown body
    parts = content.strip().split("---")

    if len(parts) < 3:
        # No frontmatter found — return empty dict and original content
        return {}, content

    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        # Malformed YAML — skip this skill gracefully
        return {}, content

    # parts[2:] handles the (rare) case where the body itself contains "---"
    # (e.g. a horizontal rule in Markdown)
    body = "---".join(parts[2:]).strip()
    return frontmatter, body


print("parse_skill_file() implementation:")
print("  - Splits on '---'")
print("  - Parses parts[1] as YAML via yaml.safe_load()")
print("  - Joins parts[2:] as the Markdown body (handles --- inside body)")
print()

# ── SECTION 5: LIVE DEMO ─────────────────────────────────────────────────────

print("── SECTION 5: LIVE DEMO ────────────────────────────────────────────")

frontmatter, body = parse_skill_file(SAMPLE_SKILL_FILE)

print("Parsed frontmatter dict:")
for k, v in frontmatter.items():
    print(f"  {k:20s} = {v!r}")

print()
print(f"trigger_keywords list: {frontmatter['trigger_keywords']}")
print(f"matter_types list:     {frontmatter['matter_types']}")
print(f"Body length:           {len(body)} characters")
print(f"Body preview:          {body[:60]!r}...")
print()

# Edge case: skill file with no frontmatter
no_fm = "## Plain Markdown\nNo frontmatter here."
fm2, body2 = parse_skill_file(no_fm)
print(f"File with no frontmatter → frontmatter={fm2!r}, body={body2!r}")

# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
print()
print("── PAUSE AND THINK ──────────────────────────────────────────────────")
questions = [
    "The function returns  ({}, content)  when frontmatter is missing.  "
    "How does the SkillLoader in  lexagent/skills/loader.py  use that return "
    "value to decide whether to index the skill?",

    "What happens if a lawyer writes  trigger_keywords: writ petition  "
    "(a scalar string) instead of  trigger_keywords: [writ petition]  "
    "(a list)?  How would you make parse_skill_file() defensive against this?",

    "yaml.safe_load() returns None when given an empty string.  The  or {}  "
    "guard handles that.  What other YAML values would produce None from "
    "safe_load()?",

    "The body join  '---'.join(parts[2:])  is needed for Markdown bodies that "
    "contain horizontal rules.  Write a test case that would catch a bug here.",

    "Should parse_skill_file() validate that required keys (name, "
    "trigger_keywords, matter_types) are present?  Or should that be the "
    "loader's responsibility?  Argue both sides.",
]
for i, q in enumerate(questions, 1):
    print(f"\n  Q{i}. {q}")
print()
