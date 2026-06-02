"""
Phase 9 — Exercise 2: Store and Retrieve Embeddings with Qdrant

Uses in-memory Qdrant — no server needed.
# pip install qdrant-client
"""
try:
    from qdrant_client import QdrantClient
    from qdrant_client import models
except ImportError:
    print("Install: pip install qdrant-client")
    raise SystemExit(1)

import random

# ── Sample data ───────────────────────────────────────────────────────────────
CASE_CHUNKS = [
    {"id": 1, "text": "Maneka Gandhi Article 21 personal liberty passport impound hearing",
     "case": "Maneka Gandhi v. UOI", "citation": "AIR 1978 SC 597"},
    {"id": 2, "text": "Kesavananda basic structure constitutional amendment Parliament limits",
     "case": "Kesavananda Bharati v. Kerala", "citation": "AIR 1973 SC 1461"},
    {"id": 3, "text": "Olga Tellis right to livelihood Article 21 pavement dwellers eviction",
     "case": "Olga Tellis v. BMC", "citation": "1985 SCC 545"},
    {"id": 4, "text": "Francis Coralie dignity bare necessities right to live Article 21",
     "case": "Francis Coralie v. Delhi", "citation": "1981 SC 608"},
    {"id": 5, "text": "Gopalan preventive detention procedure established by law Article 21 narrow",
     "case": "A.K. Gopalan v. Madras", "citation": "AIR 1950 SC 27"},
]


def make_fake_vector(text: str, dim: int = 10) -> list[float]:
    """
    Create a deterministic fake vector from text.
    (In production: use a real embedding model like text-embedding-3-small)
    Not random — same text always → same vector (important for reproducibility).
    """
    random.seed(hash(text) % (2**32))
    return [random.uniform(0.0, 1.0) for _ in range(dim)]


# ── TODO 1: Create a Qdrant client and collection ─────────────────────────────
# - Create an in-memory client: QdrantClient(":memory:")
# - Collection name: "matter_001_writ" (simulates firm_id=matter_001, topic=writ)
# - Vector config: size=10, distance=models.Distance.COSINE
# - Handle AlreadyExists gracefully (the collection might already exist in tests)

# TODO: create client and collection here
client = None  # replace with real client


# ── TODO 2: Upsert the 5 case chunks ─────────────────────────────────────────
# - For each chunk in CASE_CHUNKS:
#   - Generate vector with make_fake_vector(chunk["text"])
#   - Create models.PointStruct(id=chunk["id"], vector=vector, payload=chunk)
# - Call client.upsert(collection_name, points=[...])
# - Print "Upserted N points to collection"

COLLECTION_NAME = "matter_001_writ"

# TODO: upsert all 5 chunks here


# ── TODO 3: Search the collection ─────────────────────────────────────────────
# - Create a query vector for "Article 21 personal liberty dignity"
#   using make_fake_vector()
# - Call client.search(COLLECTION_NAME, query_vector=..., limit=3)
# - Print the top 3 results showing: case name, citation, score

# TODO: search and print top 3 results here


# ── TODO 4: Demonstrate per-matter isolation ──────────────────────────────────
# - Create a SECOND collection named "matter_002_contract"
# - Upsert 1 point: {"id": 10, "text": "arbitration clause seat venue SIAC ICC"}
# - Search "arbitration" in matter_001_writ — should return 0 relevant results
# - Search "arbitration" in matter_002_contract — should return the 1 result
# - Print: "Isolation confirmed: matter_001 search returned N results, matter_002 returned M"

# TODO: implement isolation demo here


# ── TESTS ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Verify client was created
    assert client is not None, "Create the Qdrant client (replace None)"

    # Verify collection exists
    collections = client.get_collections().collections
    names = [c.name for c in collections]
    assert COLLECTION_NAME in names, f"Collection '{COLLECTION_NAME}' not found. Create it in TODO 1."
    print(f"✓ Collection '{COLLECTION_NAME}' exists")

    # Verify upsert worked
    count = client.count(COLLECTION_NAME).count
    assert count == 5, f"Expected 5 points, got {count}. Complete TODO 2."
    print(f"✓ {count} points in collection")

    # Verify search works
    query_vec = make_fake_vector("Article 21 personal liberty")
    results = client.search(COLLECTION_NAME, query_vector=query_vec, limit=3)
    assert len(results) == 3, f"Expected 3 search results, got {len(results)}"
    assert all(hasattr(r, "score") for r in results), "Results should have .score attribute"
    print(f"✓ Search returned {len(results)} results")
    for r in results:
        print(f"  Score {r.score:.3f}: {r.payload.get('case', 'unknown')}")

    # Verify isolation (if TODO 4 implemented)
    if "matter_002_contract" in names:
        results2 = client.search("matter_002_contract", query_vector=make_fake_vector("arbitration"), limit=3)
        print(f"✓ matter_002_contract has {len(results2)} results for 'arbitration'")

    print("\n✅ All tests passed!")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
# 1. Open lexagent/tools/retriever.py — find PersistentQdrantRetriever.
#    How does it decide the collection_name? Does it use firm_id + matter_id?
# 2. make_fake_vector uses random.seed(hash(text)). What breaks if you use
#    truly random vectors? Try changing to random.random() and rerun — do the
#    search results make sense?
# 3. In production, you'd use a real embedding model. The vector dimension must
#    match the collection's size. What happens if you upsert a 384-dim vector
#    into a collection created with size=10?
