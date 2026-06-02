# phase-03-skills / 01_what_is_a_skill.py
# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: THE SKILLS SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════
# Skills are lightweight .md files that make LexAgent matter-type aware.
# A writ petition drafter needs different guidance than a legal notice drafter.
# Skills provide that context — without touching a single line of Python.

# ── SECTION 1: THE PROBLEM ──────────────────────────────────────────────────
#
# Every type of legal matter has its own structure, its own leading cases,
# its own procedural traps.  A single generic prompt cannot capture all of
# that.  If we hard-code matter-specific instructions into node code we end
# up with a tangled mess that only a programmer can update.
#
# The lawyer should be able to say: "Add support for rent disputes" and do it
# themselves — in a text editor, without opening a terminal.
#
# That is the problem skills solve.

print("── SECTION 1: THE PROBLEM ──────────────────────────────────────────")
print("Different matters need different guidance.")
print("Writ petitions ≠ legal notices ≠ cheque bounce cases.")
print("Hard-coding everything into Python makes the lawyer dependent on a dev.")
print()

# ── SECTION 2: THE SOLUTION ─────────────────────────────────────────────────
#
# Skills live in  lexagent/skills/  as plain Markdown files.
#
#   lexagent/skills/
#     writ_petition.md
#     legal_notice.md
#     cheque_bounce.md
#     rent_dispute.md    ← lawyer can drop this in anytime
#
# Each file has two parts:
#   1. YAML frontmatter  (between --- markers)  — machine-readable metadata
#   2. Markdown body                            — human-readable instructions
#
# The loader in  lexagent/skills/loader.py  reads all these files at startup
# and picks the right one based on what the lawyer tells the agent.

print("── SECTION 2: THE SOLUTION ─────────────────────────────────────────")
print("Skills are .md files in  lexagent/skills/")
print("The SkillLoader picks the right skill and injects it into the prompt.")
print()

# ── SECTION 3: A COMPLETE SKILL FILE ────────────────────────────────────────
#
# Here is what a real skill file looks like.  Study it carefully —
# the frontmatter keys (name, trigger_keywords, matter_types) are the contract
# between the skill file and the loader code.

WRIT_PETITION_SKILL = """---
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
- Bandhua Mukti Morcha v. Union of India, (1984) 3 SCC 161 (PIL standing)

### Procedural Notes
- Check if alternative remedy exists (mandatory pre-condition)
- Limitation: generally 3 years but check laches doctrine
- Urgent hearing: file CM Application for listing
- Vakalatnama required even for PIL petitions
"""

print("── SECTION 3: A COMPLETE SKILL FILE ───────────────────────────────")
print("Skill file content (as stored in  lexagent/skills/writ_petition.md ):")
print(WRIT_PETITION_SKILL)

# ── SECTION 4: THREE THINGS SKILLS PROVIDE ─────────────────────────────────
#
# Every skill gives the agent three things it cannot guess on its own:
#
#   1. STRUCTURE GUIDANCE
#      The exact heading order, numbering style, and Latin phrases that
#      courts expect for that matter type.  Judges notice when these are wrong.
#
#   2. KEY CASES TO LOOK FOR
#      Landmark judgments the draft must cite (or consciously distinguish).
#      The research node uses these as seed queries for Indian Kanoon.
#
#   3. PROCEDURAL STEPS
#      Prerequisite checks (alternative remedy), limitation traps, filing
#      formalities.  Missing any one can get the matter rejected in-limine.

print("── SECTION 4: THREE THINGS SKILLS PROVIDE ─────────────────────────")
things = [
    ("Structure Guidance",  "Exact heading order and court-specific formatting"),
    ("Key Cases",           "Seed judgments for the research node to expand on"),
    ("Procedural Steps",    "Checklist of pre-conditions and filing formalities"),
]
for label, desc in things:
    print(f"  ✦  {label:20s} — {desc}")
print()

# ── SECTION 5: NO CODE REQUIRED ─────────────────────────────────────────────
#
# This is the most important design decision in the skills system.
#
# A lawyer can add a brand-new skill by:
#   1. Opening a text editor
#   2. Copying an existing .md skill file
#   3. Changing the frontmatter and body
#   4. Dropping the file into  lexagent/skills/
#   5. Restarting the agent (or triggering a reload)
#
# No Python.  No YAML schema validator.  No pull request.
# The loader is fault-tolerant: a malformed skill file is skipped with a
# warning, and the rest of the skills still load.

print("── SECTION 5: NO CODE REQUIRED ─────────────────────────────────────")
print("To add a new skill:")
steps = [
    "cp lexagent/skills/writ_petition.md  lexagent/skills/rent_dispute.md",
    "Edit the frontmatter (name, keywords, matter_types)",
    "Edit the Markdown body (structure, cases, procedure)",
    "Restart the agent — the loader picks it up automatically",
]
for i, step in enumerate(steps, 1):
    print(f"  Step {i}: {step}")
print()
print("Files to look at next:")
print("  lexagent/skills/              ← drop new .md files here")
print("  lexagent/skills/loader.py     ← SkillLoader implementation")

# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
print()
print("── PAUSE AND THINK ──────────────────────────────────────────────────")
questions = [
    "Why do we separate the YAML frontmatter from the Markdown body "
    "instead of using all-YAML or all-Markdown?",

    "The loader falls back to None when no skill matches.  What should the "
    "draft node do differently when there is no active skill?",

    "trigger_keywords is a list of strings.  What are the failure modes of "
    "simple substring matching?  How would you make matching smarter?",

    "If a matter could match two skills (e.g. a constitutional rent dispute), "
    "how should the loader decide which skill wins?",

    "The CLAUDE.md says 'lawyers write skills in a text editor.'  What "
    "validation would you add to give helpful error messages for bad YAML?",
]
for i, q in enumerate(questions, 1):
    print(f"\n  Q{i}. {q}")
print()
