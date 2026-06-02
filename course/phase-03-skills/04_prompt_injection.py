# phase-03-skills / 04_prompt_injection.py
# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT INJECTION — assembling the system prompt from SOUL + skill + base
# ═══════════════════════════════════════════════════════════════════════════════
# No external imports needed — pure Python string operations.

# ── SECTION 1: HOW SYSTEM PROMPTS ARE ASSEMBLED ──────────────────────────────
#
# Every time the draft node calls the LLM it sends a system prompt.
# That system prompt is assembled from three distinct sources:
#
#   SOUL            ← from ~/.lexagent/SOUL.md
#                     Who the lawyer is, their bar number, drafting preferences
#
#   ACTIVE SKILL    ← from SkillLoader.match_skill(matter_type, user_input)
#                     Matter-specific structure, cases, procedural traps
#
#   BASE INSTRUCTIONS ← from lexagent/prompts/draft.txt  (or similar)
#                     Core task: "Draft a court-ready document..."
#
# The LLM sees all three as a single string.  Section separators make it
# easy for the model to mentally compartmentalise the different kinds of
# guidance.
#
# WHY assemble at call time, not hardcode?
#   Because SOUL can be updated by the lawyer between sessions, and the
#   active skill changes per matter.  Static concatenation at module load
#   would ignore both.

print("── SECTION 1: HOW SYSTEM PROMPTS ARE ASSEMBLED ─────────────────────")
print("  SOUL text     (who the lawyer is, style preferences)")
print("  + ACTIVE SKILL (structure, cases, procedure for this matter type)")
print("  + BASE INSTRUCTIONS (core task, output format)")
print("  ─────────────────────────────────────────────────────────────────")
print("  = SYSTEM PROMPT  sent to the LLM on every draft call")
print()

# ── SECTION 2: build_system_prompt() ────────────────────────────────────────
#
# This function is the single place that controls prompt shape.
# All three components are optional — the function degrades gracefully.
#
# Each present component is wrapped in a ## heading so the LLM knows what
# kind of guidance it is reading.

print("── SECTION 2: build_system_prompt() ────────────────────────────────")


def build_system_prompt(soul: str, skill: str, base: str) -> str:
    """
    Assemble a system prompt from three optional components.

    Args:
        soul: Contents of SOUL.md — lawyer profile and style preferences.
        skill: Active skill body returned by SkillLoader.match_skill().
        base: Core task instructions from lexagent/prompts/.

    Returns:
        Assembled system prompt string.
    """
    MAX_SKILL_CHARS = 2000  # see Section 3 for why this limit exists

    parts: list[str] = []

    if soul and soul.strip():
        parts.append(f"## Lawyer Profile\n{soul.strip()}")

    if skill and skill.strip():
        truncated = (
            skill[:MAX_SKILL_CHARS] + "..."
            if len(skill) > MAX_SKILL_CHARS
            else skill
        )
        parts.append(f"## Active Skill\n{truncated.strip()}")

    # Base instructions always go last — they are the primary task directive.
    # WHY last? The LLM gives more weight to instructions that appear later
    # in the context window (recency bias in attention).
    if base and base.strip():
        parts.append(f"## Instructions\n{base.strip()}")

    return "\n\n".join(parts)


print("  build_system_prompt(soul, skill, base) → assembled prompt string")
print("  All three args are optional; absent components are silently skipped.")
print()

# ── SECTION 3: TOKEN BUDGET ──────────────────────────────────────────────────
#
# LLMs have a context window (typically 200k tokens for claude-sonnet-4).
# The system prompt competes with the matter brief, conversation history,
# research findings, and the output itself.
#
# A token is roughly 4 characters of English text.
# 2000 characters ≈ 500 tokens — a reasonable budget for skill guidance.
#
# If a skill grows beyond 2000 chars it is almost certainly including
# information that belongs in the research node (full case text, statute
# excerpts) rather than the skill file.  The 2000-char limit enforces
# good skill hygiene without hard-failing.
#
# WHY truncate rather than error?
#   A truncated skill is better than a crashed agent.  Log a warning in
#   production so the lawyer knows to trim their skill file.

print("── SECTION 3: TOKEN BUDGET ──────────────────────────────────────────")
MAX_SKILL_CHARS = 2000
approx_tokens = MAX_SKILL_CHARS // 4
print(f"  MAX_SKILL_CHARS = {MAX_SKILL_CHARS} characters ≈ {approx_tokens} tokens")
print("  Skills over this limit are truncated (not errored).")
print("  Rule of thumb: if your skill exceeds 2000 chars, it's too detailed.")
print("  Move case excerpts and statute text to the research node instead.")
print()

# ── SECTION 4: SECTION SEPARATORS ────────────────────────────────────────────
#
# The assembled prompt uses  ##  Markdown headings as separators.
# The LLM is trained on vast amounts of Markdown and intuitively treats
# ## headings as section boundaries.
#
# Alternative: XML tags like <soul>...</soul>.  Both work; ## is simpler
# to read when you print the prompt for debugging.

print("── SECTION 4: SECTION SEPARATORS ───────────────────────────────────")
print("  Using ## Markdown headings as section separators.")
print("  The LLM treats ## as natural section boundaries (Markdown training).")
print("  Print the assembled prompt before sending to verify shape.")
print()

# ── SECTION 5: LIVE DEMO ─────────────────────────────────────────────────────

print("── SECTION 5: LIVE DEMO ────────────────────────────────────────────")

SOUL = """
Name: Priya Mehta
Bar Council: Bar Council of Delhi, Enrolment No. D/1234/2010
Specialisation: Constitutional Law, High Court Practice
Style: Formal, structured, no Latin except where conventional.
Preferred citation format: (Year) Volume SCC PageNo
"""

SKILL = """
## Writ Petition Skill

### Structure
1. Court heading (High Court / Supreme Court)
2. Writ Petition number
3. In the matter of [Parties]
4. Most Respectfully Showeth

### Key Cases
- Maneka Gandhi v. Union of India, AIR 1978 SC 597
- L. Chandra Kumar v. Union of India, (1997) 3 SCC 261

### Procedural Notes
- Verify no alternative remedy exists before filing
- Limitation: generally 3 years; check laches
"""

BASE = """
You are LexAgent, an AI drafting assistant for Indian litigation.
Draft a court-ready document based on the matter brief provided.
Use Indian legal citation format. Verify every citation before including it.
Output only the document — no explanatory commentary outside the draft.
"""

assembled = build_system_prompt(SOUL, SKILL, BASE)

print("Assembled system prompt:")
print("─" * 60)
print(assembled)
print("─" * 60)
print(f"\nTotal prompt length: {len(assembled)} characters "
      f"(≈ {len(assembled)//4} tokens)")

# Verify structure
assert "## Lawyer Profile" in assembled, "SOUL section missing"
assert "## Active Skill" in assembled,   "Skill section missing"
assert "## Instructions" in assembled,   "Base section missing"
print("\nAll three sections present ✓")

# Demo: truncation kicks in
long_skill = "x" * 3000
assembled_long = build_system_prompt("", long_skill, "Draft something.")
skill_section = assembled_long.split("## Active Skill\n")[1].split("## Instructions")[0]
assert skill_section.endswith("..."), "Truncation marker missing"
print("Truncation at 2000 chars verified ✓")

# Demo: graceful degradation — no skill, no soul
minimal = build_system_prompt("", "", "Draft a legal notice.")
print(f"\nMinimal prompt (no soul, no skill): {minimal!r}")

# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
print()
print("── PAUSE AND THINK ──────────────────────────────────────────────────")
questions = [
    "The function puts base instructions LAST because of the LLM's recency "
    "bias in attention.  Test this claim: swap soul and base in a real draft "
    "call and compare output quality.  What did you find?",

    "build_system_prompt() accepts plain strings.  In production, SOUL.md "
    "and the skill body are read from disk.  Where in the call chain would "
    "you add caching so the file is not re-read on every request?",

    "The 2000-char skill limit is arbitrary.  How would you measure the "
    "actual token count instead of using the character / 4 approximation?  "
    "(Hint: the Anthropic SDK has a token-counting method.)",

    "What should happen if SOUL.md contains personally identifiable "
    "information (bar number, phone, address) and the assembled prompt is "
    "logged to a file?  How would you redact it?",

    "lexagent/nodes/draft.py calls build_system_prompt() and passes the "
    "result to the LLM.  Sketch the function signature and the two lines of "
    "code in the draft node that call SkillLoader and build_system_prompt().",
]
for i, q in enumerate(questions, 1):
    print(f"\n  Q{i}. {q}")
print()
