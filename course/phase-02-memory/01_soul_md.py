"""
01 — SOUL.md: The Lawyer's Persistent Identity
===============================================
Every time LexAgent runs, it needs to know WHO it is working for.
Is this a family court lawyer in Chennai who prefers terse language?
Or a High Court silk in Delhi who cites constitutional theory?

SOUL.md is the answer. It is a plain text file that lives at:
  ~/.lexagent/SOUL.md

The agent reads it on every run and injects it into the system prompt.
The lawyer controls the agent's personality by editing a text file —
no code, no deployment, no API call.

python 01_soul_md.py
"""

from pathlib import Path
from datetime import datetime
import tempfile
import os

# ── SECTION 1: WHERE SOUL.md LIVES ──────────────────────────────────────────
#
# Path.home() returns the current user's home directory as a Path object.
# On Mac:    /Users/brahm
# On Linux:  /home/brahm
# On Win:    C:\Users\brahm
#
# We always store LexAgent data inside ~/.lexagent/
# WHY a hidden dot-directory? Convention on Unix: user config lives in ~/.<name>
# Examples: ~/.ssh/, ~/.config/, ~/.bashrc

LEXAGENT_DIR = Path.home() / ".lexagent"
SOUL_PATH = LEXAGENT_DIR / "SOUL.md"

print("── SECTION 1: Where SOUL.md lives ─────────────────────────────────────")
print(f"  Home directory   : {Path.home()}")
print(f"  LexAgent dir     : {LEXAGENT_DIR}")
print(f"  SOUL.md path     : {SOUL_PATH}")
print(f"  SOUL.md exists?  : {SOUL_PATH.exists()}")
print()

# ── SECTION 2: WHAT SOUL.md LOOKS LIKE ──────────────────────────────────────
#
# SOUL.md uses markdown with clear sections so:
#   1. The LLM can parse and apply each section semantically
#   2. The lawyer can read and edit it in any text editor
#   3. Git can diff it — changes are reviewable
#
# There is no rigid schema. The lawyer writes what they want the agent to know.
# WHY markdown and not JSON/YAML? Lawyers write prose, not data structures.

SAMPLE_SOUL = """# Lawyer Identity

**Name:** Arjun Mehta
**Bar Number:** MH/12345/2001
**Enrollment:** Bombay High Court
**Chambers:** Mehta & Associates, Fort, Mumbai

# Practice Areas

Primary: Commercial litigation, insolvency (IBC), arbitration
Secondary: Constitutional matters, fundamental rights petitions

# Drafting Style

- Formal and precise. Avoid colloquialisms.
- Lead with the strongest legal ground, not the facts.
- Cite the full AIR/SCC citation on first mention; use short form thereafter.
  Example: "Maneka Gandhi v. Union of India, (1978) 1 SCC 248 ('Maneka Gandhi')"
- Never use passive voice in prayer clauses.
- Paragraph limit: 8 lines max. Break long arguments into numbered sub-paragraphs.

# Preferred Authorities

- Constitutional: Maneka Gandhi, Kesavananda Bharati, Minerva Mills
- Contracts: Specific Relief Act 2018 amendments
- IBC: NCLT Ahmedabad judgments on Section 7 threshold

# Notes for Agent

- Always include a "Statement of Facts" section before arguments.
- Jurisdiction is always Bombay High Court unless stated otherwise.
- Client names go in UPPERCASE on first mention only.
"""

print("── SECTION 2: A sample SOUL.md ─────────────────────────────────────────")
print(SAMPLE_SOUL)

# ── SECTION 3: THE WRONG WAY — HARDCODING LAWYER IDENTITY ───────────────────
#
# You might be tempted to put lawyer identity directly in a Python string.
# Here is why that is wrong:

print("── SECTION 3: The WRONG way ────────────────────────────────────────────")
print()

# WRONG: lawyer identity baked into source code
WRONG_SYSTEM_PROMPT = """
You are an AI assistant for Arjun Mehta, a commercial litigator at Bombay High Court.
Draft formal documents. Cite AIR citations. Use formal language.
"""
print("  WRONG: identity is in source code.")
print("  To change this, you must edit Python code, commit, redeploy.")
print("  A lawyer cannot change their own drafting style without a developer.")
print()

# ── SECTION 4: THE RIGHT WAY — LOAD FROM FILE ───────────────────────────────

print("── SECTION 4: The RIGHT way — load_soul() ──────────────────────────────")
print()

def load_soul(soul_path: Path = SOUL_PATH) -> str:
    """
    Load the lawyer's SOUL.md file.

    WHY return empty string instead of raising FileNotFoundError?
    - The agent must still work on first run, before setup is complete.
    - Graceful degradation: no SOUL.md → generic agent; SOUL.md exists → personalised.
    - The CLI's `lex setup` command creates SOUL.md on first run.
    """
    if not soul_path.exists():
        # WHY not raise? See docstring above.
        return ""
    return soul_path.read_text(encoding="utf-8")


# Test it with a temporary file (safe — doesn't touch real ~/.lexagent/SOUL.md)
with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as tmp:
    tmp.write(SAMPLE_SOUL)
    tmp_path = Path(tmp.name)

loaded = load_soul(tmp_path)
print(f"  Loaded {len(loaded)} characters from temporary SOUL.md")
print(f"  First line: {loaded.splitlines()[0]!r}")
print()

# Test graceful degradation
missing_path = Path("/tmp/does_not_exist_soul.md")
empty = load_soul(missing_path)
print(f"  Missing file → returns: {empty!r}")
print()

os.unlink(tmp_path)  # clean up

# ── SECTION 5: INJECTING SOUL INTO THE SYSTEM PROMPT ────────────────────────
#
# The system prompt is assembled fresh at the start of every graph run.
# SOUL.md content becomes the first section of that prompt.
# WHY first? LLMs pay more attention to content at the top of the prompt.
# (This is called "primacy bias" in prompt engineering.)

print("── SECTION 5: How SOUL.md shapes the system prompt ─────────────────────")
print()

BASE_INSTRUCTIONS = """You are LexAgent, an AI legal drafting assistant for Indian courts.
Your job is to draft court-ready documents with verified citations.
Always follow the lawyer's style preferences above."""

def build_system_prompt(soul_text: str, base_instructions: str) -> str:
    """
    Assemble the system prompt from its parts.

    Order matters:
      1. Lawyer identity (SOUL.md) — highest priority context
      2. Base instructions — generic agent behaviour
    """
    if soul_text.strip():
        # WHY strip()? SOUL.md might start/end with whitespace or blank lines.
        return f"# Lawyer Profile\n\n{soul_text.strip()}\n\n---\n\n{base_instructions}"
    else:
        # No SOUL.md — use generic prompt only
        return base_instructions

assembled = build_system_prompt(SAMPLE_SOUL, BASE_INSTRUCTIONS)
print("  Assembled system prompt (first 300 chars):")
print("  " + assembled[:300].replace("\n", "\n  "))
print()
print(f"  Total prompt length: {len(assembled)} characters")
print()

# ── SECTION 6: SOUL.md AND THE SETUP WIZARD ─────────────────────────────────
#
# On first run, `lex setup` creates SOUL.md by asking the lawyer questions.
# In lexagent/cli.py, the setup command does:
#   1. Ask for name, bar number, court, practice areas, style preferences
#   2. Render a SOUL.md template with those answers
#   3. Write to ~/.lexagent/SOUL.md
#   4. Open in $EDITOR so the lawyer can review/edit immediately
#
# The agent never writes to SOUL.md automatically after setup.
# WHY? SOUL.md is the lawyer's voice. Only the lawyer should change it.

print("── SECTION 6: The setup wizard writes SOUL.md once ─────────────────────")
print()

def write_soul_template(name: str, bar: str, court: str, soul_path: Path) -> None:
    """
    Write a starter SOUL.md template.
    Called once by `lex setup` — never called automatically after that.
    """
    # WHY mkdir(parents=True, exist_ok=True)?
    # parents=True creates ~/.lexagent/ if it doesn't exist.
    # exist_ok=True doesn't raise if ~/.lexagent/ already exists.
    soul_path.parent.mkdir(parents=True, exist_ok=True)

    template = f"""# Lawyer Identity

**Name:** {name}
**Bar Number:** {bar}
**Enrollment:** {court}

# Drafting Style

- [Describe your preferred tone and structure here]

# Preferred Authorities

- [List your go-to cases here]

# Notes for Agent

- [Any special instructions for the agent]
"""
    soul_path.write_text(template, encoding="utf-8")
    print(f"  Created SOUL.md at: {soul_path}")

# Demonstrate (writes to /tmp, not the real path)
demo_soul_path = Path(tempfile.mkdtemp()) / "SOUL.md"
write_soul_template("Priya Sharma", "DL/9988/2015", "Delhi High Court", demo_soul_path)
print(f"  File size: {demo_soul_path.stat().st_size} bytes")
print(f"  Preview:\n")
print("  " + demo_soul_path.read_text()[:200].replace("\n", "\n  "))
print()

# ── PAUSE AND THINK ──────────────────────────────────────────────────────────

print("""
── PAUSE AND THINK ─────────────────────────────────────────────────────────

Open lexagent/memory/soul.py in your editor and answer these questions:

1. The real load_soul() in soul.py also accepts a `config` parameter (LexConfig).
   Why does it need config, and what does it read from it?
   Hint: look at what LEXAGENT_DIR is set from in LexConfig.

2. What happens if SOUL.md contains 10,000 words?
   The LLM has a context window limit. Where in the real code is this handled?
   Search soul.py for any truncation or length check.

3. In build_system_prompt() above, SOUL.md goes BEFORE base instructions.
   Look at lexagent/prompts/ — which prompt file is the "base instructions"?
   Open it. How long is it?

4. SOUL.md is append-only in our demo (write_soul_template writes once).
   What if a lawyer wants to update their style preferences?
   Should the agent ever auto-update SOUL.md? What are the risks?

5. The real soul.py has a function called format_soul_for_prompt().
   It does more than just prepend "# Lawyer Profile\\n\\n".
   Open soul.py and describe what the extra formatting does.
""")
