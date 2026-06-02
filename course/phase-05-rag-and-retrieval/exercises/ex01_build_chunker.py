"""
Phase 5 — Exercise 1: Build a Parent/Child Chunker

Implement the two chunking functions, then run the test block.
"""

SAMPLE_TEXT = """
The Supreme Court of India in Maneka Gandhi v. Union of India held that the right
to personal liberty under Article 21 of the Constitution is not confined to mere
physical freedom from arrest or detention. The Court overruled the earlier narrow
interpretation in A.K. Gopalan and held that Articles 14, 19, and 21 are not
mutually exclusive but form a cluster of fundamental rights. The procedure
established by law under Article 21 must be right, just, fair, and reasonable,
not arbitrary, fanciful, or oppressive. The passport impounded without hearing
violated the right to travel which is part of personal liberty. This expansive
interpretation has since been followed in Francis Coralie, Olga Tellis, and
numerous other judgments of the Supreme Court and High Courts across India.
The doctrine of audi alteram partem — hear the other side — was elevated as
a fundamental requirement of natural justice embedded within Article 21 itself.
No procedure that is manifestly arbitrary can be called a procedure established
by law. The decision marked a watershed moment in Indian constitutional law.
"""


def chunk_text(text: str, chunk_size: int = 50, overlap: int = 10) -> list[str]:
    """
    Split text into overlapping word-boundary chunks.

    Args:
        text: input text
        chunk_size: target number of words per chunk
        overlap: number of words to repeat between consecutive chunks

    Returns:
        list of chunk strings

    Example with chunk_size=5, overlap=2 on "a b c d e f g h":
        chunk 0: "a b c d e"   (words 0-4)
        chunk 1: "d e f g h"   (words 3-7, overlap of 2)
    """
    # TODO: split text into words, use a sliding window
    # start at 0, step by (chunk_size - overlap) each iteration
    # stop when start >= len(words)
    pass


def create_parent_child_chunks(text: str) -> list[dict]:
    """
    Create parent chunks (large) containing child chunks (small).
    Score on child, retrieve parent for LLM context.

    Uses: parent_size=100 words, child_size=25 words, overlap=5 words

    Each returned dict has:
        child_id:   "p{parent_idx}_c{child_idx}"
        parent_id:  "p{parent_idx}"
        child_text: the small chunk (for BM25/TF-IDF scoring)
        parent_text: the full parent chunk (sent to LLM)
    """
    # TODO:
    # 1. chunk_text(text, 100, 20) to get parents
    # 2. for each parent, chunk_text(parent, 25, 5) to get children
    # 3. build and return the list of dicts
    pass


# ── TESTS ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Test chunk_text
    chunks = chunk_text(SAMPLE_TEXT)
    assert chunks is not None, "chunk_text returned None"
    assert len(chunks) > 1, "Expected multiple chunks"
    assert all(isinstance(c, str) for c in chunks), "All chunks should be strings"
    print(f"✓ chunk_text: {len(chunks)} chunks, first chunk: '{chunks[0][:40]}...'")

    # Verify overlap
    if len(chunks) >= 2:
        words0 = chunks[0].split()
        words1 = chunks[1].split()
        overlap_words = set(words0[-10:]) & set(words1[:10])
        assert len(overlap_words) > 0, "Expected some word overlap between consecutive chunks"
        print(f"✓ Overlap detected: {len(overlap_words)} shared words between chunk 0 and 1")

    # Test create_parent_child_chunks
    pairs = create_parent_child_chunks(SAMPLE_TEXT)
    assert pairs is not None, "create_parent_child_chunks returned None"
    assert len(pairs) > 0, "Expected at least one parent-child pair"

    first = pairs[0]
    assert "child_id" in first, "Missing child_id"
    assert "parent_id" in first, "Missing parent_id"
    assert "child_text" in first, "Missing child_text"
    assert "parent_text" in first, "Missing parent_text"
    assert len(first["child_text"]) < len(first["parent_text"]), \
        "Child should be shorter than parent"

    print(f"✓ create_parent_child_chunks: {len(pairs)} child chunks")
    print(f"  First pair: child_id={first['child_id']}, parent_id={first['parent_id']}")
    print(f"  Child ({len(first['child_text'].split())} words): '{first['child_text'][:40]}...'")
    print(f"  Parent ({len(first['parent_text'].split())} words): '{first['parent_text'][:40]}...'")
    print("\n✅ All tests passed!")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
# 1. Open lexagent/tools/chunker.py — what chunk sizes does it use?
#    Are they word-based or token-based? Why does token count matter for LLMs?
# 2. What happens if SAMPLE_TEXT is shorter than chunk_size words?
#    Does your implementation handle this edge case?
# 3. The overlap ensures citations at chunk boundaries aren't split.
#    What would break if overlap=0 and a citation like "AIR 1978 SC 597" spanned
#    two adjacent chunks?
