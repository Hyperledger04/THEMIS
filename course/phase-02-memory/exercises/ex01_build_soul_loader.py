"""
Phase 02 — Memory | Exercise 01: Build the Soul Loader
=======================================================
Your task: implement three functions that load SOUL.md and inject it
into LangGraph message history.

This mirrors what lexagent/memory/soul.py does in the real codebase.

Instructions:
1. Read the SAMPLE_SOUL_MD and EXPECTED outputs below carefully.
2. Implement each TODO function.
3. Run this file — all three assertions at the bottom must pass.

Run:
    python course/phase-02-memory/exercises/ex01_build_soul_loader.py
"""

from pathlib import Path

# ── SECTION 1: THE SOUL FORMAT ─────────────────────────────────────────────

# SOUL.md uses YAML frontmatter (between --- delimiters) followed by free text.
# The soul loader does NOT parse the YAML — it treats the whole file as a
# plain string and injects it into the system prompt verbatim.
# WHY: Lawyers write SOUL.md in a text editor; complex parsing would break
# on minor formatting variations.

SAMPLE_SOUL_MD = """\
---
name: Arjun Sharma
bar_number: BAR/DEL/2015/1234
court: Delhi High Court
style: Formal and precise. Cite Supreme Court first.
preferences:
  - Always check limitation period first
  - Prefer fundamental rights arguments in writ matters
---
"""

# ── SECTION 2: IMPLEMENT THESE THREE FUNCTIONS ─────────────────────────────

def load_soul(soul_path: Path) -> str:
    """Return the full content of SOUL.md, or an empty string if missing.

    Args:
        soul_path: absolute Path to the SOUL.md file

    Returns:
        File contents as a string, or "" if the file does not exist.

    Hint: Path.exists() and Path.read_text(encoding="utf-8")
    """
    # TODO: implement
    pass


def format_for_prompt(soul_text: str) -> str:
    """Wrap soul content in a Markdown section header for the system prompt.

    Args:
        soul_text: raw string from load_soul()

    Returns:
        "## Lawyer Profile\n" + soul_text   if soul_text is non-empty
        ""                                   if soul_text is empty/None

    Hint: use a simple if/else — no regex needed.
    """
    # TODO: implement
    pass


def inject_into_messages(soul_text: str, messages: list) -> list:
    """Prepend the soul as a system message if not already present.

    Rules:
    - If soul_text is empty, return messages unchanged.
    - If messages[0] is already a system message (role == "system"),
      return messages unchanged (don't double-inject).
    - Otherwise, prepend {"role": "system", "content": format_for_prompt(soul_text)}.

    Args:
        soul_text: raw soul string
        messages:  list of {"role": ..., "content": ...} dicts

    Returns:
        New list with soul prepended (or original list if no injection needed).

    Hint: return [new_msg] + messages  to prepend without mutating the input.
    """
    # TODO: implement
    pass


# ── SECTION 3: SELF-TEST ───────────────────────────────────────────────────

def run_tests() -> None:
    import tempfile, os

    # Test 1: load_soul — file exists
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(SAMPLE_SOUL_MD)
        tmp_path = Path(f.name)

    loaded = load_soul(tmp_path)
    assert loaded == SAMPLE_SOUL_MD, f"load_soul failed:\n{repr(loaded)}"
    os.unlink(tmp_path)

    # Test 2: load_soul — file missing
    missing = load_soul(Path("/tmp/does_not_exist_xyz.md"))
    assert missing == "", f"load_soul should return '' for missing file, got {repr(missing)}"

    # Test 3: format_for_prompt — with content
    formatted = format_for_prompt(SAMPLE_SOUL_MD)
    assert formatted.startswith("## Lawyer Profile\n"), (
        f"format_for_prompt should start with header, got: {repr(formatted[:40])}"
    )
    assert SAMPLE_SOUL_MD in formatted, "format_for_prompt should include original text"

    # Test 4: format_for_prompt — empty input
    assert format_for_prompt("") == "", "format_for_prompt('') should return ''"
    assert format_for_prompt(None) == "", "format_for_prompt(None) should return ''"  # type: ignore[arg-type]

    # Test 5: inject_into_messages — normal injection
    messages = [{"role": "user", "content": "Draft a writ petition"}]
    result = inject_into_messages(SAMPLE_SOUL_MD, messages)
    assert result[0]["role"] == "system", "First message should be system after injection"
    assert "Lawyer Profile" in result[0]["content"], "Injected message should contain header"
    assert result[1] == messages[0], "Original user message should still be present"

    # Test 6: inject_into_messages — do not double-inject
    already_has_system = [
        {"role": "system", "content": "existing system prompt"},
        {"role": "user", "content": "Draft a writ petition"},
    ]
    result2 = inject_into_messages(SAMPLE_SOUL_MD, already_has_system)
    assert result2[0]["content"] == "existing system prompt", (
        "Should not overwrite existing system message"
    )

    # Test 7: inject_into_messages — empty soul, no injection
    result3 = inject_into_messages("", messages)
    assert result3 == messages, "Empty soul should not modify messages"

    print("All 7 assertions passed. Well done!")


if __name__ == "__main__":
    run_tests()


# ── PAUSE AND THINK ───────────────────────────────────────────────────────
#
# 1. Open lexagent/memory/soul.py — how does the real implementation
#    handle the case where SOUL.md contains malformed YAML frontmatter?
#    Does it parse YAML at all, or treat it as plain text?
#
# 2. Why does inject_into_messages check messages[0]["role"] == "system"
#    instead of scanning all messages for a system role?
#    What assumption does this make about message ordering in LangGraph?
#
# 3. The function returns [new_msg] + messages rather than messages.insert(0, …).
#    What is the benefit of the non-mutating approach in a LangGraph node
#    that returns only changed keys to the shared state?
