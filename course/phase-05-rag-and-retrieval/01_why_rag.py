"""
Phase 05 — RAG and Retrieval
File 01: Why RAG? The Hallucination Problem in Legal AI

Run: python 01_why_rag.py
No external dependencies required.
"""

# ── SECTION 1: LLM HALLUCINATION PROBLEM ──────────────────────────────────────
#
# Large language models are trained on text scraped from the internet.
# They learn PATTERNS — how legal language looks, how citations are formatted.
# But they were NOT trained to memorise every case ever decided.
#
# The result: when asked to cite cases, LLMs INVENT citations that look real.
# This is called hallucination. In law, an invented citation is malpractice.

print("=" * 70)
print("SECTION 1: The Hallucination Problem")
print("=" * 70)

HALLUCINATED_DRAFT = """
...The right to personal liberty under Article 21 is well settled.
In Ram Prasad v Union of India AIR 2001 SC 1142, the Supreme Court held
that detention without hearing violates natural justice. This was affirmed
in Sharma v State of Bihar SCC 1999 Vol 3 at 440...
"""

print("\n[DRAFT FROM VANILLA LLM — NO RAG]")
print(HALLUCINATED_DRAFT)
print("Problem: 'AIR 2001 SC 1142' and 'SCC 1999 Vol 3 440' do not exist.")
print("A lawyer submitting this faces a Bar Council disciplinary proceeding.\n")


# ── SECTION 2: RAG PIPELINE OVERVIEW ──────────────────────────────────────────
#
# RAG = Retrieval-Augmented Generation.
# Instead of asking the LLM to remember cases, we RETRIEVE relevant chunks
# from a trusted corpus FIRST, then give those chunks to the LLM as context.
#
# LexAgent pipeline:
#   intake → research → [chunk → score → retrieve] → draft → cite → review
#                           ↑ RAG lives here ↑
#
# The LLM's job becomes simpler: "summarise and format what I gave you"
# rather than "recall and invent from memory."

print("=" * 70)
print("SECTION 2: RAG Pipeline — Research Findings → Verified Draft")
print("=" * 70)

PIPELINE_STEPS = [
    ("1. Research", "Kanoon scraper fetches top-N case texts for the matter"),
    ("2. Chunk",    "Each judgment split into 256-word child chunks"),
    ("3. Score",    "BM25 + TF-IDF hybrid ranks chunks against query"),
    ("4. Retrieve", "Top-K chunks selected as context window"),
    ("5. Draft",    "LLM drafts with retrieved chunks in system prompt"),
    ("6. Cite",     "Citation extractor checks every citation against chunks"),
    ("7. Review",   "Risk annotations added; unverified citations flagged"),
]

for step, desc in PIPELINE_STEPS:
    print(f"  {step:12s} → {desc}")


# ── SECTION 3: INDIAN LAW SPECIFIC REASONS ────────────────────────────────────
#
# Three reasons RAG matters MORE for Indian law than for US/UK law:
#
# 1. CITATION COMPLEXITY: Indian citations have multiple parallel reporters.
#    "Maneka Gandhi" appears as AIR 1978 SC 597 AND (1978) 1 SCC 248 AND
#    [1978] 2 SCR 621. LLMs confuse these endlessly.
#
# 2. TRAINING DATA SCARCITY: Pre-2010 Indian judgments are underrepresented
#    in Common Crawl. The model never saw most High Court decisions.
#
# 3. EVOLVING DOCTRINE: Constitutional doctrine post-Puttaswamy (2017)
#    changed rapidly. Models trained before 2023 don't know the later cases.

print("\n" + "=" * 70)
print("SECTION 3: Why Indian Law Needs RAG More Than US/UK Law")
print("=" * 70)

REASONS = {
    "Citation complexity": (
        "AIR, SCC, SCR, MLJ, ILR — multiple reporters for the same case. "
        "LLMs mix reporter codes and volume numbers constantly."
    ),
    "Training data gap": (
        "Most pre-2010 High Court judgments are NOT in Common Crawl. "
        "The LLM genuinely has no memory of them."
    ),
    "Rapidly evolving doctrine": (
        "Post-Puttaswamy (2017), right to privacy reshaped Article 21. "
        "Models freeze at training cutoff; retrieved corpus is current."
    ),
}

for reason, explanation in REASONS.items():
    print(f"\n  [{reason}]")
    print(f"  {explanation}")


# ── SECTION 4: THE CITATION GATE ──────────────────────────────────────────────
#
# After the LLM produces a draft, LexAgent runs a CITATION GATE:
#   - Extract every citation from the draft using a regex
#   - For each citation, check: does this string appear in a retrieved chunk?
#   - If yes → grounded. If no → flag as unverified.
#
# The gate does NOT validate the legal HOLDING — only that the citation
# string came from a document we actually fetched. A human lawyer still
# reads the case. But at least the citation EXISTS.

print("\n" + "=" * 70)
print("SECTION 4: The Citation Gate")
print("=" * 70)

print("""
  [Draft produced]
       ↓
  extract_citations()   →   ['AIR 1978 SC 597', 'AIR 2001 SC 1142']
       ↓
  for each citation:
       is it in retrieved_chunks?
           YES  →  grounded_citations['AIR 1978 SC 597'] = 'chunk_match'
           NO   →  unverified_citations.append('AIR 2001 SC 1142')
       ↓
  if unverified_citations:
       citations_verified = False
       append warning to draft
""")


# ── SECTION 5: DEMO — BAD DRAFT VS RAG-GROUNDED DRAFT ────────────────────────

print("=" * 70)
print("SECTION 5: Bad Draft vs RAG-Grounded Draft")
print("=" * 70)

BAD_DRAFT = (
    "The petitioner's right to travel is protected under Article 21. "
    "See Ram Prasad v UOI AIR 2001 SC 1142 and Sharma v Bihar SCC 1999 440."
)

RETRIEVED_CHUNK = (
    "Maneka Gandhi v Union of India AIR 1978 SC 597: The Supreme Court held "
    "that the right to travel abroad is a facet of personal liberty under "
    "Article 21 and cannot be curtailed without a fair and reasonable procedure."
)

RAG_DRAFT = (
    "The petitioner's right to travel is protected under Article 21. "
    "In Maneka Gandhi v Union of India AIR 1978 SC 597, the Supreme Court held "
    "that the right to travel abroad is a facet of personal liberty and cannot "
    "be curtailed without a fair procedure established by law."
)

print("\n[BAD DRAFT — citations invented]")
print(f"  {BAD_DRAFT}")

print("\n[RETRIEVED CHUNK — from Indian Kanoon]")
print(f"  {RETRIEVED_CHUNK}")

print("\n[RAG-GROUNDED DRAFT — citation traceable to chunk]")
print(f"  {RAG_DRAFT}")

# Simple verification demo
citations_bad = ["AIR 2001 SC 1142", "SCC 1999 440"]
citations_good = ["AIR 1978 SC 597"]

print("\n[Citation gate results]")
for c in citations_bad:
    found = c in RETRIEVED_CHUNK
    print(f"  {'✓' if found else '✗'} {c:30s} → {'grounded' if found else 'UNVERIFIED — flag for lawyer'}")
for c in citations_good:
    found = c in RETRIEVED_CHUNK
    print(f"  {'✓' if found else '✗'} {c:30s} → {'grounded' if found else 'UNVERIFIED'}")


# ── PAUSE AND THINK ────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("PAUSE AND THINK — before moving to 02_chunking.py")
print("=" * 70)
print("""
  1. Open lexagent/nodes/cite.py. Which function extracts citations?
     What regex pattern does it use? Does it handle both AIR and SCC formats?

  2. Open lexagent/tools/retriever.py. At what point does retrieval happen —
     before drafting, during drafting, or after? Trace the call from research node.

  3. Why does the citation gate check string presence rather than semantic
     similarity? When would semantic similarity be better?

  4. What happens when a valid case has multiple reporter citations
     (AIR 1978 SC 597 vs (1978) 1 SCC 248) and the draft uses one format
     but the retrieved chunk uses the other? How would you fix this?

  5. The pipeline fetches chunks before drafting. But the lawyer's query
     changes as drafting proceeds. How would you handle mid-draft retrieval?
""")
