"""
Phase 5, Lesson 4: TF-IDF Vectors and Cosine Similarity
# pip install scikit-learn
"""
# ── SECTION 1: What TF-IDF is ──────────────────────────────────────────────────
print("=" * 60)
print("TF-IDF Vectors + Cosine Similarity")
print("=" * 60)
print("""
  TF-IDF converts each document into a vector of word weights.

  TF  (Term Frequency): how often a word appears in THIS document
  IDF (Inverse Doc Frequency): how rare the word is across ALL documents
  TF-IDF = TF × IDF

  Result: common words ("the", "a", "of") get near-zero weight.
          rare, meaningful words ("certiorari", "mandamus") get high weight.

  Cosine similarity: measures angle between two vectors.
    1.0 = identical direction (same topic)
    0.0 = perpendicular (completely different topics)
""")

# ── SECTION 2: Setup ───────────────────────────────────────────────────────────
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
except ImportError:
    print("Install scikit-learn: pip install scikit-learn")
    raise SystemExit(1)

CASES = [
    "Maneka Gandhi v Union of India AIR 1978 SC 597 Article 21 personal liberty "
    "right to travel abroad passport cannot be impounded without fair hearing",
    "Kesavananda Bharati v State of Kerala AIR 1973 SC 1461 basic structure "
    "doctrine constitutional amendment Parliament cannot destroy basic structure",
    "A K Gopalan v State of Madras AIR 1950 SC 27 preventive detention Article 19 "
    "Article 21 personal liberty narrow interpretation procedure established by law",
    "Olga Tellis v Bombay Municipal Corporation 1985 SCC right to livelihood "
    "Article 21 right to life includes right to livelihood pavement dwellers",
    "Francis Coralie Mullin v Union Territory Delhi 1981 SC Article 21 right to "
    "live with dignity human dignity bare necessities personal liberty expansive",
]

# ── SECTION 3: Build TF-IDF matrix ─────────────────────────────────────────────
print("── Building TF-IDF matrix ──")
vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
tfidf_matrix = vectorizer.fit_transform(CASES)
print(f"Matrix shape: {tfidf_matrix.shape} ({len(CASES)} docs × {tfidf_matrix.shape[1]} features)")
print(f"Sample features: {vectorizer.get_feature_names_out()[:8].tolist()}")

# ── SECTION 4: Query and rank ──────────────────────────────────────────────────
print("\n── Query: 'right to personal liberty dignity' ──")
query = "right to personal liberty dignity"
query_vec = vectorizer.transform([query])
sims = cosine_similarity(query_vec, tfidf_matrix)[0]

ranked = sorted(zip(sims, CASES), key=lambda x: x[0], reverse=True)
for rank, (sim, case) in enumerate(ranked, 1):
    print(f"  #{rank} Sim {sim:.3f}: {case[:65]}...")

# ── SECTION 5: TF-IDF vs BM25 comparison ──────────────────────────────────────
print("""
── When TF-IDF beats BM25, and when it doesn't ──

  TF-IDF WINS for doctrine queries:
    "right to personal liberty" matches "personal liberty guaranteed" even
    without exact phrase — because vector similarity captures semantic overlap.

  BM25 WINS for citation queries:
    "AIR 1978 SC 597" — BM25 treats each token separately with high IDF.
    TF-IDF may spread weight across many low-IDF terms ("1978", "597").

  HYBRID = best of both worlds (next lesson).
""")

# ── SECTION 6: Visualize the vector ────────────────────────────────────────────
print("── Top TF-IDF weights for Maneka Gandhi case ──")
feature_names = vectorizer.get_feature_names_out()
doc0_weights = np.asarray(tfidf_matrix[0].todense()).flatten()
top_indices = doc0_weights.argsort()[-8:][::-1]
for idx in top_indices:
    if doc0_weights[idx] > 0:
        print(f"  '{feature_names[idx]}': {doc0_weights[idx]:.3f}")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
print("\n── PAUSE AND THINK ──")
print("""
  1. Open lexagent/tools/retriever.py — does it use TfidfVectorizer or something else?
     Is there a custom embedding model used anywhere?

  2. ngram_range=(1,2) means we also index 2-word phrases ("personal liberty",
     "basic structure"). Why is this especially useful for Indian legal text?

  3. What happens if you query "AIR 1978 SC 597" with TF-IDF? Run it and compare
     the score to the BM25 score from the previous lesson. Which is higher?

  4. TF-IDF is a "bag of words" model — word ORDER doesn't matter.
     "Liberty personal" and "personal liberty" get the same vector.
     Is this a problem for Indian legal text? Give an example where order matters.

  5. LexAgent config has lexagent/config.py → retriever_bm25_weight (default 0.4).
     This means BM25 gets 40% weight in the hybrid. Why might you increase this
     for a matter involving many precise citation strings?
""")
