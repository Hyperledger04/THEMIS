"""
02 — Per-Matter Memory: The Running Case File
==============================================
Every legal matter has a life that spans weeks or months.
The lawyer sends a brief today, asks for a revision next week,
wants a rejoinder after the reply is filed.

LexAgent needs to remember what happened on each matter.
This is per-matter memory: one MEMORY.md file per case.

Directory structure:
  ~/.lexagent/
    SOUL.md                          ← lawyer-wide (Phase 2, lesson 01)
    matters/
      sharma-v-state-2024/
        MEMORY.md                    ← per-matter running log ← this lesson
        state.json                   ← last full LexState snapshot
      ibc-abc-corp-2025/
        MEMORY.md
        state.json

python 02_matter_memory.py
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# ── SECTION 1: MATTER IDs — HUMAN-READABLE SLUGS ────────────────────────────
#
# A matter ID is a slug: lowercase, hyphens, no spaces, no special chars.
# WHY slugs and not UUIDs (like "d4f8a3b1-...")?
#   - A lawyer needs to SAY the matter ID to find their files.
#   - "sharma-v-state-2024" is memorable and scannable in a directory listing.
#   - UUIDs are opaque — you can't tell what matter it is without a lookup.
#
# WHY not use the case number? Case numbers change (court re-registers),
# are long and awkward, and aren't known at matter-creation time.

print("── SECTION 1: Matter IDs ────────────────────────────────────────────────")
print()

def slugify(text: str) -> str:
    """
    Convert a matter name to a filesystem-safe slug.
    'Sharma v. State of Maharashtra (2024)' → 'sharma-v-state-of-maharashtra-2024'
    """
    import re
    # Lowercase everything
    slug = text.lower()
    # Replace anything that isn't alphanumeric with a hyphen
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    return slug

examples = [
    "Sharma v. State of Maharashtra (2024)",
    "ABC Corp Insolvency — NCLT Mumbai 2025",
    "Writ Petition: Right to Privacy",
]
for ex in examples:
    print(f"  {ex!r}")
    print(f"  → {slugify(ex)!r}")
    print()

# ── SECTION 2: WHY MEMORY.md IS APPEND-ONLY ─────────────────────────────────
#
# Legal matters need an audit trail.
# If the agent overwrote MEMORY.md on every run, you would lose:
#   - Earlier drafts and the reasoning behind them
#   - When a particular argument was added or removed
#   - Whether a citation was present before the rejoinder
#
# WRONG: overwrite on every run
# WRONG_CODE: memory_path.write_text(new_content)
#
# RIGHT: append a timestamped entry
# Each run adds a new section. The file grows. History is preserved.
# WHY: Legal records are not mutable. This mirrors how physical files work.

print("── SECTION 2: Append-only memory ──────────────────────────────────────")
print()
print("  WRONG: memory_path.write_text(new_content)  # destroys history")
print("  RIGHT: append a timestamped entry each run")
print()

# ── SECTION 3: THE DIRECTORY STRUCTURE ──────────────────────────────────────

# We'll work in a temp directory so this demo is safe and self-contained.
BASE_DIR = Path(tempfile.mkdtemp()) / ".lexagent"
MATTERS_DIR = BASE_DIR / "matters"

print("── SECTION 3: Creating the directory structure ─────────────────────────")
print()

def get_matter_dir(matter_id: str, base_dir: Path = MATTERS_DIR) -> Path:
    """
    Return the directory for a specific matter.
    Creates it if it doesn't exist.
    WHY exist_ok=True? Multiple agents/CLI calls may try to create it.
    """
    matter_dir = base_dir / matter_id
    matter_dir.mkdir(parents=True, exist_ok=True)
    return matter_dir

matter_id = "sharma-v-state-2024"
matter_dir = get_matter_dir(matter_id)
print(f"  Matter directory : {matter_dir}")
print(f"  Exists?          : {matter_dir.exists()}")
print()

# ── SECTION 4: APPENDING TO MEMORY.md ───────────────────────────────────────

print("── SECTION 4: append_to_matter_memory() ────────────────────────────────")
print()

def append_to_matter_memory(
    matter_id: str,
    content: str,
    base_dir: Path = MATTERS_DIR,
) -> Path:
    """
    Append a timestamped entry to the matter's MEMORY.md.

    Each entry looks like:

      ## 2024-07-15T14:32:01
      [content here]

    WHY ISO 8601 timestamps? They sort lexicographically.
    `ls -t` and FTS search both work correctly with this format.

    Returns the Path to the MEMORY.md file.
    """
    matter_dir = get_matter_dir(matter_id, base_dir)
    memory_path = matter_dir / "MEMORY.md"

    timestamp = datetime.now().isoformat(timespec="seconds")

    # Build the entry
    entry = f"\n## {timestamp}\n\n{content.strip()}\n"

    # WHY "a" mode (append) not "w" mode (write)?
    # "w" would overwrite the entire file. "a" adds to the end.
    # The audit trail is append-only.
    with memory_path.open("a", encoding="utf-8") as f:
        # If this is the first entry, write a header first
        if memory_path.stat().st_size == 0:
            f.write(f"# Matter Memory: {matter_id}\n")
        f.write(entry)

    return memory_path


# Simulate three runs of the agent on the same matter
entries = [
    "Initial brief received. Matter type: writ petition. Jurisdiction: Bombay HC.\nParties: Sharma (petitioner) v. State of Maharashtra (respondent).",
    "Draft completed. 12 paragraphs. Cited: Maneka Gandhi (1978), Olga Tellis (1985).\nLawyer requested addition of Section 14 SARFAESI argument.",
    "Revised draft sent. Added SARFAESI ground. Limitation analysis: within 3 years of cause of action.",
]

for entry in entries:
    path = append_to_matter_memory(matter_id, entry)

print(f"  MEMORY.md content after 3 runs:")
print()
memory_content = path.read_text()
print("  " + memory_content.replace("\n", "\n  "))
print()

# ── SECTION 5: READING MATTER MEMORY ────────────────────────────────────────

print("── SECTION 5: load_matter_memory() ─────────────────────────────────────")
print()

def load_matter_memory(
    matter_id: str,
    base_dir: Path = MATTERS_DIR,
) -> str:
    """
    Load the full MEMORY.md for a matter.
    Returns empty string if the file doesn't exist (first run for this matter).
    WHY empty string not None? Callers can safely do `if memory:` or
    concatenate with other strings without None-checks.
    """
    matter_dir = base_dir / matter_id
    memory_path = matter_dir / "MEMORY.md"

    if not memory_path.exists():
        return ""
    return memory_path.read_text(encoding="utf-8")


loaded = load_matter_memory(matter_id)
print(f"  Loaded {len(loaded)} characters")
print(f"  Lines: {len(loaded.splitlines())}")
print()

# ── SECTION 6: STATE SNAPSHOT — state.json ──────────────────────────────────
#
# MEMORY.md is human-readable prose. state.json is the machine-readable twin.
# After every graph.astream() completes, we save the full LexState as JSON.
# WHY both?
#   - MEMORY.md: a lawyer can read it, audit it, share it with a colleague
#   - state.json: the agent can reload it and continue exactly where it left off
#
# WHY save state as JSON not pickle?
#   - JSON is human-readable and git-diffs well
#   - pickle is Python-version-specific and can execute arbitrary code on load
#   - Legal data must be inspectable; binary formats are not acceptable

print("── SECTION 6: State snapshots — state.json ─────────────────────────────")
print()

def save_state_snapshot(
    matter_id: str,
    state: dict[str, Any],
    base_dir: Path = MATTERS_DIR,
) -> Path:
    """
    Overwrite state.json with the latest LexState after a graph run.
    WHY overwrite (not append) here?
      - MEMORY.md is the audit trail (human prose, append-only).
      - state.json is a hot-reload checkpoint (machine state, latest only).
      - Keeping every state version would bloat disk with huge JSON files.
    """
    matter_dir = get_matter_dir(matter_id, base_dir)
    snapshot_path = matter_dir / "state.json"

    # WHY indent=2? Makes the JSON readable in a text editor and diff-able in git.
    # WHY default=str? Some state values (Path, datetime) aren't JSON-serialisable.
    snapshot_path.write_text(
        json.dumps(state, indent=2, default=str),
        encoding="utf-8",
    )
    return snapshot_path


# Simulate saving a state snapshot
fake_state = {
    "matter_id": matter_id,
    "matter_type": "writ petition",
    "parties": {"petitioner": "Sharma", "respondent": "State of Maharashtra"},
    "jurisdiction": "Bombay High Court",
    "intake_complete": True,
    "draft_output": "IN THE HIGH COURT OF JUDICATURE AT BOMBAY...",
    "citations_verified": True,
    "created_at": datetime.now().isoformat(),
}

snapshot_path = save_state_snapshot(matter_id, fake_state)
print(f"  Saved state.json: {snapshot_path}")
print(f"  File size: {snapshot_path.stat().st_size} bytes")
print()
print("  state.json preview (first 300 chars):")
raw = snapshot_path.read_text()
print("  " + raw[:300].replace("\n", "\n  "))
print()

# ── SECTION 7: SOUL.md vs MATTER MEMORY — THE KEY DIFFERENCE ────────────────

print("── SECTION 7: SOUL.md vs Matter Memory ─────────────────────────────────")
print()
print("  SOUL.md                          | MEMORY.md")
print("  ─────────────────────────────────────────────────────")
print("  One file per LAWYER              | One file per MATTER")
print("  Lawyer-wide preferences          | Case-specific history")
print("  Written by lawyer (via setup)    | Written by agent (auto-appended)")
print("  Rarely changes                   | Grows on every run")
print("  Injected into EVERY prompt       | Injected for THIS matter only")
print("  ~/.lexagent/SOUL.md              | ~/.lexagent/matters/{id}/MEMORY.md")
print()
print("  Combined: the agent knows who the lawyer is (SOUL) AND")
print("  what happened on this specific matter (MEMORY.md).")
print()

# ── PAUSE AND THINK ──────────────────────────────────────────────────────────

print("""
── PAUSE AND THINK ─────────────────────────────────────────────────────────

Open lexagent/memory/matter_memory.py in your editor and answer these:

1. The real append_to_matter_memory() also updates a "last_modified" field.
   Why would the agent need to know WHEN memory was last written?
   Hint: think about stale memory from a matter that is 2 years old.

2. load_matter_memory() returns the full file as one string.
   For a matter with 50 runs, MEMORY.md could be 20,000 tokens.
   How should the agent handle a MEMORY.md that exceeds the context window?
   What strategies exist? (Summarisation? Last-N entries only?)

3. state.json is overwritten on every run. What could go wrong if two
   CLI processes run simultaneously on the same matter?
   Look at save_state_snapshot — is there any locking mechanism?

4. Why is MEMORY.md stored in the FILESYSTEM rather than the SQLite
   sessions.db that you will study in lesson 03?
   What is the tradeoff? (Think: git, grep, sharing with colleagues.)

5. Open lexagent/nodes/intake.py. At which point in the intake node
   does the agent load matter_memory? Before or after the LLM call?
   Why does the order matter?
""")
