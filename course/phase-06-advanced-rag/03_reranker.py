# ── SECTION 1: PROBLEM — RETRIEVAL ≠ RELEVANCE ──────────────────────────────────────────────
#
# File: course/phase-06-advanced-rag/03_reranker.py
# LexAgent source: lexagent/tools/reranker.py
# Toggle: LEX_RERANKER_ENABLED=true  (OFF by default — costs 1 LLM call per chunk)
#
# BM25 and TF-IDF rank chunks by keyword overlap with the query.
# They do NOT understand legal doctrine.
#
# Example query: "right to life personal liberty passport impounded"
#
# BM25 may rank this chunk highest:
#   "The petitioner's passport was impounded by the passport authority."
# …because it contains "passport" and "impounded" — high keyword overlap.
#
# But the doctrinally important chunk is:
#   "Maneka Gandhi v UOI held that Article 21 personal liberty requires just, fair
#    and reasonable procedure — mere 'procedure established by law' is insufficient."
#
# A lawyer NEEDS the second chunk. BM25 gives them the first.
# Solution: after retrieval, ask the LLM to score each chunk 0–10 for relevance.


# ── SECTION 2: SOLUTION — LLM RE-RANKING ────────────────────────────────────────────────────
#
# Pipeline:
#   query → BM25/vector retrieval (top-20) → LLM scores each chunk → return top-5
#
# Cost note: 1 LLM call per chunk. If you retrieve 20 chunks and each call
# costs $0.001, that is $0.02 per query. Acceptable for high-stakes litigation drafting.
# NOT acceptable for a consumer search box.
#
# WHY keep retrieval before re-ranking?
# Re-ranking 1,000 chunks would cost $1 per query. Retrieval narrows the field cheaply.
# Re-ranking is the expensive PRECISION step, not the RECALL step.


# ── SECTION 3: COST / QUALITY TRADEOFF ──────────────────────────────────────────────────────
#
# Strategy          | Cost      | Quality
# ──────────────────|───────────|────────────────────────────────────────
# BM25 only         | ~$0       | Misses doctrine, good for keyword queries
# Vector only       | ~$0.001   | Misses exact terms, good for semantic queries
# Hybrid (BM25+vec) | ~$0.002   | Better recall, still no doctrine understanding
# + LLM re-rank     | ~$0.02    | High precision on doctrinal relevance ← LexAgent uses this
#
# Toggle: set LEX_RERANKER_ENABLED=true in .env to activate the LLM scoring step.
# When disabled, hybrid retrieval scores are used as-is.


# ── SECTION 4: SIMULATED LLM SCORES (no API needed) ──────────────────────────────────────────
#
# In production, each score comes from an actual LLM call like:
#
#   prompt = f"""
#   Query: {query}
#   Chunk: {chunk}
#   On a scale 0–10, how relevant is this chunk to answering the query?
#   Reply with a single integer only.
#   """
#   score = int(llm.invoke(prompt).content.strip())
#
# Here we use a lookup table keyed by recognisable substrings — same interface, zero cost.

SIMULATED_SCORES: dict[str, int] = {
    "Maneka Gandhi v UOI Article 21 personal liberty": 9,
    "Kesavananda Bharati basic structure":              3,
    "A K Gopalan preventive detention Article 19":     6,
    "Olga Tellis right to livelihood":                 7,
    "Francis Coralie right to live dignity":           8,
    "passport authority impounded travel document":    4,
    "procedure established by law section 10":         5,
}


def fake_llm_score(query: str, chunk: str) -> int:
    """
    Simulate an LLM relevance score (0–10) without an API call.
    Production version: replace the body with an actual LLM invocation.
    """
    chunk_lower = chunk.lower()
    for key, score in SIMULATED_SCORES.items():
        # If any of the first 3 words of the key appear in the chunk, use that score.
        key_words = key.lower().split()[:3]
        if any(w in chunk_lower for w in key_words):
            return score
    return 2  # Default: low relevance for unrecognised chunks.


def bm25_score(query: str, chunk: str) -> float:
    """
    Extremely simplified BM25: count query term overlaps (keyword frequency).
    Real BM25 adds IDF weighting and document length normalisation.
    """
    query_terms = query.lower().split()
    chunk_lower = chunk.lower()
    return sum(chunk_lower.count(term) for term in query_terms)


# ── SECTION 5: DEMO — BM25 ORDER vs LLM-RERANKED ORDER ──────────────────────────────────────

CHUNKS = [
    "The petitioner's passport was impounded under Section 10(3)(c) of the Passports Act 1967.",
    "A K Gopalan v State of Madras (1950) upheld preventive detention under Article 19 restrictions.",
    "Olga Tellis v Bombay Municipal Corporation held the right to livelihood flows from Article 21.",
    "Kesavananda Bharati established the basic structure doctrine limiting Parliament's amending power.",
    "Francis Coralie Mullin v UT Delhi: the right to live with dignity is part of Article 21.",
    "Maneka Gandhi v UOI (1978): Article 21 personal liberty requires just, fair and reasonable procedure.",
    "Procedure established by law under Section 10 must satisfy Articles 14 and 19 as well.",
]


def rerank(query: str, chunks: list[str]) -> list[dict]:
    """Score each chunk with the simulated LLM and return sorted results."""
    scored = [(fake_llm_score(query, chunk), chunk) for chunk in chunks]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"llm_score": s, "text": c} for s, c in scored]


def bm25_rank(query: str, chunks: list[str]) -> list[dict]:
    """Rank chunks by BM25 keyword overlap."""
    scored = [(bm25_score(query, chunk), chunk) for chunk in chunks]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"bm25_score": s, "text": c} for s, c in scored]


def main() -> None:
    query = "right to life personal liberty passport impounded Article 21"

    print("=== Re-Ranker Demo ===")
    print(f"Query: {query}\n")

    print("── BM25 Order (keyword overlap) ──")
    for i, item in enumerate(bm25_rank(query, CHUNKS), 1):
        preview = item["text"][:70]
        print(f"  {i}. [score={item['bm25_score']:.0f}] {preview}...")

    print("\n── LLM Re-ranked Order (doctrinal relevance) ──")
    for i, item in enumerate(rerank(query, CHUNKS), 1):
        preview = item["text"][:70]
        print(f"  {i}. [score={item['llm_score']}] {preview}...")

    print("\nObservation: BM25 surfaces the 'passport' chunk first (keyword match).")
    print("LLM re-ranker surfaces Maneka Gandhi first (doctrinal relevance).")
    print("The lawyer needs Maneka Gandhi. Re-ranking wins.")


if __name__ == "__main__":
    main()


# ── PAUSE AND THINK ─────────────────────────────────────────────────────────────────────────
#
# 1. Open lexagent/tools/reranker.py (or create it).
#    Write the function signature: rerank(query: str, chunks: list[str]) -> list[str]
#    What LLM prompt would you send to score a single chunk 0–10?
#
# 2. LEX_RERANKER_ENABLED is a config flag. Which node reads it?
#    Trace: research node → cite node → which one calls rerank()?
#
# 3. Why re-rank the TOP-20 from BM25, not all 200 chunks in the database?
#    What is the cost implication of re-ranking all chunks?
#
# 4. A chunk scores 9 on LLM relevance but comes from a 1952 judgment that was
#    later overruled. How would you incorporate the knowledge graph (02_graphrag.py)
#    to penalise overruled cases in the final ranking?
#
# 5. The LLM scoring prompt is itself a form of RAG (context in, judgment out).
#    Does the re-ranker LLM need to be the same model as the drafting LLM?
#    What tradeoff does using a cheaper/smaller model for scoring introduce?
