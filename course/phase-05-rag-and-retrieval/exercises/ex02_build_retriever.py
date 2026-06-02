"""
Phase 5 — Exercise 2: Build HybridRetriever from Scratch
# pip install rank-bm25 scikit-learn
"""

CASES = [
    "Maneka Gandhi v Union of India AIR 1978 SC 597 Article 21 personal liberty "
    "right to travel abroad passport impounded without hearing natural justice",
    "Kesavananda Bharati v State of Kerala AIR 1973 SC 1461 basic structure doctrine "
    "constitutional amendment Parliament power limits",
    "A K Gopalan v State of Madras AIR 1950 SC 27 preventive detention Article 21 "
    "personal liberty procedure established by law narrow interpretation",
    "Olga Tellis v Bombay Municipal Corporation 1985 SCC 545 right to livelihood "
    "Article 21 right to life pavement dwellers eviction",
    "Francis Coralie Mullin v Union Territory Delhi 1981 SC 608 Article 21 "
    "right to live with dignity human dignity bare necessities",
]


class HybridRetriever:
    """
    Combines BM25 (keyword) + TF-IDF (semantic) for retrieval.
    alpha controls BM25 weight: hybrid = alpha*bm25_norm + (1-alpha)*tfidf_norm
    """

    def __init__(self, corpus: list[str], alpha: float = 0.4):
        self.corpus = corpus
        self.alpha = alpha
        # TODO: initialize self.bm25 using BM25Okapi(tokenized_corpus)
        # TODO: initialize self.vectorizer = TfidfVectorizer(stop_words="english")
        # TODO: fit vectorizer and store self.tfidf_matrix = vectorizer.fit_transform(corpus)
        pass

    @classmethod
    def from_findings(cls, findings: list[str], alpha: float = 0.4) -> "HybridRetriever":
        """Build retriever from research_findings (matches LexAgent pattern)."""
        # TODO: return cls(corpus=findings, alpha=alpha)
        pass

    def retrieve(self, query: str, k: int = 3) -> list[dict]:
        """
        Return top-k chunks ranked by hybrid score.

        Steps:
        1. Get BM25 scores: self.bm25.get_scores(query.lower().split())
        2. Get TF-IDF cosine scores: cosine_similarity(query_vec, self.tfidf_matrix)[0]
        3. Normalize both to [0, 1] by dividing by max (handle max=0)
        4. hybrid = alpha * bm25_norm + (1-alpha) * tfidf_norm
        5. Return top-k as [{"text": ..., "score": float, "rank": int}, ...]
        """
        # TODO: implement
        pass


# ── TESTS ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        import numpy as np
        from rank_bm25 import BM25Okapi
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Run: pip install rank-bm25 scikit-learn")
        raise SystemExit(1)

    retriever = HybridRetriever.from_findings(CASES, alpha=0.4)
    assert retriever is not None, "from_findings returned None"

    # Test 1: doctrine query
    results = retriever.retrieve("personal liberty dignity Article 21", k=3)
    assert results is not None, "retrieve returned None"
    assert len(results) == 3, f"Expected 3 results, got {len(results)}"
    assert all("text" in r and "score" in r for r in results), "Each result needs text and score"
    print(f"✓ Doctrine query top result: {results[0]['text'][:55]}... (score={results[0]['score']:.3f})")

    # Test 2: citation query — Maneka Gandhi should rank #1
    results2 = retriever.retrieve("AIR 1978 SC 597", k=3)
    assert "Maneka Gandhi" in results2[0]["text"], \
        f"Expected Maneka Gandhi as top result for citation query, got: {results2[0]['text'][:50]}"
    print(f"✓ Citation query top result: {results2[0]['text'][:55]}... (score={results2[0]['score']:.3f})")

    # Test 3: scores are in [0, 1]
    assert all(0.0 <= r["score"] <= 1.0 for r in results), "Scores should be normalized to [0, 1]"
    print("✓ All scores in [0, 1] range")

    # Test 4: results sorted descending
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True), "Results should be sorted by score descending"
    print("✓ Results sorted descending by score")

    print("\n✅ All tests passed!")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
# 1. Open lexagent/tools/retriever.py — does the real HybridRetriever also have
#    a PersistentQdrantRetriever? What does persistence add beyond what you built?
# 2. Your retriever is rebuilt every time from_findings() is called. What is the
#    computational cost of fitting TfidfVectorizer on 50 large judgments?
# 3. Change alpha to 0.9 and rerun. Does the citation query still work correctly?
#    At what alpha does TF-IDF stop helping for citation queries?
