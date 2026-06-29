# WHY: Single interface for all lawyer-profile reads and writes.
# draft.py, soul.py, and any future specialist agents go through here —
# enabling mem0 requires zero changes to callers.
#
# Priority order:
#   1. mem0 (LEX_MEM0_ENABLED=true) — semantic, evolving, queryable
#   2. SOUL.md / MEMORY.md file fallback — always present, never breaks
#
# Architecture note (V3 §9.2): Senior Counsel owns all memory reads/writes.
# Specialists receive memory as typed input fields — they never call this module.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from themis.config import LexConfig

logger = logging.getLogger(__name__)

# Module-level singleton — one Mem0Client per process.
# WHY: Qdrant connection + sentence-transformer warm-up costs ~500ms.
# Caching avoids that penalty on every draft call.
_client: Optional["Mem0Client"] = None  # type: ignore[name-defined]
_client_key: str = ""


def _get_client(config: "LexConfig") -> "Mem0Client":  # type: ignore[name-defined]
    global _client, _client_key
    from themis.memory.mem0_client import Mem0Client

    # Rebuild client only when the Qdrant config changes (URL, key, model, collection)
    key = f"{config.qdrant_url}|{config.qdrant_api_key}|{config.embedding_model}|{config.mem0_collection}"
    if _client is None or _client_key != key:
        _client = Mem0Client(
            qdrant_url=config.qdrant_url,
            qdrant_api_key=config.qdrant_api_key,
            collection_name=config.mem0_collection,
            embedding_model=config.embedding_model,
            openai_api_key=config.openai_api_key,
        )
        _client_key = key
    return _client


def load_lawyer_profile(lawyer_id: str, config: "LexConfig") -> Optional[str]:
    """
    Load the lawyer's identity and style context for injection into the draft prompt.

    Always reads SOUL.md first (curated by the lawyer — source of truth for identity).
    When mem0 is enabled and Qdrant is reachable, appends semantically-retrieved
    style memories inferred from past drafting sessions.

    WHY append, not replace: SOUL.md is intentional; mem0 memories are inferred.
    Both layers together give the richest context without risking hallucination.
    """
    from pathlib import Path
    from themis.memory.soul import soul_path

    soul_text: Optional[str] = None
    path = soul_path(config.home_dir)
    if path.exists():
        soul_text = path.read_text(encoding="utf-8")

    if not config.mem0_enabled:
        return soul_text

    client = _get_client(config)
    if not client.is_available:
        return soul_text

    recalled = client.search(
        "lawyer drafting style citation preference tone jurisdiction court",
        user_id=lawyer_id,
        limit=8,
    )
    if not recalled:
        return soul_text

    enrichment = (
        "\n\n## Recalled Style Memories (inferred from past sessions)\n"
        + "\n".join(f"- {m}" for m in recalled)
    )
    return (soul_text or "") + enrichment


def save_feedback(
    text: str,
    matter_id: str,
    lawyer_id: str,
    config: "LexConfig",
    metadata: Optional[dict] = None,
) -> None:
    """
    Persist a learning signal to mem0.

    Called by the draft node after each successful draft with a summary of
    what was drafted (matter type, jurisdiction, skill used). mem0 merges
    this with existing memories — repeated patterns strengthen preferences.

    No-op when mem0 is disabled (LEX_MEM0_ENABLED not set).
    """
    if not config.mem0_enabled:
        return

    client = _get_client(config)
    if not client.is_available:
        return

    meta = {"matter_id": matter_id, **(metadata or {})}
    client.add(text, user_id=lawyer_id, metadata=meta)
    logger.debug("Saved feedback memory for lawyer %s (matter: %s)", lawyer_id, matter_id)


def load_matter_context(
    matter_id: str,
    lawyer_id: str,
    config: "LexConfig",
) -> Optional[str]:
    """
    Retrieve matter-specific context for injection into the draft prompt.

    When mem0 is disabled: returns MEMORY.md content (current file-based behaviour).
    When mem0 is enabled: semantic search over past matter memories in Qdrant.
    """
    if not config.mem0_enabled:
        from themis.memory.matter_memory import load_matter_memory
        return load_matter_memory(matter_id, config.matters_dir, firm_id=config.default_firm_id)

    client = _get_client(config)
    if not client.is_available:
        from themis.memory.matter_memory import load_matter_memory
        return load_matter_memory(matter_id, config.matters_dir, firm_id=config.default_firm_id)

    memories = client.search(
        f"matter {matter_id} facts parties issues research findings",
        user_id=lawyer_id,
        limit=10,
    )
    if not memories:
        # Also try MEMORY.md as fallback even in mem0 mode — first session has no memories yet
        from themis.memory.matter_memory import load_matter_memory
        return load_matter_memory(matter_id, config.matters_dir, firm_id=config.default_firm_id)

    return "\n".join(f"- {m}" for m in memories)


def seed_soul_to_mem0(lawyer_id: str, config: "LexConfig") -> int:
    """
    Bootstrap mem0 from SOUL.md — the one-time operation that makes mem0 useful immediately.

    Extracts each structured field and section as a distinct memory entry so that
    `load_lawyer_profile()` returns real preferences on the very first enriched draft,
    not an empty recall.

    Returns the number of memories stored. No-op when mem0 is disabled or unavailable.
    """
    if not config.mem0_enabled:
        return 0

    from themis.memory.soul import soul_path, _parse_soul

    path = soul_path(config.home_dir)
    if not path.exists():
        return 0

    content = path.read_text(encoding="utf-8")
    soul = _parse_soul(content)

    client = _get_client(config)
    if not client.is_available:
        return 0

    # Field-level memories — specific, searchable style signals
    # Keys map directly to SOUL_TEMPLATE field names parsed by _parse_soul
    field_labels = {
        "primary_courts": "Primary courts",
        "primary_practice_areas": "Practice areas",
        "typical_matter_types": "Typical matter types",
        "preferred_tone": "Preferred drafting tone",
        "citation_preference": "Citation preference",
        "document_length": "Document length preference",
        "language_notes": "Language notes",
        "formatting_style": "Formatting style",
        "firm_name": "Firm",
        "firm_type": "Firm type",
    }
    memories: list[tuple[str, dict]] = []
    for key, label in field_labels.items():
        val = soul.get(key, "").strip()
        if val:
            memories.append((f"{label}: {val}", {"source": "SOUL.md", "field": key}))

    # Section-level memories — richer blocks (judicial preferences, custom instructions)
    section_labels = {
        "section_known_judicial_preferences": "Known judicial preferences",
        "section_custom_instructions": "Custom instructions",
        "section_firm_context": "Firm context",
        "section_drafting_style": "Drafting style",
    }
    for key, label in section_labels.items():
        body = soul.get(key, "").strip()
        if body and len(body) > 15:
            memories.append((f"{label}: {body}", {"source": "SOUL.md", "section": key}))

    count = 0
    for text, meta in memories:
        result = client.add(text, user_id=lawyer_id, metadata=meta)
        if result is not None:
            count += 1

    logger.info("Seeded %d memories from SOUL.md for lawyer %s", count, lawyer_id)
    return count


def seed_matter_to_mem0(
    matter_id: str,
    lawyer_id: str,
    config: "LexConfig",
) -> int:
    """
    Bootstrap mem0 from a matter's MEMORY.md file.

    Splits the file at section headings and stores each section as a
    separate memory so `load_matter_context()` can retrieve the specific
    facts, parties, or research notes most relevant to a query — rather
    than returning the full flat file.

    Returns the number of memories stored.
    """
    if not config.mem0_enabled:
        return 0

    from themis.memory.matter_memory import load_matter_memory

    content = load_matter_memory(matter_id, config.matters_dir, firm_id=config.default_firm_id)
    if not content:
        return 0

    client = _get_client(config)
    if not client.is_available:
        return 0

    # Split on markdown headings to create one memory per logical chunk
    import re
    chunks = re.split(r"\n(?=##? )", content.strip())
    chunks = [c.strip() for c in chunks if c.strip() and len(c.strip()) > 20]

    count = 0
    for chunk in chunks:
        result = client.add(
            chunk,
            user_id=lawyer_id,
            metadata={"source": "MEMORY.md", "matter_id": matter_id},
        )
        if result is not None:
            count += 1

    logger.info("Seeded %d memories from MEMORY.md for matter %s", count, matter_id)
    return count


def reset_client() -> None:
    """
    Clear the cached Mem0Client. Used in tests to force re-init with different config.
    """
    global _client, _client_key
    _client = None
    _client_key = ""
