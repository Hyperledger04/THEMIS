# Tests for the wisdom accumulation system.

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from lexagent.memory.wisdom import (
    _append_wisdom,
    get_relevant_wisdom,
    load_wisdom,
    wisdom_path,
)


# ---------------------------------------------------------------------------
# File path helpers
# ---------------------------------------------------------------------------

def test_wisdom_path_default():
    p = wisdom_path()
    assert p.name == "wisdom.md"
    assert "lexagent" in str(p)


def test_wisdom_path_custom(tmp_path):
    p = wisdom_path(str(tmp_path))
    assert p == tmp_path / "wisdom.md"


# ---------------------------------------------------------------------------
# load_wisdom / _append_wisdom
# ---------------------------------------------------------------------------

def test_load_wisdom_absent(tmp_path):
    assert load_wisdom(str(tmp_path)) == ""


def test_append_and_load_wisdom(tmp_path):
    entry = '- matter_type: "legal notice"\n  jurisdiction: "Delhi HC"\n  note: "Always cite Section 80 CPC."\n  date: "2025-01-01"'
    _append_wisdom(entry, str(tmp_path))
    raw = load_wisdom(str(tmp_path))
    assert "legal notice" in raw
    assert "Delhi HC" in raw


def test_append_multiple_entries(tmp_path):
    e1 = '- matter_type: "writ petition"\n  jurisdiction: "Supreme Court"\n  note: "Article 32 — fundamental right."\n  date: "2025-01-01"'
    e2 = '- matter_type: "bail application"\n  jurisdiction: "Delhi HC"\n  note: "Cite Arnesh Kumar guidelines."\n  date: "2025-02-01"'
    _append_wisdom(e1, str(tmp_path))
    _append_wisdom(e2, str(tmp_path))
    raw = load_wisdom(str(tmp_path))
    assert "writ petition" in raw
    assert "bail application" in raw


# ---------------------------------------------------------------------------
# get_relevant_wisdom
# ---------------------------------------------------------------------------

def test_get_relevant_wisdom_empty(tmp_path):
    result = get_relevant_wisdom("legal notice", "Delhi HC", str(tmp_path))
    assert result == ""


def test_get_relevant_wisdom_matching(tmp_path):
    entries = (
        '- matter_type: "legal notice"\n  jurisdiction: "Delhi HC"\n  note: "Cite Section 80 CPC for pre-suit notice."\n  date: "2025-01-01"\n'
        '- matter_type: "writ petition"\n  jurisdiction: "Supreme Court"\n  note: "Article 32 is the right."\n  date: "2025-02-01"\n'
    )
    (tmp_path / "wisdom.md").write_text(entries)
    result = get_relevant_wisdom("legal notice", "Delhi HC", str(tmp_path))
    assert "Section 80 CPC" in result
    assert "Article 32" not in result  # writ petition doesn't match


def test_get_relevant_wisdom_no_match(tmp_path):
    entries = '- matter_type: "writ petition"\n  jurisdiction: "Bombay HC"\n  note: "Check fundamental right."\n  date: "2025-01-01"\n'
    (tmp_path / "wisdom.md").write_text(entries)
    result = get_relevant_wisdom("legal notice", "Delhi HC", str(tmp_path))
    assert result == ""


def test_get_relevant_wisdom_partial_match(tmp_path):
    entries = '- matter_type: "bail application"\n  jurisdiction: "Delhi HC"\n  note: "Arnesh Kumar guidelines apply."\n  date: "2025-01-01"\n'
    (tmp_path / "wisdom.md").write_text(entries)
    # Jurisdiction matches even if matter_type doesn't
    result = get_relevant_wisdom("legal notice", "Delhi HC", str(tmp_path))
    assert "Arnesh Kumar" in result


def test_get_relevant_wisdom_max_entries(tmp_path):
    lines = []
    for i in range(10):
        lines.append(
            f'- matter_type: "legal notice"\n  jurisdiction: "Delhi HC"\n  note: "Note {i}"\n  date: "2025-01-01"\n'
        )
    (tmp_path / "wisdom.md").write_text("".join(lines))
    result = get_relevant_wisdom("legal notice", "Delhi HC", str(tmp_path), max_entries=3)
    # At most 3 entries in the output
    assert result.count("Note") <= 3


# ---------------------------------------------------------------------------
# extract_and_save_wisdom (mocked LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_and_save_wisdom(tmp_path):
    from lexagent.memory.wisdom import extract_and_save_wisdom
    from lexagent.config import LexConfig

    state = {
        "matter_type": "legal notice",
        "jurisdiction": "Delhi HC",
        "purpose": "Recovery of dues under Section 138 NI Act",
        "limitation_analysis": "Within limitation period",
        "statutes_cited": ["NI Act Section 138"],
        "draft_output": "Dear Sir, This is a legal notice under Section 138...",
    }
    cfg = LexConfig(home_dir=str(tmp_path))

    yaml_output = '- matter_type: "legal notice"\n  jurisdiction: "Delhi HC"\n  note: "Section 138 NI Act — 30-day demand notice before filing complaint."\n  date: "2025-01-01"'

    with patch("lexagent.nodes._llm.call_llm", new_callable=AsyncMock) as mock_call_llm:
        mock_call_llm.return_value = {"content": yaml_output, "tool_calls": None}

        await extract_and_save_wisdom(state, cfg)  # type: ignore[arg-type]

    raw = load_wisdom(str(tmp_path))
    assert "Section 138" in raw


@pytest.mark.asyncio
async def test_extract_and_save_wisdom_no_draft():
    """Skips extraction when draft_output is absent — must not raise."""
    from lexagent.memory.wisdom import extract_and_save_wisdom
    from lexagent.config import LexConfig

    state = {"matter_type": "legal notice"}
    cfg = LexConfig()

    # Should complete without error even though draft_output is missing
    await extract_and_save_wisdom(state, cfg)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_extract_and_save_wisdom_llm_error(tmp_path):
    """LLM failure is swallowed — wisdom file stays empty."""
    from lexagent.memory.wisdom import extract_and_save_wisdom
    from lexagent.config import LexConfig

    state = {
        "matter_type": "writ petition",
        "jurisdiction": "Supreme Court",
        "draft_output": "Draft content here...",
    }
    cfg = LexConfig(home_dir=str(tmp_path))

    with patch("lexagent.nodes._llm.call_llm", new_callable=AsyncMock) as mock_call_llm:
        mock_call_llm.side_effect = RuntimeError("API unavailable")

        await extract_and_save_wisdom(state, cfg)  # type: ignore[arg-type]

    # File absent or empty — no crash
    assert load_wisdom(str(tmp_path)) == ""
