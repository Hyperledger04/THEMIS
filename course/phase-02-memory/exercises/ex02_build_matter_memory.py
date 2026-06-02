"""
Phase 02 — Memory | Exercise 02: Build Matter Memory
=====================================================
Your task: implement three functions that manage per-matter MEMORY.md files
and JSON state snapshots on disk.

This mirrors what lexagent/memory/matter_memory.py does in the real codebase.

Instructions:
1. Read the expected directory layout below carefully.
2. Implement each TODO function.
3. Run this file — all assertions at the bottom must pass and clean up after.

Run:
    python course/phase-02-memory/exercises/ex02_build_matter_memory.py

Expected on-disk layout after use:
    <base_dir>/
    └── sharma-v-state-2024/
        ├── MEMORY.md     ← append_to_matter_memory writes here
        └── state.json    ← save_state_snapshot writes here
"""

import json
from datetime import datetime
from pathlib import Path

# ── SECTION 1: THE MATTER DIRECTORY PATTERN ────────────────────────────────

# Each legal matter gets its own subdirectory inside ~/.lexagent/matters/.
# This mirrors how lawyers keep a physical file per matter.
#
# MEMORY.md is an append-only log:
#   [2025-01-15T14:32:00]
#   Research finding: AIR 1978 SC 597 supports petitioner's standing.
#
#   [2025-01-15T14:45:00]
#   Draft complete. High-risk clause flagged at paragraph 4.
#
# WHY append-only: never overwrite research findings. If the agent makes
# a mistake, the full history lets the lawyer retrace what happened.

SAMPLE_MATTER_ID = "sharma-v-state-2024"


# ── SECTION 2: IMPLEMENT THESE THREE FUNCTIONS ─────────────────────────────

def append_to_matter_memory(matter_id: str, content: str, base_dir: Path) -> None:
    """Append a timestamped entry to the matter's MEMORY.md.

    Creates the matter directory and MEMORY.md if they do not exist.
    Each entry follows this format (note the blank line after content):

        [2025-01-15T14:32:00]
        <content>

    Args:
        matter_id: unique matter identifier, e.g. "sharma-v-state-2024"
        content:   the text to append (can be multi-line)
        base_dir:  parent directory, e.g. Path("/tmp/matters")

    Hint:
        matter_dir = base_dir / matter_id
        matter_dir.mkdir(parents=True, exist_ok=True)
        memory_file = matter_dir / "MEMORY.md"
        Use open(memory_file, "a", encoding="utf-8") to append.
        datetime.now().isoformat(timespec="seconds") gives a clean timestamp.
    """
    # TODO: implement
    pass


def load_matter_memory(matter_id: str, base_dir: Path) -> str:
    """Return the full content of the matter's MEMORY.md, or "" if missing.

    Args:
        matter_id: unique matter identifier
        base_dir:  parent directory

    Returns:
        File content as a string, or "" if the file does not exist.
    """
    # TODO: implement
    pass


def save_state_snapshot(matter_id: str, state: dict, base_dir: Path) -> None:
    """Save the LexAgent state dict as state.json inside the matter directory.

    Creates the matter directory if it does not exist.
    Overwrites any existing state.json — this is always the latest snapshot.

    Args:
        matter_id: unique matter identifier
        state:     dict of LexAgent state fields to persist
        base_dir:  parent directory

    Hint:
        Use json.dumps(state, indent=2, ensure_ascii=False) for readable output.
        Write with Path.write_text(encoding="utf-8").
    """
    # TODO: implement
    pass


# ── SECTION 3: SELF-TEST ───────────────────────────────────────────────────

def run_tests() -> None:
    import tempfile, shutil

    base_dir = Path(tempfile.mkdtemp(prefix="lexagent_ex02_"))

    try:
        # Test 1: append creates directory and file
        append_to_matter_memory(SAMPLE_MATTER_ID, "First research note.", base_dir)
        memory_file = base_dir / SAMPLE_MATTER_ID / "MEMORY.md"
        assert memory_file.exists(), "MEMORY.md should be created by first append"

        content_after_first = memory_file.read_text(encoding="utf-8")
        assert "First research note." in content_after_first, (
            "MEMORY.md should contain the appended content"
        )
        assert "[" in content_after_first, (
            "MEMORY.md entry should contain a timestamp in [...]"
        )

        # Test 2: append is additive
        append_to_matter_memory(SAMPLE_MATTER_ID, "Second note: limitation check done.", base_dir)
        content_after_second = memory_file.read_text(encoding="utf-8")
        assert "First research note." in content_after_second, (
            "First note should still be present after second append"
        )
        assert "Second note" in content_after_second, (
            "Second note should be present"
        )

        # Test 3: load_matter_memory returns current content
        loaded = load_matter_memory(SAMPLE_MATTER_ID, base_dir)
        assert "First research note." in loaded, "load should return all appended content"
        assert "Second note" in loaded, "load should return second entry too"

        # Test 4: load_matter_memory — missing matter returns ""
        missing = load_matter_memory("nonexistent-matter-xyz", base_dir)
        assert missing == "", f"Missing matter should return '', got {repr(missing)}"

        # Test 5: save_state_snapshot creates state.json
        sample_state = {
            "matter_id": SAMPLE_MATTER_ID,
            "matter_type": "writ",
            "jurisdiction": "Delhi High Court",
            "intake_complete": True,
        }
        save_state_snapshot(SAMPLE_MATTER_ID, sample_state, base_dir)
        state_file = base_dir / SAMPLE_MATTER_ID / "state.json"
        assert state_file.exists(), "state.json should be created by save_state_snapshot"

        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["matter_type"] == "writ", (
            f"Saved state should preserve matter_type, got: {saved.get('matter_type')}"
        )
        assert saved["intake_complete"] is True, "Booleans should be preserved in JSON"

        # Test 6: save_state_snapshot overwrites on second call
        updated_state = {**sample_state, "draft_output": "Draft text goes here."}
        save_state_snapshot(SAMPLE_MATTER_ID, updated_state, base_dir)
        saved2 = json.loads(state_file.read_text(encoding="utf-8"))
        assert "draft_output" in saved2, "Second save should overwrite with new keys"

        print("All 6 assertions passed. Well done!")

    finally:
        shutil.rmtree(base_dir)   # clean up temp dir regardless of failures


if __name__ == "__main__":
    run_tests()


# ── PAUSE AND THINK ───────────────────────────────────────────────────────
#
# 1. Open lexagent/memory/matter_memory.py — does the real implementation
#    use append mode ("a") or does it read-then-write? What are the
#    trade-offs of each approach if two processes write simultaneously?
#
# 2. save_state_snapshot overwrites state.json on every call, while
#    MEMORY.md is append-only. Why is it safe to overwrite state.json
#    but not MEMORY.md?
#
# 3. The test uses shutil.rmtree in a finally block — why is this important
#    even though we are only writing to /tmp? What would happen if the
#    test directory accumulated across many test runs?
