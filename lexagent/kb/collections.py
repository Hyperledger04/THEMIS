"""
Centralised Qdrant collection naming and lifecycle management.

WHY centralise here: every component that touches Qdrant (ingestion, retriever,
judgment cache, mem0) must agree on collection names and vector dimensions.
Scattering collection names across files causes silent mismatches that are hard
to debug in production. One source of truth.

Three collection tiers:
  firm      — firm-wide KB (uploaded acts, precedents, standard clauses)
  matter    — per-matter context (uploaded docs specific to one case)
  judgments — shared judgment cache (populated by react_research auto-cache)

All vector payloads for a firm are optionally AES-256-GCM encrypted using the
firm's derived key (see lexagent/security/crypto.py). Encryption is transparent:
read/write helpers here call encrypt/decrypt so callers never handle raw crypto.

DPDP Day 1 commitment: encryption at rest is on by default when
LexConfig.encryption_key is set. When absent (dev/offline), data is stored as
plaintext — acceptable for local single-lawyer mode.
"""
from __future__ import annotations

from typing import Optional

from lexagent.config import LexConfig

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams
except ImportError:
    QdrantClient = None  # type: ignore[assignment,misc]
    Distance = None  # type: ignore[assignment]
    VectorParams = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Collection naming
# ---------------------------------------------------------------------------

def firm_collection(firm_id: str) -> str:
    """Qdrant collection for firm-wide knowledge base."""
    # WHY: sanitise firm_id so collection names are valid Qdrant identifiers.
    # Qdrant collection names must match [a-zA-Z0-9_-].
    return f"firm_{_safe(firm_id)}"


def matter_collection(firm_id: str, matter_id: str) -> str:
    """Per-matter Qdrant collection — isolated per case."""
    return f"matter_{_safe(firm_id)}_{_safe(matter_id)}"


def judgments_collection() -> str:
    """Shared judgment cache — populated by react_research, read by retriever."""
    return "judgments_cache"


def _safe(name: str) -> str:
    """Strip characters that are illegal in Qdrant collection names."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


# ---------------------------------------------------------------------------
# Collection creation / ensure
# ---------------------------------------------------------------------------

def ensure_collections(
    firm_id: str,
    matter_id: Optional[str] = None,
    cfg: Optional[LexConfig] = None,
) -> None:
    """
    Create the standard Qdrant collections for a firm (and optionally a matter)
    if they do not already exist.

    Idempotent — safe to call on every startup or new-matter creation.
    Skips silently when cfg.qdrant_enabled is False (offline/dev mode).
    """
    if cfg is None:
        cfg = LexConfig()
    if not cfg.qdrant_enabled:
        return

    client = QdrantClient(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key)
    dim = cfg.embedding_dim

    _ensure_one(client, firm_collection(firm_id), dim)
    _ensure_one(client, judgments_collection(), dim)
    if matter_id:
        _ensure_one(client, matter_collection(firm_id, matter_id), dim)


def _ensure_one(client, name: str, dim: int) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


# ---------------------------------------------------------------------------
# Payload encryption helpers
# ---------------------------------------------------------------------------

def encrypt_payload(payload: dict, firm_id: str, cfg: Optional[LexConfig] = None) -> dict:
    """
    Encrypt string values in a Qdrant point payload using the firm's derived key.

    Non-string values (ints, lists, etc.) are left untouched — Qdrant uses them
    for filtering and they must remain plaintext.

    Returns the payload unchanged when encryption_key is not configured
    (personal / offline mode).
    """
    if cfg is None:
        cfg = LexConfig()
    if not cfg.encryption_key:
        return payload

    from lexagent.security.crypto import encrypt_str

    return {
        k: encrypt_str(v, cfg.encryption_key, firm_id) if isinstance(v, str) else v
        for k, v in payload.items()
    }


def decrypt_payload(payload: dict, firm_id: str, cfg: Optional[LexConfig] = None) -> dict:
    """Decrypt string values in a retrieved Qdrant point payload."""
    if cfg is None:
        cfg = LexConfig()
    if not cfg.encryption_key:
        return payload

    from lexagent.security.crypto import decrypt_str

    result = {}
    for k, v in payload.items():
        if isinstance(v, (bytes, str)):
            try:
                result[k] = decrypt_str(v, cfg.encryption_key, firm_id)
            except Exception:
                # WHY: If decryption fails (e.g. legacy plaintext row), fall
                # back to the raw value. This enables zero-downtime migration.
                result[k] = v
        else:
            result[k] = v
    return result
