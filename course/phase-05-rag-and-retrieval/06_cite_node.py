"""
Phase 5, Lesson 6: The Citation Verification Node

This is the full cite node pipeline: extract → verify → ground → flag.
No external dependencies needed.
"""
import re

print("=" * 60)
print("Citation Verification — the cite node")
print("=" * 60)

# ── SECTION 1: Why cite verification exists ────────────────────────────────────
print("""
  Without RAG: LLM invents "AIR 2019 SC 500 — Sharma v. State" — doesn't exist.
  With RAG:    LLM cites cases from research_findings. But does it cite them correctly?

  The cite node:
  1. Extracts every citation string from the draft
  2. Searches retrieved chunks for that exact string
  3. If found → verified, records which chunk
  4. If not found → unverified (possible hallucination)
  5. Returns: citations_verified=True only if ALL citations are grounded
""")

# ── SECTION 2: Indian citation regex ──────────────────────────────────────────
print("── Indian Citation Patterns ──")

# Indian citations follow specific reporter formats:
# AIR YYYY CourtCode PageNum   e.g. "AIR 1978 SC 597"
# (YYYY) Vol SCC PageNum       e.g. "(1973) 4 SCC 225"
# YYYY SCMR                    e.g. "1985 SCMR 1234"
CITATION_RE = re.compile(
    r'\b(?:AIR\s+\d{4}\s+\w{2,4}\s+\d+|'  # AIR format
    r'\(\d{4}\)\s+\d+\s+SCC\s+\d+|'        # SCC format
    r'\d{4}\s+SCR\s+\d+|'                   # SCR format
    r'\d{4}\s+MLJ\s+\d+)',                  # MLJ format
    re.IGNORECASE
)

sample_draft = """
IN THE HIGH COURT OF DELHI

The fundamental right to personal liberty under Article 21 is sacrosanct.
As held in AIR 1978 SC 597 (Maneka Gandhi), the passport cannot be impounded
without hearing. The principle in (1981) 1 SCC 608 reinforces this position.
However, counsel also cited AIR 2024 SC 9999 which does not exist in our records.
"""

found = CITATION_RE.findall(sample_draft)
print(f"Citations found in draft: {found}")

# ── SECTION 3: The verification function ──────────────────────────────────────
print("\n── Citation Verification ──")

def extract_citations(draft: str) -> list[str]:
    """Extract all Indian citation strings from draft text."""
    return CITATION_RE.findall(draft)


def verify_citations(citations: list[str], chunks: list[str]) -> dict:
    """
    Check each citation against retrieved chunks.
    Returns state-ready dict with citations_verified, unverified_citations,
    grounded_citations keys (matching LexState fields).
    """
    chunks_text = " ".join(chunks)
    grounded = {}
    unverified = []

    for cit in citations:
        # Case-insensitive check: citation must appear verbatim in a chunk
        if re.search(re.escape(cit), chunks_text, re.IGNORECASE):
            # Find which specific chunk contains it
            for i, chunk in enumerate(chunks):
                if re.search(re.escape(cit), chunk, re.IGNORECASE):
                    grounded[cit] = f"chunk_{i}"
                    break
        else:
            unverified.append(cit)

    return {
        "citations_verified": len(unverified) == 0,
        "unverified_citations": unverified,
        "grounded_citations": grounded,
    }


# ── SECTION 4: Live demo ───────────────────────────────────────────────────────
# Simulate what research node would have fetched
RETRIEVED_CHUNKS = [
    "In Maneka Gandhi v Union of India, AIR 1978 SC 597, the Supreme Court held "
    "that Article 21 must be read with Articles 14 and 19. The passport cannot be "
    "impounded without giving the holder an opportunity of hearing.",

    "The Supreme Court in (1981) 1 SCC 608, Francis Coralie Mullin v Union Territory, "
    "held that the right to life under Article 21 includes the right to live with "
    "basic human dignity.",

    "In Kesavananda Bharati v State of Kerala, AIR 1973 SC 1461, the Court established "
    "the basic structure doctrine — Parliament cannot amend the Constitution to destroy "
    "its basic structure.",
]

citations = extract_citations(sample_draft)
result = verify_citations(citations, RETRIEVED_CHUNKS)

print(f"Draft citations: {citations}")
print(f"citations_verified: {result['citations_verified']}")
print(f"grounded_citations: {result['grounded_citations']}")
print(f"unverified_citations: {result['unverified_citations']}")
print("\n→ 'AIR 2024 SC 9999' is unverified — it never appeared in research_findings.")
print("  LexAgent will flag this or block the output depending on cfg.cite_threshold.")

# ── SECTION 5: How cite node returns to LangGraph ──────────────────────────────
print("""
── Cite node return value (partial dict for LangGraph) ──

  async def run(state: LexState) -> dict:
      draft = state.get("draft_output", "")
      findings = state.get("research_findings", [])

      retriever = HybridRetriever.from_findings(findings)
      chunks = retriever.retrieve(draft, k=10)
      chunk_texts = [c["text"] for c in chunks]

      citations = extract_citations(draft)
      result = verify_citations(citations, chunk_texts)

      return {
          "citations_verified": result["citations_verified"],
          "unverified_citations": result["unverified_citations"],
          "grounded_citations": result["grounded_citations"],
      }
  # Note: returns ONLY changed keys — not the full state
""")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
print("── PAUSE AND THINK ──")
print("""
  1. Open lexagent/nodes/cite.py — what is the _CITATION_RE pattern?
     Does it handle more formats than the one here?

  2. The cite node only checks if the citation STRING appears in chunks.
     Is this enough to prove the citation is correct? What could still go wrong?
     (Hint: what if the case exists but the proposition cited is wrong?)

  3. What does cfg.cite_threshold control? Open lexagent/config.py to find it.
     Should this be higher or lower for a court filing vs an internal memo?

  4. Open lexagent/state.py — find the grounded_citations field.
     What type is it? How does the review node use it?

  5. The cite node in LexAgent (Phase 9 features) also queries Qdrant if
     cfg.qdrant_enabled is True. Why would persistent Qdrant help here compared
     to rebuilding HybridRetriever from research_findings each time?
""")
