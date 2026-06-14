import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from themis.nodes.chamber import run

SAMPLE_STATE = {
    "draft_output": "The accused issued a cheque for Rs 5 lakh. It was dishonoured on 10 Jan 2025.",
    "active_skill": "S.138 NI Act complaint",
    "jurisdiction": "CJM, Gurugram",
    "matter_type": "s138_complaint",
    "chamber_enabled": True,
    "messages": [],
    "error": None,
}

@pytest.mark.asyncio
async def test_chamber_returns_three_fields():
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=[
        MagicMock(content="1. Missing notice date\n2. No verification clause"),
        MagicMock(content="1. VALID\n2. WRONG"),
        MagicMock(content="ACTION: Add notice date. RISK LEVEL: MEDIUM"),
    ])
    with patch("themis.nodes.chamber._get_llm", return_value=mock_llm):
        result = await run(SAMPLE_STATE)
    assert "chamber_issues" in result
    assert "chamber_pushback" in result
    assert "chamber_review" in result

@pytest.mark.asyncio
async def test_chamber_skipped_when_disabled():
    state = {**SAMPLE_STATE, "chamber_enabled": False}
    result = await run(state)
    assert result == {}

@pytest.mark.asyncio
async def test_chamber_captures_llm_error():
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("quota exceeded"))
    with patch("themis.nodes.chamber._get_llm", return_value=mock_llm):
        result = await run(SAMPLE_STATE)
    assert "error" in result
