"""Tests for lexagent/tools/retriever.py"""
import pytest
from lexagent.tools.chunker import Chunk
from lexagent.tools.retriever import HybridRetriever, RetrievalResult


_SAMPLE_FINDINGS = [
    {
        "citation": "AIR 1978 SC 597",
        "case_name": "Maneka Gandhi v Union of India",
        "full_text": (
            "The right to personal liberty under Article 21 cannot be curtailed "
            "except by procedure established by law. The Supreme Court held that "
            "the procedure must be fair, just and reasonable. AIR 1978 SC 597."
        ),
    },
    {
        "citation": "(2021) 3 SCC 415",
        "case_name": "Test Case Two",
        "full_text": (
            "Injunction granted against construction on disputed property. "
            "Plaintiff demonstrated prima facie case and balance of convenience. "
            "(2021) 3 SCC 415. Order XXXIX Rule 1 and 2 CPC applied."
        ),
    },
]


# -----------------------------------------------------------------------
# HybridRetriever construction
# -----------------------------------------------------------------------

def test_from_findings_builds_retriever():
    r = HybridRetriever.from_findings(_SAMPLE_FINDINGS)
    assert isinstance(r, HybridRetriever)
    assert len(r._children) > 0


def test_from_findings_empty_list():
    r = HybridRetriever.from_findings([])
    assert r._children == []


def test_from_findings_skips_empty_body():
    findings = [{"citation": "X", "full_text": ""}]
    r = HybridRetriever.from_findings(findings)
    assert r._children == []


def test_from_findings_uses_snippet_fallback():
    findings = [{"citation": "Y", "header": "Case Y", "snippet": "Some legal text here."}]
    r = HybridRetriever.from_findings(findings)
    assert len(r._children) > 0


# -----------------------------------------------------------------------
# retrieve
# -----------------------------------------------------------------------

def test_retrieve_returns_list():
    r = HybridRetriever.from_findings(_SAMPLE_FINDINGS)
    results = r.retrieve("injunction property", top_k=3)
    assert isinstance(results, list)


def test_retrieve_result_type():
    r = HybridRetriever.from_findings(_SAMPLE_FINDINGS)
    results = r.retrieve("Article 21 personal liberty")
    for res in results:
        assert isinstance(res, RetrievalResult)
        assert isinstance(res.child, Chunk)
        assert isinstance(res.parent, Chunk)
        assert isinstance(res.score, float)


def test_retrieve_top_k_limit():
    r = HybridRetriever.from_findings(_SAMPLE_FINDINGS)
    results = r.retrieve("law", top_k=1)
    assert len(results) <= 1


def test_retrieve_empty_corpus_returns_empty():
    r = HybridRetriever.from_findings([])
    assert r.retrieve("anything") == []


def test_retrieve_exact_citation_string():
    r = HybridRetriever.from_findings(_SAMPLE_FINDINGS)
    results = r.retrieve("AIR 1978 SC 597", top_k=5)
    # BM25 should surface the finding that contains this exact string
    assert len(results) > 0
    sources = [res.child.source_doc for res in results]
    assert any("AIR 1978 SC 597" in s for s in sources)


def test_retrieve_scores_between_0_and_1():
    r = HybridRetriever.from_findings(_SAMPLE_FINDINGS)
    results = r.retrieve("personal liberty Article 21")
    for res in results:
        assert 0.0 <= res.bm25_score <= 1.0
        assert 0.0 <= res.vector_score <= 1.0


def test_retrieve_parent_text_populated():
    r = HybridRetriever.from_findings(_SAMPLE_FINDINGS, child_max_tokens=50, parent_max_tokens=200)
    results = r.retrieve("injunction")
    for res in results:
        # parent_text should be set (may equal child_text for short docs)
        assert isinstance(res.parent.chunk_text, str)


# -----------------------------------------------------------------------
# Custom weights
# -----------------------------------------------------------------------

def test_custom_bm25_weight_accepted():
    r = HybridRetriever.from_findings(_SAMPLE_FINDINGS, bm25_weight=0.8)
    assert r._bm25_weight == 0.8


def test_zero_similarity_threshold_returns_results():
    r = HybridRetriever.from_findings(_SAMPLE_FINDINGS, similarity_threshold=0.0)
    results = r.retrieve("property")
    assert len(results) > 0
