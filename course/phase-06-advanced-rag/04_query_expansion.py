"""
Phase 6, Lesson 4: Query Expansion — Indian Legal Synonyms
No external dependencies needed.
"""
print("=" * 60)
print("Query Expansion for Indian Legal Text")
print("=" * 60)

# ── SECTION 1: The vocabulary mismatch problem ────────────────────────────────
print("""
  Problem: lawyers use everyday language; case law uses formal legal language.

  Lawyer types:    "eviction case"
  Case law says:   "suit for ejectment" / "possession matter" / "dispossession"

  Without expansion: BM25 scores 0 for "eviction" if corpus only has "ejectment"
  With expansion:    query becomes "eviction ejectment possession dispossession"
                     → BM25 now finds the right cases

  Why NOT use an LLM for expansion?
  - LLMs can hallucinate synonyms ("wrongful eviction" is NOT "ejectment" in law)
  - Deterministic dictionary: same input → same expansion, always
  - Zero API cost, zero latency
  - Lawyer-curated: can be reviewed and corrected without touching Python code
""")

# ── SECTION 2: The synonym dictionary ────────────────────────────────────────
LEGAL_SYNONYMS: dict[str, list[str]] = {
    # Property / Tenancy
    "eviction": ["ejectment", "possession", "dispossession", "unlawful occupation"],
    "tenancy": ["lease", "licensee", "landlord tenant", "rent"],

    # Negotiable Instruments
    "cheque bounce": ["section 138 ni act", "negotiable instruments act",
                      "dishonour of cheque", "dishonour", "section 138"],
    "dishonour": ["section 138 ni act", "cheque bounce", "returned unpaid"],

    # Constitutional / Writs
    "writ": ["article 226", "article 32", "mandamus", "certiorari",
             "habeas corpus", "prohibition", "quo warranto"],
    "fundamental rights": ["article 14", "article 19", "article 21",
                           "constitutional rights", "basic rights"],

    # Criminal
    "bail": ["anticipatory bail", "regular bail", "section 437 crpc",
             "section 438 crpc", "section 439 crpc", "interim bail"],
    "fir": ["first information report", "section 154 crpc", "police complaint"],

    # Limitation
    "limitation": ["time barred", "delay and laches", "condonation of delay",
                   "section 5 limitation act", "section 14 limitation act"],
    "time barred": ["limitation period expired", "barred by limitation", "limitation"],

    # Civil
    "injunction": ["stay order", "interim relief", "status quo order",
                   "temporary injunction", "order 39 rule 1"],
    "contempt": ["contempt of court", "wilful disobedience", "civil contempt",
                 "criminal contempt", "contempt of courts act"],

    # Corporate / Commercial
    "company": ["corporation", "limited company", "private limited", "llp",
                "limited liability partnership", "incorporation"],
    "insolvency": ["ibc", "insolvency and bankruptcy code", "nclt", "liquidation",
                   "resolution professional", "corporate insolvency resolution"],
}

# ── SECTION 3: The expand_query function ─────────────────────────────────────
def expand_query(query: str) -> str:
    """
    Append Indian legal synonyms to the query.
    For any synonym key found in the query, append its synonyms.
    Returns expanded query string (original + synonyms).
    """
    query_lower = query.lower()
    expanded_terms = [query]

    for term, synonyms in LEGAL_SYNONYMS.items():
        if term in query_lower:
            # Only add synonyms not already in the query
            new_terms = [s for s in synonyms if s not in query_lower]
            expanded_terms.extend(new_terms)

    return " ".join(expanded_terms)


# ── SECTION 4: Live demo ──────────────────────────────────────────────────────
print("── Query Expansion Examples ──\n")

test_queries = [
    "eviction case limitation period",
    "cheque bounce complaint against director",
    "writ petition against illegal order",
    "bail application murder case",
    "company insolvency NCLT petition",
]

for q in test_queries:
    expanded = expand_query(q)
    added = expanded[len(q):].strip()
    print(f"  Original:  {q}")
    print(f"  Expanded:  {expanded[:90]}{'...' if len(expanded) > 90 else ''}")
    print(f"  Added:     {added[:70] if added else '(nothing new)'}")
    print()

# ── SECTION 5: BM25 score comparison ─────────────────────────────────────────
print("── BM25 Score: Before vs After Expansion ──")

CORPUS = [
    "suit for ejectment filed by landlord against tenant dispossession under Transfer of Property Act",
    "writ petition against illegal construction Article 226 High Court certiorari",
    "section 138 negotiable instruments act dishonour of cheque criminal complaint",
    "anticipatory bail under section 438 CrPC sessions court murder case",
]

try:
    from rank_bm25 import BM25Okapi
    tokenized = [doc.lower().split() for doc in CORPUS]
    bm25 = BM25Okapi(tokenized)

    query = "eviction case"
    expanded = expand_query(query)

    raw_scores = bm25.get_scores(query.lower().split())
    exp_scores = bm25.get_scores(expanded.lower().split())

    print(f"\n  Query: '{query}'")
    print(f"  Raw scores:      {[f'{s:.3f}' for s in raw_scores]}")
    print(f"  Expanded scores: {[f'{s:.3f}' for s in exp_scores]}")
    print(f"  → Corpus[0] (ejectment) score: {raw_scores[0]:.3f} → {exp_scores[0]:.3f}")
    print("  (Expansion found 'ejectment' case that raw query missed entirely)")

except ImportError:
    print("  (Install rank-bm25 to see score comparison: pip install rank-bm25)")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
print("\n── PAUSE AND THINK ──")
print("""
  1. Open lexagent/tools/query_expander.py — does the real expander use a similar
     dictionary approach? What additional synonym categories does it include?

  2. The dictionary approach is deterministic. If a lawyer in Karnataka searches
     "eviction" but local case law uses "Kannada equivalent terms", this fails.
     How would you extend this approach to handle regional legal terminology?

  3. What happens if expand_query is called with "section 138" (no space before)?
     Does your implementation catch "section 138 ni act" in LEGAL_SYNONYMS?
     How would you make the matching more robust?

  4. Expansion increases query length. BM25 with 20-term queries may score
     differently than 3-term queries. Should you weight original query terms
     higher than expanded terms? How would you implement this?

  5. Open lexagent/config.py — is query expansion toggled by a feature flag?
     Should it be? What would be the downside of always-on expansion?
""")
