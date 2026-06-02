"""
Phase 5, Lesson 5: Hybrid Retrieval — BM25 + TF-IDF Combined
# pip install rank-bm25 scikit-learn
"""
print("=" * 60)
print("HybridRetriever: BM25 + TF-IDF")
print("=" * 60)

# ── SECTION 1: Why hybrid? ─────────────────────────────────────────────────────
print("""
  BM25 alone:  great for exact citations, misses doctrine queries
  TF-IDF alone: great for doctrine, misses exact citation strings
  Hybrid:       combines both with a weighted average

  Formula:
    hybrid_score = alpha * norm(bm25_score) + (1 - alpha) * norm(tfidf_score)

  alpha = cfg.retriever_bm25_weight (default 0.4)
  - alpha=0.0 → pure TF-IDF (doctrine only)
  - alpha=1.0 → pure BM25 (keyword only)
  - alpha=0.4 → default: slightly TF-IDF weighted
""")

# ── SECTION 2: HybridRetriever class ──────────────────────────────────────────
try:
    from rank_bm25 import BM25Okapi
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
except ImportError:
    print("Install: pip install rank-bm25 scikit-learn")
    raise SystemExit(1)


class HybridRetriever:
    """Combines BM25 (keyword) + TF-IDF (semantic) retrieval."""

    def __init__(self, corpus: list[str], alpha: float = 0.4):
        self.corpus = corpus
        self.alpha = alpha

        # BM25 index
        tokenized = [doc.lower().split() for doc in corpus]
        self.bm25 = BM25Okapi(tokenized)

        # TF-IDF index
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)

    @classmethod
    def from_findings(cls, findings: list[str], alpha: float = 0.4) -> "HybridRetriever":
        """Build retriever from research_findings list (LexAgent pattern)."""
        return cls(corpus=findings, alpha=alpha)

    @staticmethod
    def _normalize(arr: np.ndarray) -> np.ndarray:
        """Scale array to [0, 1]. Returns zeros if max is 0."""
        mx = arr.max()
        return arr / mx if mx > 0 else arr

    def retrieve(self, query: str, k: int = 3) -> list[dict]:
        """Return top-k chunks with hybrid scores."""
        bm25_scores = np.array(self.bm25.get_scores(query.lower().split()))
        query_vec = self.vectorizer.transform([query])
        tfidf_scores = cosine_similarity(query_vec, self.tfidf_matrix)[0]

        hybrid = self.alpha * self._normalize(bm25_scores) + \
                 (1 - self.alpha) * self._normalize(tfidf_scores)

        top_k_idx = hybrid.argsort()[-k:][::-1]
        return [
            {"text": self.corpus[i], "score": float(hybrid[i]),
             "bm25": float(bm25_scores[i]), "tfidf": float(tfidf_scores[i])}
            for i in top_k_idx
        ]


# ── SECTION 3: Live demo ───────────────────────────────────────────────────────
CASES = [
    "Maneka Gandhi v Union of India AIR 1978 SC 597 Article 21 personal liberty "
    "right to travel abroad passport cannot be impounded without fair hearing",
    "Kesavananda Bharati v State of Kerala AIR 1973 SC 1461 basic structure "
    "doctrine constitutional amendment Parliament cannot destroy basic structure",
    "A K Gopalan v State of Madras AIR 1950 SC 27 preventive detention Article 21 "
    "personal liberty narrow interpretation procedure established by law",
    "Olga Tellis v Bombay Municipal Corporation 1985 SCC right to livelihood "
    "Article 21 right to life includes right to livelihood pavement dwellers",
    "Francis Coralie Mullin v Delhi 1981 SC Article 21 right to live with dignity",
]

retriever = HybridRetriever.from_findings(CASES, alpha=0.4)

print("── Query 1: Doctrine ('personal liberty dignity') ──")
results = retriever.retrieve("personal liberty dignity", k=3)
for r in results:
    print(f"  Score {r['score']:.3f} (BM25:{r['bm25']:.2f} TF-IDF:{r['tfidf']:.3f}): {r['text'][:55]}...")

print("\n── Query 2: Citation ('AIR 1978 SC 597') ──")
results = retriever.retrieve("AIR 1978 SC 597", k=3)
for r in results:
    print(f"  Score {r['score']:.3f}: {r['text'][:60]}...")

print("\n── Alpha effect: increasing BM25 weight ──")
retriever_heavy_bm25 = HybridRetriever.from_findings(CASES, alpha=0.8)
results2 = retriever_heavy_bm25.retrieve("personal liberty", k=1)
results3 = retriever.retrieve("personal liberty", k=1)
print(f"  alpha=0.8 top: {results2[0]['text'][:55]}...")
print(f"  alpha=0.4 top: {results3[0]['text'][:55]}...")

# ── SECTION 4: Connection to LexAgent ─────────────────────────────────────────
print("""
── How HybridRetriever fits in LexAgent ──

  1. research node: fetches raw case text → research_findings list
  2. cite node: HybridRetriever.from_findings(state["research_findings"])
  3. For each citation in draft: retriever.retrieve(citation_string, k=5)
  4. If citation appears in a top-5 chunk → verified (grounded_citations)
  5. If not → unverified_citations list

  Config: LEX_BM25_WEIGHT=0.4 (default, tunable per deployment)
""")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
print("── PAUSE AND THINK ──")
print("""
  1. Open lexagent/tools/retriever.py — does it have a from_findings() classmethod?
     What does it do with research_findings from LexState?

  2. The retriever here is rebuilt on every cite node call (from_findings each time).
     What is the cost of this? When would you want to cache/persist the retriever?
     Hint: see lexagent/tools/retriever.py → PersistentQdrantRetriever.

  3. LexConfig has retriever_bm25_weight. Find it in lexagent/config.py.
     For a matter with 20 specific citation strings to verify, would you increase
     or decrease this value? Why?

  4. The _normalize function divides by max score. What happens if ALL BM25 scores
     are 0 (no keyword overlap at all)? Is the hybrid score still meaningful?

  5. k=5 is the default — 5 parent chunks fed to the LLM for citation grounding.
     Why not k=50? What limits how many chunks you can include in the prompt?
""")
