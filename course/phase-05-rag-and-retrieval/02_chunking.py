"""
Phase 05 — RAG and Retrieval
File 02: Chunking — Breaking Judgments into Retrievable Pieces

Run: python 02_chunking.py
No external dependencies required.
"""

# ── SECTION 1: WHY CHUNK ──────────────────────────────────────────────────────
#
# A Supreme Court judgment can be 50,000 words. GPT-4 / Claude have context
# windows of ~100K tokens — but filling the entire window with one judgment
# means NO room for the lawyer's question, system prompt, or the actual draft.
#
# More importantly: if you stuff 50,000 words in, the LLM will "lose" the
# relevant passage in the noise. Precision drops. Cost explodes.
#
# The solution: break each judgment into CHUNKS, score each chunk against
# the lawyer's query, and only include the TOP-K chunks in the prompt.
# A 256-word chunk is ~350 tokens. Top-5 chunks = ~1,750 tokens. Manageable.

print("=" * 70)
print("SECTION 1: Why Chunk — Context Window is NOT Free")
print("=" * 70)

JUDGMENT_WORD_COUNT = 45_000
CHUNK_SIZE = 256
OVERLAP = 50
NUM_CHUNKS = (JUDGMENT_WORD_COUNT - OVERLAP) // (CHUNK_SIZE - OVERLAP)

print(f"""
  Full judgment word count : ~{JUDGMENT_WORD_COUNT:,}
  Full judgment token count: ~{JUDGMENT_WORD_COUNT * 1.3:.0f} (1.3 tokens per word)
  Top-5 chunks token count : ~{5 * CHUNK_SIZE * 1.3:.0f}

  Chunks we'd create from one judgment (size={CHUNK_SIZE}, overlap={OVERLAP}):
    ≈ {NUM_CHUNKS} chunks

  We score ALL {NUM_CHUNKS} and include only TOP 5 in the LLM prompt.
  Cost reduction: ~{NUM_CHUNKS / 5:.0f}x fewer tokens to the LLM.
""")


# ── SECTION 2: NAIVE CHUNKING (BAD) ───────────────────────────────────────────
#
# The simplest approach: split every N characters. Fast. Terrible.
# "personal libert" + "y under Article" — the word "liberty" is cut in half.
# Citation "AIR 1978 SC" gets split from its volume "597" in the next chunk.
# Retrieval will MISS this chunk when searching for "AIR 1978 SC 597".

print("=" * 70)
print("SECTION 2: Naive Character Splitting — Why It Breaks Citations")
print("=" * 70)

SAMPLE = "The right to personal liberty under Article 21 AIR 1978 SC 597 cannot be curtailed without fair procedure."
CHAR_SIZE = 40

naive_chunks = [SAMPLE[i : i + CHAR_SIZE] for i in range(0, len(SAMPLE), CHAR_SIZE)]

print("\n[Naive character split — chunk_size=40]")
for i, chunk in enumerate(naive_chunks):
    print(f"  chunk[{i}]: '{chunk}'")

print(f"\n  Notice: 'AIR 1978 SC' is in chunk[2], '597' is in chunk[3].")
print(f"  A query for 'AIR 1978 SC 597' will MISS both chunks individually.")


# ── SECTION 3: SENTENCE-BOUNDARY CHUNKING WITH OVERLAP ────────────────────────
#
# Better strategy: split on WORD boundaries and carry OVERLAP between chunks.
# Overlap means a citation that falls near a chunk boundary appears in TWO
# consecutive chunks. At least one of them will score well on retrieval.

print("\n" + "=" * 70)
print("SECTION 3: Word-Boundary Chunking With Overlap")
print("=" * 70)


def chunk_text(text: str, chunk_size: int = 256, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks of roughly chunk_size words.

    WHY overlap: a citation near a chunk boundary appears in both the
    preceding and following chunk, so retrieval doesn't miss it.
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        # WHY chunk_size - overlap: advance by stride = chunk_size - overlap
        # so the next chunk starts overlap words before this chunk ended.
        start += chunk_size - overlap
    return chunks


# Demo on short text to show overlap clearly
SHORT = (
    "The Supreme Court held in Maneka Gandhi v Union of India AIR 1978 SC 597 "
    "that personal liberty cannot be curtailed. "
    "This was applied in Francis Coralie v Delhi AIR 1981 SC 746 to extend "
    "the right to live with dignity. "
    "Later in Olga Tellis v BMC 1985 SCC the right to livelihood was recognised."
)

small_chunks = chunk_text(SHORT, chunk_size=20, overlap=5)
print("\n[chunk_size=20 words, overlap=5 words]")
for i, c in enumerate(small_chunks):
    print(f"  chunk[{i}]: {c}")


# ── SECTION 4: PARENT / CHILD PATTERN ─────────────────────────────────────────
#
# Problem with small chunks: they score well (precise retrieval) but give
# the LLM too little context to understand the holding.
#
# Solution: TWO chunk sizes.
#   Child  (256 words): used for BM25 / TF-IDF SCORING. Small = precise.
#   Parent (1024 words): given to the LLM as CONTEXT after the child scores.
#
# Every child knows its parent. Retrieval returns child score → parent text.
# This is the "parent-document retriever" pattern from LangChain / LlamaIndex.

print("\n" + "=" * 70)
print("SECTION 4: Parent / Child Pattern — Score Small, Read Large")
print("=" * 70)

print("""
  ┌──────────────────────────────────────────────────────┐
  │  Parent chunk (1024 words) — given to LLM            │
  │  ┌────────────┐  ┌────────────┐  ┌────────────┐      │
  │  │ child[0]   │  │ child[1]   │  │ child[2]   │ ...  │
  │  │ 256 words  │  │ 256 words  │  │ 256 words  │      │
  │  └────────────┘  └────────────┘  └────────────┘      │
  │     ↑ scored against query                           │
  └──────────────────────────────────────────────────────┘

  Query hits child[1] (score 0.87) → retrieve parent → LLM reads 1024 words
""")


def create_parent_child_chunks(text: str) -> list[dict]:
    """Create parent chunks (1024 words) containing child chunks (256 words).

    Each child dict has:
      child_id    — unique id like p0_c1
      parent_id   — which parent this child belongs to
      child_text  — small chunk for BM25/TF-IDF scoring
      parent_text — large chunk returned to the LLM
    """
    parents = chunk_text(text, chunk_size=1024, overlap=100)
    result = []
    for pi, parent in enumerate(parents):
        children = chunk_text(parent, chunk_size=256, overlap=50)
        for ci, child in enumerate(children):
            result.append(
                {
                    "child_id": f"p{pi}_c{ci}",
                    "parent_id": f"p{pi}",
                    "child_text": child,
                    "parent_text": parent,
                }
            )
    return result


# ── SECTION 5: LIVE DEMO ───────────────────────────────────────────────────────

print("=" * 70)
print("SECTION 5: Live Demo — Chunk a Sample Judgment")
print("=" * 70)

SAMPLE_JUDGMENT = (
    "In the matter of Maneka Gandhi versus Union of India the Supreme Court "
    "of India delivered a landmark judgment in 1978. "
    "The petitioner's passport had been impounded by the Government without "
    "providing any reasons or opportunity of hearing. "
    "The Court held unanimously that the right to travel abroad is part of "
    "personal liberty guaranteed under Article 21 of the Constitution. "
    "The procedure established by law must be fair just and reasonable. "
    "Justice P N Bhagwati writing for himself observed that Article 21 must "
    "be read together with Articles 14 and 19. "
    "The golden triangle principle was thus established. "
    "The earlier restrictive view in A K Gopalan AIR 1950 SC 27 was overruled. "
    "This judgment fundamentally reshaped fundamental rights jurisprudence. "
    "The right to life cannot be interpreted narrowly. "
    "Every limb of Article 21 must be given its full content. "
) * 3  # Repeat to simulate a longer text

chunks_pc = create_parent_child_chunks(SAMPLE_JUDGMENT)

print(f"\n  Sample text word count : {len(SAMPLE_JUDGMENT.split())}")
print(f"  Parent chunks created  : {len(set(c['parent_id'] for c in chunks_pc))}")
print(f"  Child chunks total     : {len(chunks_pc)}")

print("\n  [First child chunk]")
first = chunks_pc[0]
print(f"    child_id  : {first['child_id']}")
print(f"    parent_id : {first['parent_id']}")
print(f"    child_text: {first['child_text'][:120]}...")
print(f"    parent len: {len(first['parent_text'].split())} words")


# ── PAUSE AND THINK ────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("PAUSE AND THINK — before moving to 03_bm25.py")
print("=" * 70)
print("""
  1. Open lexagent/tools/chunker.py. Does LexAgent use fixed-size or
     sentence-boundary chunking? What is the default chunk_size?

  2. Why is the overlap set to 50 words and not 128 (50% of chunk)?
     What happens to retrieval quality as overlap increases toward chunk_size?

  3. In the parent/child pattern, if two children from DIFFERENT parents
     both score highly for the same query, do we return both parents?
     How does LexAgent handle deduplication?

  4. Indian judgments often have numbered paragraphs (¶1, ¶2...). Could
     paragraph boundaries be better split points than word counts? What
     would you need to detect paragraph boundaries reliably?

  5. How would you chunk a PDF that has headers, footnotes, and a table
     of cases? Should all of these be chunked the same way?
""")
