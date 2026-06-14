"""Tests for themis/tools/retriever.py"""
import pytest
from themis.tools.chunker import Chunk
from themis.tools.retriever import HybridRetriever, RetrievalResult


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


# ---------------------------------------------------------------------------
# PersistentQdrantRetriever — CRIT-01 score gate
# ---------------------------------------------------------------------------

def test_persistent_qdrant_retriever_passes_score_threshold_to_query_points(monkeypatch):
    """CRIT-01: retrieve() must forward score_threshold to query_points so
    low-similarity Qdrant results never enter the cite node corpus."""
    from unittest.mock import MagicMock
    from themis.tools.retriever import PersistentQdrantRetriever

    # Build a minimal cfg with the threshold we want to assert.
    cfg = MagicMock()
    cfg.qdrant_url = "http://localhost:6333"
    cfg.qdrant_api_key = None
    cfg.embedding_model = "all-MiniLM-L6-v2"
    cfg.embedding_dim = 384
    cfg.retriever_similarity_threshold = 0.42  # sentinel value

    # Patch the embedding model so no network call is made.
    # WHY: encode()[0].tolist() is called in retriever.py — plain list has no
    # .tolist(), so we use numpy to match the SentenceTransformer return type.
    import numpy as np
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[0.1] * 384])

    # Patch the Qdrant client; capture what query_points was called with.
    mock_client = MagicMock()
    mock_client.query_points.return_value = MagicMock(points=[])

    qr = PersistentQdrantRetriever("M-test", firm_id="firm1", cfg=cfg)
    qr._model = mock_model
    qr._client = mock_client

    qr.retrieve("cheque bounce", top_k=3)

    call_kwargs = mock_client.query_points.call_args.kwargs
    assert call_kwargs.get("score_threshold") == 0.42, (
        "PersistentQdrantRetriever.retrieve() must pass score_threshold to query_points "
        "so low-similarity results are filtered before entering the cite node corpus."
    )
