# Hybrid BM25 + TF-IDF vector retriever with parent/child chunk hierarchy.
#
# Two retrieval paths fused at rerank time:
#   BM25  — exact keyword match, critical for Indian citation strings
#           like "AIR 1978 SC 597" that semantic search degrades on.
#   TF-IDF cosine — lightweight vector similarity for doctrine/concept queries.
#
# Weighted fusion: score = α * bm25 + (1-α) * vector
#
# Child/parent hierarchy (5d):
#   Child chunks (small, ≤256 tokens) are used for precise match scoring.
#   Parent chunks (large, ≤1024 tokens) go into the LLM context window.
#   The retriever returns (child_chunk, parent_chunk) pairs so callers can
#   use the exact match for grounding and the parent for generation context.

from __future__ import annotations

from typing import NamedTuple

import numpy as np
from rank_bm25 import BM25Okapi  # type: ignore[import]
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import]
from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import]

from themis.tools.chunker import Chunk, chunk_text
from themis.tools.query_expander import expand_query


class RetrievalResult(NamedTuple):
    child: Chunk        # Small chunk used for match scoring and citation grounding
    parent: Chunk       # Larger chunk passed to the LLM for generation context
    score: float        # Fused retrieval score
    bm25_score: float
    vector_score: float


class HybridRetriever:
    """
    Build indexes from a corpus of text strings, then retrieve the
    top-k most relevant (child, parent) chunk pairs for a query.

    Usage:
        retriever = HybridRetriever.from_findings(research_findings, cfg)
        results = retriever.retrieve("injunction property dispute", top_k=5)
    """

    def __init__(
        self,
        child_chunks: list[Chunk],
        parent_chunks: list[Chunk],
        bm25_weight: float = 0.4,
        similarity_threshold: float = 0.35,
        query_expansion: bool = True,
    ) -> None:
        self._children = child_chunks
        self._parents = parent_chunks
        self._bm25_weight = bm25_weight
        self._threshold = similarity_threshold
        self._query_expansion = query_expansion

        child_texts = [c.chunk_text for c in child_chunks]

        # WHY: BM25Okapi raises ZeroDivisionError on an empty corpus.
        # Guard here so callers can construct a retriever on empty findings
        # and get back empty results gracefully.
        if child_texts:
            tokenised = [t.lower().split() for t in child_texts]
            self._bm25: BM25Okapi | None = BM25Okapi(tokenised)
        else:
            self._bm25 = None

        # TF-IDF vector index over child chunks
        # WHY: TF-IDF + cosine is lightweight, offline, and robust for legal prose.
        # It can be swapped for a proper embedding model later without changing
        # the retriever interface — just replace this block.
        self._vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),   # unigrams + bigrams capture Indian citation phrases
            sublinear_tf=True,
            min_df=1,
        )
        if child_texts:
            self._tfidf_matrix = self._vectorizer.fit_transform(child_texts)
        else:
            self._tfidf_matrix = None

    @classmethod
    def from_findings(
        cls,
        findings: list[dict],
        bm25_weight: float = 0.4,
        similarity_threshold: float = 0.35,
        child_max_tokens: int = 256,
        parent_max_tokens: int = 1024,
        query_expansion: bool = True,
    ) -> "HybridRetriever":
        """
        Build a retriever from research_findings dicts.
        Each finding may have: full_text, header, snippet, citation, case_name.
        """
        child_chunks: list[Chunk] = []
        parent_chunks: list[Chunk] = []

        for finding in findings:
            source = finding.get("citation") or finding.get("case_name") or "unknown"
            body = (
                finding.get("full_text")
                or finding.get("header", "") + "\n" + finding.get("snippet", "")
            ).strip()
            if not body:
                continue

            children = chunk_text(body, source_doc=source, max_tokens=child_max_tokens)
            parents = chunk_text(body, source_doc=source, max_tokens=parent_max_tokens)

            # Map each child to its parent by position
            # WHY: Parents cover the same text at coarser granularity.
            # A child at index i maps to the parent that contains the same region.
            # Simple heuristic: parent_index = child_index // ratio.
            ratio = max(1, len(children) // max(1, len(parents)))
            for i, child in enumerate(children):
                parent_idx = min(i // ratio, len(parents) - 1)
                parent = parents[parent_idx]
                # Copy parent text into the child chunk for easy access
                child.parent_text = parent.chunk_text
                child_chunks.append(child)
                parent_chunks.append(parent)

        return cls(child_chunks, parent_chunks, bm25_weight, similarity_threshold, query_expansion)

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """Return up to top_k (child, parent) pairs ranked by fused score."""
        if not self._children or self._bm25 is None:
            return []

        bm25_scores = self._bm25_scores(query)
        vector_scores = self._vector_scores(query)

        # Weighted fusion
        fused = (
            self._bm25_weight * bm25_scores
            + (1 - self._bm25_weight) * vector_scores
        )

        # Filter by threshold, then take top_k
        indices = np.where(fused >= self._threshold)[0]
        if len(indices) == 0:
            # WHY: Fall back to top_k without threshold when nothing passes —
            # better to return weak matches than nothing in the cite node.
            indices = np.argsort(fused)[::-1][:top_k]
        else:
            indices = indices[np.argsort(fused[indices])[::-1]][:top_k]

        results: list[RetrievalResult] = []
        for i in indices:
            child = self._children[i]
            parent = self._parents[i]
            results.append(RetrievalResult(
                child=child,
                parent=parent,
                score=float(fused[i]),
                bm25_score=float(bm25_scores[i]),
                vector_score=float(vector_scores[i]),
            ))
        return results

    async def retrieve_reranked(
        self,
        query: str,
        top_k: int = 5,
        reranker=None,
    ) -> list[RetrievalResult]:
        """
        Retrieve then optionally re-rank using an LLMReranker.

        WHY separate method instead of modifying retrieve():
            retrieve() is synchronous and used in many places. Async re-ranking
            is opt-in and requires an await, so keeping it separate avoids
            forcing all callers to become async just for an optional feature.
        """
        # Fetch a wider candidate pool so the re-ranker has more to work with
        candidates = self.retrieve(query, top_k=top_k * 2)
        if reranker is None or not candidates:
            return candidates[:top_k]
        return await reranker.rerank(query, candidates)

    def _bm25_scores(self, query: str) -> np.ndarray:
        # WHY: expand_query() adds Indian legal synonyms before exact-match BM25
        # scoring so "injunction" also matches "ad interim stay" in the corpus.
        effective_query = expand_query(query) if self._query_expansion else query
        scores = np.array(self._bm25.get_scores(effective_query.lower().split()), dtype=float)  # type: ignore[union-attr]
        # Normalise to [0, 1]
        max_s = scores.max()
        return scores / max_s if max_s > 0 else scores

    def _vector_scores(self, query: str) -> np.ndarray:
        n = len(self._children)
        if self._tfidf_matrix is None or n == 0:
            return np.zeros(n)
        q_vec = self._vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self._tfidf_matrix).flatten()
        return sims


class PersistentQdrantRetriever:
    """
    Dense vector retriever backed by Qdrant for per-matter persistent storage.

    WHY: HybridRetriever is rebuilt from scratch each session — all Kanoon
    findings are discarded on restart. PersistentQdrantRetriever stores
    embeddings in a Qdrant collection keyed by matter_id so knowledge
    accumulates across sessions and bot restarts.

    Collection naming: "{firm_id}_matter_{matter_id}" for tenant isolation.
    Falls back to in-memory HybridRetriever if Qdrant is unreachable.
    """

    def __init__(self, matter_id: str, firm_id: str = "default", cfg=None):
        from themis.config import LexConfig
        self._cfg = cfg or LexConfig()
        self._matter_id = matter_id
        self._collection = f"{firm_id}_matter_{matter_id}"
        self._client = None
        self._model = None

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(
                url=self._cfg.qdrant_url,
                api_key=self._cfg.qdrant_api_key or None,
            )
        return self._client

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._cfg.embedding_model)
        return self._model

    def _ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams
        client = self._get_client()
        existing = {c.name for c in client.get_collections().collections}
        if self._collection not in existing:
            client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._cfg.embedding_dim,
                    distance=Distance.COSINE,
                ),
            )

    def index_findings(self, findings: list[dict]) -> int:
        """
        Embed and upsert research findings into the Qdrant collection.
        Returns the number of points upserted.

        Each finding dict is expected to have keys: case_name, citation,
        relevance, url, source. The full text used for embedding is
        "{case_name} {citation} {relevance}".
        """
        if not findings:
            return 0
        try:
            from qdrant_client.models import PointStruct
            self._ensure_collection()
            model = self._get_model()
            client = self._get_client()

            texts = [
                f"{f.get('case_name', '')} {f.get('citation', '')} {f.get('relevance', '')}"
                for f in findings
            ]
            vectors = model.encode(texts, show_progress_bar=False).tolist()

            points = [
                PointStruct(
                    id=abs(hash(f.get("citation", "") + f.get("case_name", ""))) % (2**63),
                    vector=vec,
                    payload=f,
                )
                for f, vec in zip(findings, vectors)
            ]
            client.upsert(collection_name=self._collection, points=points)
            return len(points)
        except Exception:
            return 0

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Query Qdrant for the top-k most relevant findings.
        Returns list of finding dicts (same shape as research_findings).
        Returns [] on any error so callers fall back gracefully.
        """
        try:
            model = self._get_model()
            client = self._get_client()
            query_vec = model.encode([query], show_progress_bar=False)[0].tolist()
            # WHY: score_threshold filters out low-similarity results before they
            # enter the cite node corpus. Without this gate, Qdrant returns the
            # top-k closest vectors regardless of actual similarity — an unrelated
            # chunk could pass BM25 scoring later and be marked verified=True.
            results = client.query_points(
                collection_name=self._collection,
                query=query_vec,
                limit=top_k,
                score_threshold=self._cfg.retriever_similarity_threshold,
            )
            return [hit.payload for hit in results.points]
        except Exception:
            return []
