"""
Phase 9 — 03: Qdrant Vector Database
======================================
Run:  pip install qdrant-client
      python 03_qdrant_vectors.py
      (uses :memory: mode — no server needed)
"""

import sys
import time

# ── SECTION 1: WHY VECTOR SEARCH ────────────────────────────────────────────
#
# When a LexAgent research node looks for relevant Indian case law, it can't
# use a plain SQL WHERE clause — cases are too long and semantically complex.
#
# Instead we:
#   1. Chunk each case judgment into ~512-token passages.
#   2. Embed each chunk with a text embedding model → a list of floats (a "vector").
#   3. Store the vector + metadata in Qdrant.
#   4. At query time: embed the query → find nearest vectors → retrieve top-k chunks.
#
# Nearest vector = semantically similar text.  SQL can't do this.
#
# In LexAgent: lexagent/tools/retriever.py contains PersistentQdrantRetriever
# which wraps these exact calls.

try:
    from qdrant_client import QdrantClient, models
    QDRANT_AVAILABLE = True
except ImportError:
    print("Install:  pip install qdrant-client")
    print("Running in PRINT-ONLY mode — no actual Qdrant calls.\n")
    QDRANT_AVAILABLE = False


# ── SECTION 2: CREATING A CLIENT ─────────────────────────────────────────────
#
# Three modes:
#
#   QdrantClient(":memory:")          ← in-process, no server, data lost on exit
#   QdrantClient("http://localhost:6333")  ← local Qdrant Docker
#   QdrantClient(url="...", api_key="...")  ← Qdrant Cloud
#
# WHY :memory: for dev?
#   No Docker, no ports, no setup.  Identical Python API to the cloud client.
#   LexAgent uses :memory: when QDRANT_URL is unset (see lexagent/config.py).

def make_client() -> "QdrantClient | None":
    if not QDRANT_AVAILABLE:
        return None
    client = QdrantClient(":memory:")
    print("Qdrant client created — mode: :memory:")
    return client


# ── SECTION 3: COLLECTIONS ────────────────────────────────────────────────────
#
# A Qdrant "collection" is like a table: it holds vectors of a fixed dimension
# and a chosen distance metric.
#
# Key params:
#   size      — vector dimension (must match your embedding model's output)
#               OpenAI text-embedding-3-small → 1536
#               Sentence-transformers all-MiniLM → 384
#               Our fake vectors below → 10
#   distance  — COSINE (angle), DOT (magnitude), EUCLID (L2)
#               Cosine is standard for text similarity.
#
# Per-matter naming: f"{firm_id}_{matter_id}"
#   • firm_a_m001 contains only Firm A's matter 001 chunks.
#   • firm_b_m001 is completely separate — no cross-contamination.
#
# WHY per-matter instead of one global collection?
#   • Delete a matter → drop one collection (fast, clean).
#   • Billing per firm is straightforward.
#   • Search scope is naturally limited — no risk of returning another firm's docs.

def create_collection(client: "QdrantClient", collection_name: str,
                      vector_size: int = 10) -> None:
    """Create a Qdrant collection for one matter."""
    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=models.Distance.COSINE,
        ),
    )
    print(f"Collection created: '{collection_name}' (dim={vector_size}, cosine)")


# ── SECTION 4: UPSERTING POINTS ───────────────────────────────────────────────
#
# A "point" is one record in Qdrant:
#   id      — integer or UUID, must be unique within the collection
#   vector  — list of floats (length == collection's vector size)
#   payload — arbitrary JSON dict (case citation, date, court, text snippet...)
#
# `upsert` = insert or update.  Safe to call multiple times with the same id.
#
# In production (lexagent/tools/retriever.py):
#   vector = embedding_model.embed(chunk_text)   ← real 1536-dim float list
#   client.upsert(collection_name, points=[
#       models.PointStruct(id=chunk_id, vector=vector, payload={"text": chunk_text, ...})
#   ])

# Fake 10-dimensional vectors for teaching.
# Pattern: [i*0.1, (i+1)*0.1, ...] — easy to reason about without a GPU.
CASE_CHUNKS = [
    {
        "id": 1,
        "text": "The Supreme Court held in Maneka Gandhi v Union of India that personal liberty cannot be curtailed without a fair procedure.",
        "citation": "Maneka Gandhi v UoI, AIR 1978 SC 597",
        "court": "Supreme Court",
        "year": 1978,
    },
    {
        "id": 2,
        "text": "Bail is the rule and jail is the exception — established in State of Rajasthan v Balchand.",
        "citation": "State of Rajasthan v Balchand, (1977) 4 SCC 308",
        "court": "Supreme Court",
        "year": 1977,
    },
    {
        "id": 3,
        "text": "In Arnesh Kumar v State of Bihar, the Supreme Court restricted automatic arrests under Section 498A IPC.",
        "citation": "Arnesh Kumar v State of Bihar, (2014) 8 SCC 273",
        "court": "Supreme Court",
        "year": 2014,
    },
    {
        "id": 4,
        "text": "Article 21 protects not just physical liberty but the right to live with dignity — Francis Coralie Mullin v UT Delhi.",
        "citation": "Francis Coralie Mullin v UT Delhi, AIR 1981 SC 746",
        "court": "Supreme Court",
        "year": 1981,
    },
    {
        "id": 5,
        "text": "Section 437 CrPC — grounds for bail for non-bailable offences including health, age, and nature of accusation.",
        "citation": "Section 437 CrPC",
        "court": "Statute",
        "year": 1973,
    },
]


def fake_vector(seed: int, size: int = 10) -> list[float]:
    """
    Generate a reproducible fake vector from an integer seed.
    In production this is replaced by an embedding model call.

    WHY this formula?
      It's simple, deterministic, and creates vectors that differ from each other —
      good enough to demonstrate nearest-neighbour search.
    """
    return [(seed * 0.1 + i * 0.05) % 1.0 for i in range(size)]


def upsert_chunks(client: "QdrantClient", collection_name: str) -> None:
    """Insert all 5 case chunks into the collection."""
    points = [
        models.PointStruct(
            id=chunk["id"],
            vector=fake_vector(chunk["id"]),
            payload={
                "text": chunk["text"],
                "citation": chunk["citation"],
                "court": chunk["court"],
                "year": chunk["year"],
            },
        )
        for chunk in CASE_CHUNKS
    ]
    client.upsert(collection_name=collection_name, points=points)
    print(f"Upserted {len(points)} case chunks into '{collection_name}'")


# ── SECTION 5: SEARCHING ──────────────────────────────────────────────────────
#
# `client.search(collection_name, query_vector, limit)` returns the `limit`
# nearest neighbours, sorted by similarity score (highest first).
#
# The score is the cosine similarity: 1.0 = identical, 0.0 = orthogonal.
#
# In production (lexagent/tools/retriever.py):
#   query_vector = embedding_model.embed(user_query)
#   results = client.search(collection_name, query_vector=query_vector, limit=5)
#   context_chunks = [r.payload["text"] for r in results]
#   # inject context_chunks into the draft node's system prompt

def search_chunks(client: "QdrantClient", collection_name: str,
                  query_seed: int = 3, top_k: int = 3) -> list:
    """Search for top_k chunks nearest to a fake query vector."""
    query_vector = fake_vector(query_seed)
    results = client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=top_k,
    )
    return results


# ── SECTION 6: FULL LIVE DEMO ─────────────────────────────────────────────────

def run_demo() -> None:
    client = make_client()
    if client is None:
        print("No Qdrant client — install qdrant-client to run the demo.")
        return

    COLLECTION = "firm_a_matter_001"

    # Step 1: create collection
    print("\n── Step 1: Create collection ──")
    create_collection(client, COLLECTION, vector_size=10)

    # Step 2: upsert 5 case chunks
    print("\n── Step 2: Upsert 5 case chunks ──")
    upsert_chunks(client, COLLECTION)

    # Step 3: search
    print("\n── Step 3: Search (query_seed=3, top_k=3) ──")
    results = search_chunks(client, COLLECTION, query_seed=3, top_k=3)
    print(f"Top {len(results)} results:")
    for i, hit in enumerate(results, 1):
        print(f"  {i}. score={hit.score:.4f}  citation='{hit.payload['citation']}'")
        print(f"     text='{hit.payload['text'][:80]}...'")

    # Step 4: demonstrate per-matter isolation
    print("\n── Step 4: Per-matter isolation demo ──")
    COLLECTION_2 = "firm_b_matter_099"
    create_collection(client, COLLECTION_2, vector_size=10)
    # firm_b's collection is empty — no cross-contamination
    results_b = client.search(
        collection_name=COLLECTION_2,
        query_vector=fake_vector(3),
        limit=3,
    )
    print(f"  firm_b_matter_099 results: {len(results_b)} (expected 0 — empty collection)")

    print("\n── Demo complete ──")


if __name__ == "__main__":
    run_demo()


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
#
# 1. Open lexagent/tools/retriever.py.
#    What class wraps the Qdrant client?  Does it use `:memory:` or a server URL?
#    Which config field controls the choice?
#
# 2. The demo uses 10-dimensional fake vectors.
#    The real retriever uses an embedding model.
#    What dimension does your current embedding model produce?
#    (Hint: search for `embedding` in lexagent/config.py or retriever.py.)
#
# 3. We use `models.Distance.COSINE`.
#    When would you choose DOT product distance instead?
#    (Hint: think about normalised vs. unnormalised embeddings.)
#
# 4. `client.upsert()` vs `client.upload_points()` — both insert points.
#    When is upsert safer?  What happens if you call upsert twice with the
#    same point id but a different vector?
#
# 5. The collection name is `f"{firm_id}_{matter_id}"`.
#    What happens to the Qdrant collection when a matter is deleted in
#    the control plane?  Is there a delete-collection call in retriever.py?
#    If not, what accumulates over time?
