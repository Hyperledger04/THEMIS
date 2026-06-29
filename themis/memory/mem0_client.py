# WHY: mem0ai is an optional dependency — lawyers who don't need semantic memory
# never install it. All methods degrade gracefully to no-ops or empty results
# when mem0ai is absent or Qdrant is unreachable.

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _try_import_mem0():
    """Return mem0.Memory class or None if mem0ai is not installed."""
    try:
        from mem0 import Memory  # type: ignore[import]
        return Memory
    except ImportError:
        return None


class Mem0Client:
    """
    Thin wrapper around mem0ai.Memory backed by a self-hosted Qdrant instance.

    Personal-mode default: all-MiniLM-L6-v2 (local HuggingFace) so no external
    API key is required. Pass openai_api_key to upgrade to text-embedding-3-small.

    All public methods are safe to call even when mem0 is unavailable — they
    return empty results or None without raising.
    """

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        qdrant_api_key: Optional[str] = None,
        collection_name: str = "lex_lawyer_memory",
        embedding_model: str = "all-MiniLM-L6-v2",
        openai_api_key: Optional[str] = None,
    ) -> None:
        self._memory = None

        MemoryClass = _try_import_mem0()
        if MemoryClass is None:
            logger.debug("mem0ai not installed — running in file-only mode")
            return

        try:
            # WHY huggingface default: avoids requiring an OpenAI key for
            # personal mode. The same model (all-MiniLM-L6-v2) is already
            # used by the BM25+vector retriever, so it's already warm.
            embedder_config: dict
            if openai_api_key:
                embedder_config = {
                    "provider": "openai",
                    "config": {
                        "model": "text-embedding-3-small",
                        "api_key": openai_api_key,
                    },
                }
            else:
                embedder_config = {
                    "provider": "huggingface",
                    "config": {"model": f"sentence-transformers/{embedding_model}"},
                }

            config: dict = {
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "collection_name": collection_name,
                        "url": qdrant_url,
                        **({"api_key": qdrant_api_key} if qdrant_api_key else {}),
                    },
                },
                "embedder": embedder_config,
            }
            self._memory = MemoryClass.from_config(config)
            logger.info("mem0 client ready (Qdrant: %s, collection: %s)", qdrant_url, collection_name)
        except Exception as exc:
            # Non-fatal — system continues with file-based memory
            logger.warning("mem0 init failed, falling back to file memory: %s", exc)

    @property
    def is_available(self) -> bool:
        return self._memory is not None

    def add(
        self,
        text: str,
        user_id: str,
        metadata: Optional[dict] = None,
    ) -> Optional[str]:
        """
        Add a memory entry. Returns the memory ID or None on failure.

        mem0 automatically deduplicates and merges memories — repeated calls
        with similar text update the existing entry rather than creating duplicates.
        """
        if self._memory is None:
            return None
        try:
            result = self._memory.add(text, user_id=user_id, metadata=metadata or {})
            # mem0 returns list[dict] in v0.1+ and dict in older versions
            if isinstance(result, list) and result:
                return result[0].get("id")
            if isinstance(result, dict):
                return result.get("id")
            return None
        except Exception as exc:
            logger.warning("mem0.add failed: %s", exc)
            return None

    def search(
        self,
        query: str,
        user_id: str,
        limit: int = 5,
    ) -> list[str]:
        """
        Semantic search over stored memories. Returns plain text strings.
        Empty list on failure or when mem0 is unavailable.
        """
        if self._memory is None:
            return []
        try:
            results = self._memory.search(query, user_id=user_id, limit=limit)
            # mem0 v0.1.29+ wraps results in {"results": [...]}
            if isinstance(results, dict):
                results = results.get("results", [])
            return [r["memory"] for r in results if isinstance(r, dict) and "memory" in r]
        except Exception as exc:
            logger.warning("mem0.search failed: %s", exc)
            return []

    def get_all(self, user_id: str) -> list[str]:
        """Return all stored memories for a user. Empty list on failure."""
        if self._memory is None:
            return []
        try:
            results = self._memory.get_all(user_id=user_id)
            if isinstance(results, dict):
                results = results.get("results", [])
            return [r["memory"] for r in results if isinstance(r, dict) and "memory" in r]
        except Exception as exc:
            logger.warning("mem0.get_all failed: %s", exc)
            return []
