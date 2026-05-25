"""Tests for lexagent/tools/reranker.py"""
import pytest
from unittest.mock import AsyncMock, patch

from lexagent.config import LexConfig
from lexagent.tools.chunker import Chunk
from lexagent.tools.retriever import RetrievalResult
from lexagent.tools.reranker import LLMReranker, _parse_scores


def _make_result(text: str, score: float = 0.5) -> RetrievalResult:
    chunk = Chunk(source_doc="test.txt", section_id="S1", chunk_index=0, chunk_text=text)
    return RetrievalResult(child=chunk, parent=chunk, score=score, bm25_score=score, vector_score=score)


def _make_reranker(response_text: str, top_k: int = 5) -> tuple:
    """Return (reranker, patcher) — caller must start/stop the patcher."""
    cfg = LexConfig()
    reranker = LLMReranker(cfg=cfg, top_k=top_k)
    return reranker, response_text


# -----------------------------------------------------------------------
# _parse_scores
# -----------------------------------------------------------------------

def test_parse_scores_json_array():
    scores = _parse_scores("[7, 3, 9, 2]", expected_count=4)
    assert scores == [7.0, 3.0, 9.0, 2.0]


def test_parse_scores_inline_numbers():
    scores = _parse_scores("The scores are 8, 5, 6, 3 respectively.", expected_count=4)
    assert len(scores) == 4
    assert scores[0] == 8.0


def test_parse_scores_fallback_neutral():
    # Unparseable → all 1.0 (neutral, preserves order)
    scores = _parse_scores("I cannot rate these passages.", expected_count=3)
    assert scores == [1.0, 1.0, 1.0]


def test_parse_scores_wrong_count_fallback():
    # Array has wrong length → fallback
    scores = _parse_scores("[7, 3]", expected_count=4)
    assert len(scores) == 4


# -----------------------------------------------------------------------
# LLMReranker.rerank
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rerank_empty_returns_empty():
    cfg = LexConfig()
    reranker = LLMReranker(cfg=cfg, top_k=5)
    assert await reranker.rerank("query", []) == []


@pytest.mark.asyncio
async def test_rerank_sorts_by_score():
    results = [
        _make_result("Low relevance passage", score=0.9),
        _make_result("High relevance passage about injunction", score=0.3),
        _make_result("Medium relevance passage", score=0.5),
    ]
    cfg = LexConfig()
    reranker = LLMReranker(cfg=cfg, top_k=3)
    with patch("lexagent.nodes._llm.call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {"content": "[2, 9, 4]", "tool_calls": None}
        reranked = await reranker.rerank("injunction property dispute", results)
    assert reranked[0].child.chunk_text == "High relevance passage about injunction"


@pytest.mark.asyncio
async def test_rerank_respects_top_k():
    results = [_make_result(f"Passage {i}") for i in range(6)]
    cfg = LexConfig()
    reranker = LLMReranker(cfg=cfg, top_k=3)
    with patch("lexagent.nodes._llm.call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {"content": "[1, 2, 3, 4, 5, 6]", "tool_calls": None}
        reranked = await reranker.rerank("query", results)
    assert len(reranked) <= 3


@pytest.mark.asyncio
async def test_rerank_llm_failure_returns_original_order():
    results = [_make_result(f"Passage {i}", score=float(i)) for i in range(3)]
    cfg = LexConfig()
    reranker = LLMReranker(cfg=cfg, top_k=3)
    with patch("lexagent.nodes._llm.call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = RuntimeError("LLM down")
        reranked = await reranker.rerank("query", results)
    assert len(reranked) <= 3
    assert reranked[0].child.chunk_text == "Passage 0"


# -----------------------------------------------------------------------
# HybridRetriever.retrieve_reranked
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_reranked_no_reranker():
    from lexagent.tools.retriever import HybridRetriever
    from lexagent.tools.chunker import chunk_text

    findings = [{"citation": "AIR 1978 SC 597", "full_text": "Section 3 Injunction.\n" + "Content " * 50}]
    retriever = HybridRetriever.from_findings(findings)
    results = await retriever.retrieve_reranked("injunction", top_k=3, reranker=None)
    assert isinstance(results, list)
