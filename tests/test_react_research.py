"""
Tests for the ReAct research node (themis/nodes/react_research.py).

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

from themis.nodes.react_research import (
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
        patch("themis.nodes.react_research._run_kanoon_search", new_callable=AsyncMock, return_value=[]),
        patch("themis.nodes.react_research._run_tavily_search", new_callable=AsyncMock, return_value=[]),
        patch("themis.tools.registry.ToolRegistry.get", return_value=mock_lim),
        patch("themis.tools.limitation", create=True),
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
        patch("themis.nodes.react_research.LexConfig", return_value=mock_cfg),
        patch("themis.nodes.react_research._run_kanoon_search", new_callable=AsyncMock, return_value=[bad, good]),
        patch("themis.nodes.react_research._run_tavily_search", new_callable=AsyncMock, return_value=[]),
        patch("themis.tools.registry.ToolRegistry.get", return_value=mock_lim),
        patch("themis.tools.limitation", create=True),
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
        patch("themis.nodes.react_research.LexConfig", return_value=mock_cfg),
        patch("themis.nodes.react_research._run_kanoon_search", new_callable=AsyncMock, return_value=[]),
        patch("themis.nodes.react_research._run_tavily_search", new_callable=AsyncMock, return_value=[]),
        patch("themis.tools.registry.ToolRegistry.get", return_value=mock_lim),
        patch("themis.tools.limitation", create=True),
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
        patch("themis.nodes.react_research.LexConfig", return_value=mock_cfg),
        patch("themis.nodes.react_research._run_kanoon_search", side_effect=RuntimeError("boom")),
    ):
        result = await run(state)
    assert "error" in result
    assert "boom" in result["error"]


# ===========================================================================
# R1 Gate Tests — ResearcherAgent (themis/agents/researcher.py)
# Tests cover: LLM routing, ReAct loop, Qdrant sync, citation gate integration
# ===========================================================================

from themis.agents.researcher import (
    _corpus_namespace,
    _execute_queries,
    _extract_statutes,
    _plan_queries,
    _sync_judgments_to_qdrant,
)
from themis.agents.researcher import run as researcher_run


# ---------------------------------------------------------------------------
# Corpus namespace detection
# ---------------------------------------------------------------------------

class TestCorpusNamespace:
    def test_supreme_court_finding(self):
        f = {"docsource": "Supreme Court of India", "citation": "AIR 2023 SC 100"}
        assert _corpus_namespace(f) == "corpus:india_sc"

    def test_high_court_with_state(self):
        f = {"docsource": "Delhi High Court", "citation": "2022 (4) RC 55"}
        assert _corpus_namespace(f) == "corpus:india_hc:delhi"

    def test_high_court_unknown_state(self):
        f = {"docsource": "High Court of Sikkim", "citation": "2021 SCC OnLine Sikk 1"}
        assert _corpus_namespace(f) == "corpus:india_hc:unknown"

    def test_privy_council(self):
        f = {"docsource": "Privy Council", "citation": "AIR 1940 PC 1"}
        assert _corpus_namespace(f) == "corpus:privy_council"

    def test_foreign_persuasive(self):
        f = {"docsource": "Court of Appeal England and Wales", "citation": "[2020] EWCA Civ 1"}
        assert _corpus_namespace(f) == "corpus:foreign_persuasive"

    def test_regulations_circular(self):
        f = {"docsource": "SEBI circular", "citation": "SEBI/HO/2024"}
        assert _corpus_namespace(f) == "corpus:regulations"

    def test_subordinate_default(self):
        f = {"docsource": "District Court", "citation": "CC/123/2023"}
        assert _corpus_namespace(f) == "corpus:india_subordinate"


# ---------------------------------------------------------------------------
# LLM routing — _plan_queries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_queries_returns_list_with_tool_field():
    """_plan_queries must return a list of dicts with 'query' and 'tool' keys."""
    state = {
        "matter_type": "ni_act_138",
        "jurisdiction": "Delhi High Court",
        "purpose": "Section 138 NI Act complaint cheque dishonour",
    }
    llm_response = json.dumps([
        {"query": "Section 138 NI Act cheque dishonour limitation", "tool": "kanoon", "angle": "case_law"},
        {"query": "NI Act Section 138 statutory text", "tool": "tavily", "angle": "statute"},
    ])
    mock_cfg = MagicMock(researcher_model="claude-sonnet-4-6")

    with patch("themis.agents.researcher.call_llm", new_callable=AsyncMock,
               return_value={"content": llm_response, "tool_calls": None}):
        queries = await _plan_queries(state, mock_cfg)

    assert isinstance(queries, list)
    assert len(queries) >= 1
    for q in queries:
        assert "query" in q
        assert q.get("tool") in ("kanoon", "tavily")


@pytest.mark.asyncio
async def test_plan_queries_falls_back_on_llm_failure():
    """_plan_queries must return a fallback single-query list when LLM fails."""
    state = {"matter_type": "bail", "jurisdiction": "Bombay High Court", "purpose": "bail application"}
    mock_cfg = MagicMock(researcher_model="claude-sonnet-4-6")

    with patch("themis.agents.researcher.call_llm", side_effect=RuntimeError("API down")):
        queries = await _plan_queries(state, mock_cfg)

    assert len(queries) >= 1
    assert "query" in queries[0]
    assert queries[0]["tool"] == "kanoon"


@pytest.mark.asyncio
async def test_plan_queries_strips_markdown_fences():
    """LLM sometimes wraps JSON in ```json fences despite the prompt; must be stripped."""
    state = {"matter_type": "injunction", "purpose": "interim injunction"}
    llm_response = '```json\n[{"query": "injunction Order 39 CPC", "tool": "kanoon", "angle": "procedure"}]\n```'
    mock_cfg = MagicMock(researcher_model="claude-sonnet-4-6")

    with patch("themis.agents.researcher.call_llm", new_callable=AsyncMock,
               return_value={"content": llm_response, "tool_calls": None}):
        queries = await _plan_queries(state, mock_cfg)

    assert len(queries) == 1
    assert queries[0]["query"] == "injunction Order 39 CPC"


# ---------------------------------------------------------------------------
# LLM routing — _execute_queries dispatches to correct tool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_queries_routes_kanoon_and_tavily():
    """Kanoon queries go to _run_kanoon_search; Tavily queries go to _run_tavily_search."""
    queries = [
        {"query": "Section 138 NI Act SC judgment", "tool": "kanoon", "angle": "case_law"},
        {"query": "NI Act 1881 statutory text amendment", "tool": "tavily", "angle": "statute"},
    ]
    mock_cfg = MagicMock()

    kanoon_hit = _good_finding(title="Kanoon Case")
    tavily_hit = _good_finding(title="Tavily Statute", url="https://tavily.com/1/", citation="NI Act 1881")

    with (
        patch("themis.agents.researcher._run_kanoon_search", new_callable=AsyncMock, return_value=[kanoon_hit]) as mock_kanoon,
        patch("themis.agents.researcher._run_tavily_search", new_callable=AsyncMock, return_value=[tavily_hit]) as mock_tavily,
    ):
        results = await _execute_queries(queries, mock_cfg)

    mock_kanoon.assert_called_once()
    mock_tavily.assert_called_once()
    assert len(results) == 2
    titles = {r["title"] for r in results}
    assert "Kanoon Case" in titles
    assert "Tavily Statute" in titles


@pytest.mark.asyncio
async def test_execute_queries_defaults_to_kanoon_for_unknown_tool():
    """Unknown tool value falls through to Kanoon (safe default)."""
    queries = [{"query": "test query", "tool": "unknown_tool", "angle": "general"}]
    mock_cfg = MagicMock()

    with (
        patch("themis.agents.researcher._run_kanoon_search", new_callable=AsyncMock, return_value=[]) as mock_kanoon,
        patch("themis.agents.researcher._run_tavily_search", new_callable=AsyncMock, return_value=[]) as mock_tavily,
    ):
        await _execute_queries(queries, mock_cfg)

    mock_kanoon.assert_called_once()
    mock_tavily.assert_not_called()


# ---------------------------------------------------------------------------
# Qdrant sync indexing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_judgments_skipped_when_qdrant_disabled():
    """When qdrant_enabled=False, sync returns 0 without touching qdrant-client."""
    cfg = MagicMock(qdrant_enabled=False)
    findings = [_good_finding()]
    result = await _sync_judgments_to_qdrant(findings, "matter-1", "firm-1", cfg)
    assert result == 0


@pytest.mark.asyncio
async def test_sync_judgments_skipped_for_empty_findings():
    """Empty findings list returns 0 immediately."""
    cfg = MagicMock(qdrant_enabled=True)
    result = await _sync_judgments_to_qdrant([], "matter-1", "firm-1", cfg)
    assert result == 0


@pytest.mark.asyncio
async def test_sync_judgments_upserts_to_correct_namespace():
    """Findings are grouped by corpus namespace and upserted to matching collections."""
    cfg = MagicMock(
        qdrant_enabled=True,
        qdrant_url="http://localhost:6333",
        qdrant_api_key=None,
        embedding_model="all-MiniLM-L6-v2",
        embedding_dim=384,
    )
    sc_finding = _good_finding(
        title="SC Case", docsource="Supreme Court of India", citation="AIR 2023 SC 1"
    )
    hc_finding = _good_finding(
        title="HC Case",
        url="https://indiankanoon.org/doc/99999/",
        docsource="Delhi High Court",
        citation="2022 Delhi 55",
    )

    mock_client = AsyncMock()
    mock_client.get_collection.side_effect = Exception("not found")
    mock_client.create_collection = AsyncMock()
    mock_client.upsert = AsyncMock()
    mock_client.close = AsyncMock()

    mock_encoder = MagicMock()
    mock_encoder.encode.return_value = MagicMock(
        tolist=MagicMock(return_value=[[0.1] * 384, [0.2] * 384])
    )

    # WHY patch qdrant_client module directly: AsyncQdrantClient is imported lazily
    # inside _sync_judgments_to_qdrant (not at module level), so we patch the
    # upstream package rather than a module attribute.
    import sys
    fake_qdrant_mod = MagicMock()
    fake_qdrant_mod.AsyncQdrantClient.return_value = mock_client
    fake_qdrant_mod.models.VectorParams = MagicMock()
    fake_qdrant_mod.models.Distance.COSINE = "Cosine"
    fake_qdrant_mod.models.PointStruct = MagicMock(side_effect=lambda **kw: kw)

    fake_st_mod = MagicMock()
    fake_st_mod.SentenceTransformer.return_value = mock_encoder

    orig_qdrant = sys.modules.get("qdrant_client")
    orig_st = sys.modules.get("sentence_transformers")
    sys.modules["qdrant_client"] = fake_qdrant_mod
    sys.modules["sentence_transformers"] = fake_st_mod

    try:
        from themis.agents.researcher import _sync_judgments_to_qdrant
        count = await _sync_judgments_to_qdrant(
            [sc_finding, hc_finding], "matter-1", "firm-1", cfg
        )
    finally:
        if orig_qdrant is None:
            sys.modules.pop("qdrant_client", None)
        else:
            sys.modules["qdrant_client"] = orig_qdrant
        if orig_st is None:
            sys.modules.pop("sentence_transformers", None)
        else:
            sys.modules["sentence_transformers"] = orig_st

    assert mock_client.upsert.call_count == 2
    upserted_collections = {call.kwargs["collection_name"] for call in mock_client.upsert.call_args_list}
    assert "corpus:india_sc" in upserted_collections
    assert "corpus:india_hc:delhi" in upserted_collections


# ---------------------------------------------------------------------------
# Full ResearcherAgent run() — ReAct loop integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_researcher_run_returns_required_keys():
    """researcher.run() must return research_findings, statutes_cited, limitation_analysis."""
    state = {
        "matter_type": "ni_act_138",
        "jurisdiction": "Delhi",
        "purpose": "Section 138 complaint",
        "matter_id": "test-matter-1",
        "firm_id": "test-firm-1",
        "execution_plan": [{"specialist": "researcher"}, {"specialist": "drafter"}],
    }
    plan_response = json.dumps([{"query": "Section 138 NI Act", "tool": "kanoon", "angle": "case_law"}])
    eval_response = json.dumps({"sufficient": True, "confidence": 0.9, "missing_areas": [], "gap_queries": []})

    mock_cfg = MagicMock(
        researcher_model="claude-sonnet-4-6",
        react_research_max_iter=1,
        qdrant_enabled=False,
        enable_kanoon=True,
        kanoon_api_key="test-key",
        tavily_enabled=False,
        tavily_api_key=None,
    )

    with (
        patch("themis.agents.researcher.LexConfig", return_value=mock_cfg),
        patch("themis.agents.researcher.call_llm", new_callable=AsyncMock,
              side_effect=[
                  {"content": plan_response, "tool_calls": None},   # planner
                  {"content": eval_response, "tool_calls": None},   # evaluator
              ]),
        patch("themis.agents.researcher._run_kanoon_search", new_callable=AsyncMock,
              return_value=[_good_finding()]),
        patch("themis.agents.researcher._run_tavily_search", new_callable=AsyncMock, return_value=[]),
        patch("themis.agents.researcher._run_limitation_check", return_value='{"risk": "low"}'),
    ):
        result = await researcher_run(state)

    assert "research_findings" in result
    assert "statutes_cited" in result
    assert "limitation_analysis" in result
    assert isinstance(result["research_findings"], list)


@pytest.mark.asyncio
async def test_researcher_run_pops_execution_plan():
    """researcher.run() must pop itself from execution_plan for Senior Counsel coordination."""
    state = {
        "matter_id": "m1",
        "firm_id": "f1",
        "execution_plan": [{"specialist": "researcher"}, {"specialist": "drafter"}],
    }
    plan_resp = json.dumps([{"query": "test", "tool": "kanoon", "angle": "general"}])
    eval_resp = json.dumps({"sufficient": True, "confidence": 1.0, "missing_areas": [], "gap_queries": []})

    mock_cfg = MagicMock(
        researcher_model="claude-sonnet-4-6",
        react_research_max_iter=1,
        qdrant_enabled=False,
        enable_kanoon=False,
        tavily_enabled=False,
        tavily_api_key=None,
    )
    with (
        patch("themis.agents.researcher.LexConfig", return_value=mock_cfg),
        patch("themis.agents.researcher.call_llm", new_callable=AsyncMock,
              side_effect=[
                  {"content": plan_resp, "tool_calls": None},
                  {"content": eval_resp, "tool_calls": None},
              ]),
        patch("themis.agents.researcher._run_kanoon_search", new_callable=AsyncMock, return_value=[]),
        patch("themis.agents.researcher._run_tavily_search", new_callable=AsyncMock, return_value=[]),
        patch("themis.agents.researcher._run_limitation_check", return_value='{"risk": "unknown"}'),
    ):
        result = await researcher_run(state)

    remaining = result.get("execution_plan", [])
    assert len(remaining) == 1
    assert remaining[0]["specialist"] == "drafter"


@pytest.mark.asyncio
async def test_researcher_run_loops_on_insufficient_findings():
    """When evaluator returns sufficient=False, the loop runs gap queries in next iteration."""
    state = {
        "matter_id": "m2",
        "firm_id": "f1",
        "matter_type": "bail",
        "execution_plan": [{"specialist": "researcher"}],
    }
    plan_resp = json.dumps([{"query": "bail CrPC 437", "tool": "kanoon", "angle": "case_law"}])
    # First eval: not sufficient — return gap query
    eval_resp_1 = json.dumps({
        "sufficient": False,
        "confidence": 0.3,
        "missing_areas": ["limitation period not found"],
        "gap_queries": [{"query": "bail application limitation period", "tool": "kanoon", "angle": "limitation"}],
    })
    # Second eval: sufficient
    eval_resp_2 = json.dumps({"sufficient": True, "confidence": 0.85, "missing_areas": [], "gap_queries": []})

    mock_cfg = MagicMock(
        researcher_model="claude-sonnet-4-6",
        react_research_max_iter=3,
        qdrant_enabled=False,
        enable_kanoon=True,
        kanoon_api_key="test",
        tavily_enabled=False,
        tavily_api_key=None,
    )
    kanoon_calls = []

    async def fake_kanoon(query, cfg):
        kanoon_calls.append(query)
        return [_good_finding(title=f"Result for {query[:20]}")]

    with (
        patch("themis.agents.researcher.LexConfig", return_value=mock_cfg),
        patch("themis.agents.researcher.call_llm", new_callable=AsyncMock,
              side_effect=[
                  {"content": plan_resp, "tool_calls": None},    # planner iter 1
                  {"content": eval_resp_1, "tool_calls": None},  # evaluator iter 1 → not sufficient
                  {"content": eval_resp_2, "tool_calls": None},  # evaluator iter 2 → sufficient
              ]),
        patch("themis.agents.researcher._run_kanoon_search", side_effect=fake_kanoon),
        patch("themis.agents.researcher._run_tavily_search", new_callable=AsyncMock, return_value=[]),
        patch("themis.agents.researcher._run_limitation_check", return_value='{"risk": "low"}'),
    ):
        result = await researcher_run(state)

    # Two Kanoon calls: initial query + gap query
    assert len(kanoon_calls) == 2
    assert "bail CrPC 437" in kanoon_calls[0]
    assert "limitation" in kanoon_calls[1]
    # Findings from both iterations are in the result (after citation gate)
    assert len(result.get("research_findings", [])) >= 1


@pytest.mark.asyncio
async def test_researcher_run_exception_returns_error_key():
    """Unhandled exception must return {'error': ...}, not raise."""
    state = {"matter_id": "m3", "firm_id": "f1", "execution_plan": []}
    mock_cfg = MagicMock(react_research_max_iter=1, qdrant_enabled=False)

    with (
        patch("themis.agents.researcher.LexConfig", return_value=mock_cfg),
        patch("themis.agents.researcher._plan_queries", side_effect=RuntimeError("LLM exploded")),
    ):
        result = await researcher_run(state)

    assert "error" in result
    assert "LLM exploded" in result["error"]
