"""
Tests for themis/kb/collections.py.

Covers:
- Collection name generation (firm, matter, judgments)
- _safe() sanitisation of illegal characters
- ensure_collections(): skips when qdrant_enabled=False, calls client when True
- encrypt_payload / decrypt_payload: passthrough when no key, round-trip when key set
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from themis.kb.collections import (
    _safe,
    decrypt_payload,
    encrypt_payload,
    ensure_collections,
    firm_collection,
    judgments_collection,
    matter_collection,
)


# ---------------------------------------------------------------------------
# Collection naming
# ---------------------------------------------------------------------------

class TestCollectionNames:
    def test_firm_collection_format(self):
        assert firm_collection("sharma_associates") == "firm_sharma_associates"

    def test_matter_collection_format(self):
        assert matter_collection("sharma", "M-2024-001") == "matter_sharma_M-2024-001"

    def test_judgments_collection_constant(self):
        assert judgments_collection() == "judgments_cache"

    def test_safe_strips_spaces(self):
        assert _safe("firm name") == "firm_name"

    def test_safe_strips_dots(self):
        assert _safe("firm.name") == "firm_name"

    def test_safe_preserves_hyphens_and_underscores(self):
        assert _safe("firm-name_123") == "firm-name_123"

    def test_safe_strips_special_chars(self):
        assert _safe("firm@#$name") == "firm___name"


# ---------------------------------------------------------------------------
# ensure_collections: qdrant_enabled=False skips client calls
# ---------------------------------------------------------------------------

def test_ensure_collections_skips_when_qdrant_disabled():
    cfg = MagicMock(qdrant_enabled=False)
    with patch("qdrant_client.QdrantClient", create=True) as mock_client:
        ensure_collections("test_firm", cfg=cfg)
    mock_client.assert_not_called()


def test_ensure_collections_creates_firm_and_judgments():
    cfg = MagicMock(
        qdrant_enabled=True,
        qdrant_url="http://localhost:6333",
        qdrant_api_key=None,
        embedding_dim=384,
    )
    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = []

    with patch("themis.kb.collections.QdrantClient", return_value=mock_client):
        ensure_collections("acme_law", cfg=cfg)

    created_names = [call.kwargs["collection_name"] for call in mock_client.create_collection.call_args_list]
    assert "firm_acme_law" in created_names
    assert "judgments_cache" in created_names


def test_ensure_collections_skips_existing():
    cfg = MagicMock(
        qdrant_enabled=True,
        qdrant_url="http://localhost:6333",
        qdrant_api_key=None,
        embedding_dim=384,
    )
    existing_col = MagicMock()
    existing_col.name = "firm_acme_law"
    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = [existing_col]

    with patch("themis.kb.collections.QdrantClient", return_value=mock_client):
        ensure_collections("acme_law", cfg=cfg)

    created_names = [call.kwargs["collection_name"] for call in mock_client.create_collection.call_args_list]
    assert "firm_acme_law" not in created_names


def test_ensure_collections_creates_matter_when_provided():
    cfg = MagicMock(
        qdrant_enabled=True,
        qdrant_url="http://localhost:6333",
        qdrant_api_key=None,
        embedding_dim=384,
    )
    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = []

    with patch("themis.kb.collections.QdrantClient", return_value=mock_client):
        ensure_collections("acme_law", matter_id="M-001", cfg=cfg)

    created_names = [call.kwargs["collection_name"] for call in mock_client.create_collection.call_args_list]
    assert "matter_acme_law_M-001" in created_names


# ---------------------------------------------------------------------------
# Payload encryption / decryption
# ---------------------------------------------------------------------------

def test_encrypt_payload_passthrough_when_no_key():
    cfg = MagicMock(encryption_key=None)
    payload = {"text": "sensitive data", "score": 0.9}
    result = encrypt_payload(payload, "firm_a", cfg=cfg)
    assert result == payload


def test_decrypt_payload_passthrough_when_no_key():
    cfg = MagicMock(encryption_key=None)
    payload = {"text": "data", "count": 5}
    result = decrypt_payload(payload, "firm_a", cfg=cfg)
    assert result == payload


def test_encrypt_decrypt_roundtrip():
    import os
    master_key = os.urandom(32).hex()
    cfg = MagicMock(encryption_key=master_key)
    payload = {"title": "Sharma v State", "snippet": "The court held..."}

    encrypted = encrypt_payload(payload, "firm_a", cfg=cfg)
    # Encrypted string values should differ from originals
    assert encrypted["title"] != payload["title"]

    decrypted = decrypt_payload(encrypted, "firm_a", cfg=cfg)
    assert decrypted["title"] == payload["title"]
    assert decrypted["snippet"] == payload["snippet"]


def test_encrypt_payload_leaves_non_strings_untouched():
    import os
    master_key = os.urandom(32).hex()
    cfg = MagicMock(encryption_key=master_key)
    payload = {"text": "hello", "score": 0.95, "tags": ["kanoon", "sc"]}

    encrypted = encrypt_payload(payload, "firm_a", cfg=cfg)
    assert encrypted["score"] == 0.95
    assert encrypted["tags"] == ["kanoon", "sc"]


def test_decrypt_payload_falls_back_on_plaintext_values():
    """Decryption must not crash on legacy plaintext rows (migration safety)."""
    import os
    master_key = os.urandom(32).hex()
    cfg = MagicMock(encryption_key=master_key)
    payload = {"text": "plaintext_not_encrypted"}

    result = decrypt_payload(payload, "firm_a", cfg=cfg)
    # Should return the raw value, not raise
    assert result["text"] == "plaintext_not_encrypted"
