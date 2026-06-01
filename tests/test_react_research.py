"""
Tests for the ReAct research node (lexagent/nodes/react_research.py).

Covers:
- Citation enforcement gate: pass / drop logic for every required field
- _fetch_with_fallback: cache hit path
- run(): stub Kanoon + disabled Tavily returns gated findings in state
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lexagent.nodes.react_research import (
    _enforce_citation_gate,
    _load_cached,
    _save_cached,
    run,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _good_finding(**overrides) -> dict:
    """Minimal finding that passes the citation gate."""
    base = {
        "title": "Lakshmi Travels v State of Maharashtra",
        "url": "https://indiankanoon.org/doc/12345/",
        "full_text": "The court held that the cheque was dishonoured...",
        "doc_excerpt": "The court held that the cheque was dishonoured...",
        "citation": "AIR 2023 SC 100",
        "docsource": "Supreme Court of India",
        "snippet": "Section 138 NI Act",
    }
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# Citation gate — passing cases
# ---------------------------------------------------------------------------

class TestEnforceCitationGate:
    def test_good_finding_passes(self):
        passed, dropped = _enforce_citation_gate([_good_finding()])
        assert len(passed) == 1
        assert len(dropped) == 0

    def test_docsource_promoted_to_citation(self):
        f = _good_finding(citation="", docsource="Delhi High Court")
        passed, _ = _enforce_citation_gate([f])
        assert passed[0]["citation"] == "Delhi High Court"

    def test_full_text_becomes_doc_excerpt_when_excerpt_absent(self):
        f = _good_finding(doc_excerpt="")
        f["full_text"] = "A" * 600
        passed, _ = _enforce_citation_gate([f])
        assert len(passed[0]["doc_excerpt"]) == 500

    def test_multiple_good_findings_all_pass(self):
        findings = [_good_finding(title=f"Case {i}", url=f"https://ik.org/doc/{i}/") for i in range(5)]
        passed, dropped = _enforce_citation_gate(findings)
        assert len(passed) == 5
        assert len(dropped) == 0

    # --- Drop cases ---

    def test_missing_title_dropped(self):
        _, dropped = _enforce_citation_gate([_good_finding(title="")])
        assert len(dropped) == 1

    def test_missing_url_dropped(self):
        _, dropped = _enforce_citation_gate([_good_finding(url="")])
        assert len(dropped) == 1

    def test_missing_text_and_excerpt_dropped(self):
        f = _good_finding(full_text="", doc_excerpt="")
        _, dropped = _enforce_citation_gate([f])
        assert len(dropped) == 1

    def test_missing_citation_and_docsource_dropped(self):
        f = _good_finding(citation="", docsource="")
        _, dropped = _enforce_citation_gate([f])
        assert len(dropped) == 1

    def test_mixed_batch_split_correctly(self):
        good = _good_finding()
        bad = _good_finding(title="")
        passed, dropped = _enforce_citation_gate([good, bad])
        assert len(passed) == 1
        assert len(dropped) == 1

    def test_empty_list_returns_empty(self):
        passed, dropped = _enforce_citation_gate([])
        assert passed == []
        assert dropped == []


# ---------------------------------------------------------------------------
# Judgment cache helpers
# ---------------------------------------------------------------------------

class TestJudgmentCache:
    def test_save_and_load_roundtrip(self, tmp_path):
        text = "Full judgment text here."
        _save_cached(99999, text, str(tmp_path))
        loaded = _load_cached(99999, str(tmp_path))
        assert loaded == text

    def test_load_returns_none_for_missing(self, tmp_path):
        assert _load_cached(00000, str(tmp_path)) is None

    def test_cache_path_uses_docid_as_filename(self, tmp_path):
        _save_cached("abc123", "text", str(tmp_path))
        assert (tmp_path / "abc123.txt").exists()


# ---------------------------------------------------------------------------
# run() node — integration with mocked backends
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_returns_research_findings_key():
    """run() must always return research_findings (may be empty list)."""
    state = {
        "matter_type": "cheque bounce",
        "purpose": "Section 138 NI Act complaint",
        "jurisdiction": "Delhi High Court",
        "user_input": "cheque bounce",
    }
    mock_lim = MagicMock(return_value={"risk": "low", "analysis": "within limitation"})
    with (
        patch("lexagent.nodes.react_research._run_kanoon_search", new_callable=AsyncMock, return_value=[]),
        patch("lexagent.nodes.react_research._run_tavily_search", new_callable=AsyncMock, return_value=[]),
        patch("lexagent.tools.registry.ToolRegistry.get", return_value=mock_lim),
        patch("lexagent.tools.limitation", create=True),
    ):
        result = await run(state)

    assert "research_findings" in result
    assert isinstance(result["research_findings"], list)


@pytest.mark.asyncio
async def test_run_citation_gate_drops_bad_findings():
    """Findings missing required fields are in citation_gate_dropped, not research_findings."""
    bad = {"title": "", "url": "https://ik.org/doc/1/", "full_text": "text", "citation": "AIR 2023 SC 1"}
    good = _good_finding()

    state = {"matter_type": "cheque", "user_input": "cheque bounce"}
    mock_lim = MagicMock(return_value={"risk": "low"})
    mock_cfg = MagicMock(enable_kanoon=True, kanoon_api_key="test-key", tavily_enabled=False, tavily_api_key=None)
    with (
        patch("lexagent.nodes.react_research.LexConfig", return_value=mock_cfg),
        patch("lexagent.nodes.react_research._run_kanoon_search", new_callable=AsyncMock, return_value=[bad, good]),
        patch("lexagent.nodes.react_research._run_tavily_search", new_callable=AsyncMock, return_value=[]),
        patch("lexagent.tools.registry.ToolRegistry.get", return_value=mock_lim),
        patch("lexagent.tools.limitation", create=True),
    ):
        result = await run(state)

    assert len(result["research_findings"]) == 1
    assert result["research_findings"][0]["title"] == good["title"]
    dropped = result.get("citation_gate_dropped") or []
    assert len(dropped) == 1


@pytest.mark.asyncio
async def test_run_includes_agent_trace():
    """run() must include research_agent_trace with step entries."""
    state = {"user_input": "landlord tenant eviction"}
    mock_lim = MagicMock(return_value={"risk": "low"})
    mock_cfg = MagicMock(enable_kanoon=True, kanoon_api_key="test-key", tavily_enabled=False, tavily_api_key=None)
    with (
        patch("lexagent.nodes.react_research.LexConfig", return_value=mock_cfg),
        patch("lexagent.nodes.react_research._run_kanoon_search", new_callable=AsyncMock, return_value=[]),
        patch("lexagent.nodes.react_research._run_tavily_search", new_callable=AsyncMock, return_value=[]),
        patch("lexagent.tools.registry.ToolRegistry.get", return_value=mock_lim),
        patch("lexagent.tools.limitation", create=True),
    ):
        result = await run(state)

    trace = result.get("research_agent_trace")
    assert trace is not None
    assert any(step["step"] == "kanoon_api_search" for step in trace)
    assert any(step["step"] == "tavily_search" for step in trace)


@pytest.mark.asyncio
async def test_run_exception_returns_error_key():
    """Unhandled exception in run() must return {'error': ...}, not raise."""
    state = {"user_input": "test"}
    mock_cfg = MagicMock(enable_kanoon=True, kanoon_api_key="test-key", tavily_enabled=False, tavily_api_key=None)
    with (
        patch("lexagent.nodes.react_research.LexConfig", return_value=mock_cfg),
        patch("lexagent.nodes.react_research._run_kanoon_search", side_effect=RuntimeError("boom")),
    ):
        result = await run(state)
    assert "error" in result
    assert "boom" in result["error"]
