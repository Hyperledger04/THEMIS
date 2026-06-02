"""
Phase 5, Lesson 3: BM25 — Best Match Ranking for Indian Case Law
# pip install rank-bm25
"""
# ── SECTION 1: Why keyword ranking matters ─────────────────────────────────────
print("=" * 60)
print("BM25: Best Match Ranking")
print("=" * 60)

# The problem with simple word counting (Term Frequency):
# - "Article 21" appears 50 times in a 5000-word judgment → high TF
# - "Article 21" appears 5 times in a 500-word headnote → same TF
# - The headnote is more densely relevant, but TF treats them equally.
# BM25 fixes this with a saturation function + length normalization.

# ── SECTION 2: BM25 formula intuition ──────────────────────────────────────────
print("\n── BM25 Formula Intuition ──")
print("""
  score = IDF(term) × TF_norm(term, doc)

  IDF (Inverse Document Frequency):
    rare terms get higher weight
    "Maneka Gandhi" appears in few docs → high IDF
    "Article 21" appears in many docs  → lower IDF

  TF_norm (normalized Term Frequency):
    uses saturation: after 5 occurrences, adding more has diminishing returns
    penalizes long documents (b=0.75 controls this)

  Parameters:
    k1 = 1.5  (saturation speed — standard)
    b  = 0.75 (length normalization — standard)
""")

# ── SECTION 3: Live BM25 demo ───────────────────────────────────────────────────
try:
    from rank_bm25 import BM25Okapi
except ImportError:
    print("Install rank-bm25: pip install rank-bm25")
    raise SystemExit(1)

# Our corpus: 5 case law summaries (real Indian Supreme Court cases)
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

print("── Corpus loaded: 5 Indian Supreme Court cases ──")

# Tokenize: BM25Okapi expects list of token lists
tokenized = [case.lower().split() for case in CASES]
bm25 = BM25Okapi(tokenized)
print(f"BM25 index built over {len(CASES)} documents")

# ── SECTION 4: Queries and scores ──────────────────────────────────────────────
print("\n── Query 1: 'article 21 personal liberty maneka gandhi' ──")
query1 = "article 21 personal liberty maneka gandhi"
scores1 = bm25.get_scores(query1.lower().split())

ranked1 = sorted(zip(scores1, CASES), key=lambda x: x[0], reverse=True)
for rank, (score, case) in enumerate(ranked1, 1):
    print(f"  #{rank} Score {score:.3f}: {case[:65]}...")

print("\n── Query 2: Exact citation string 'AIR 1978 SC 597' ──")
query2 = "AIR 1978 SC 597"
scores2 = bm25.get_scores(query2.split())
ranked2 = sorted(zip(scores2, CASES), key=lambda x: x[0], reverse=True)
print(f"  #1 Score {ranked2[0][0]:.3f}: {ranked2[0][1][:65]}...")
print("  (BM25 finds exact citation strings reliably — no semantic confusion)")

# ── SECTION 5: Why BM25 beats LIKE for legal citations ──────────────────────────
print("""
── Why BM25 beats SQL LIKE for Indian citations ──

  LIKE '%AIR 1978 SC 597%'  — exact string match only, no ranking
  BM25("AIR 1978 SC 597")   — scores all docs, rare terms (597) get high IDF

  For Indian law:
  - Citation strings ("AIR 1978 SC 597") are rare → high IDF → high BM25 score
  - The right judgment floats to the top even in a corpus of 10,000 cases
  - LIKE requires the citation to be exact character-for-character
""")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
print("\n── PAUSE AND THINK ──")
print("""
  1. Open lexagent/tools/retriever.py — where is BM25Okapi used?
     What parameter does LexConfig expose to tune it?

  2. Why is BM25 better for "AIR 1978 SC 597" than for "right to personal liberty"?
     (Hint: think about IDF — which query has rarer terms in a legal corpus?)

  3. BM25 uses word tokens (split on spaces). "Maneka" and "Gandhi" are separate tokens.
     What happens if a lawyer types "Maneka-Gandhi" (hyphenated)?
     How would you fix this in the tokenizer?

  4. Open lexagent/tools/retriever.py — does it use BM25Okapi or BM25Plus?
     Look up the difference. Why might BM25Plus be better for very short chunks?

  5. The corpus here is 5 sentences. In production LexAgent, the corpus is
     research_findings (list of fetched judgment texts). Open lexagent/tools/retriever.py
     and find the from_findings() classmethod — how does it build the corpus?
""")
