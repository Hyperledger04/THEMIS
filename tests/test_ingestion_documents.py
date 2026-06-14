"""Tests for themis/ingestion/documents.py — file ingestion pipeline."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from themis.ingestion.documents import (
    IngestedDocument,
    PageText,
    _extract_plaintext,
    _sha256_prefix,
    ingest_file,
)
from themis.workspace.models import DocumentRecord


# ---------------------------------------------------------------------------
# _extract_plaintext — no external deps, fast
# ---------------------------------------------------------------------------

class TestExtractPlaintext:
    def test_single_chunk(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello world\nSecond line\n")
        parser, pages = _extract_plaintext(f)
        assert parser == "plaintext"
        assert len(pages) == 1
        assert pages[0].page == 1
        assert "Hello world" in pages[0].text

    def test_large_file_splits_into_pages(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("x" * 9001)  # 3 chunks at 3000 chars
        parser, pages = _extract_plaintext(f)
        assert parser == "plaintext"
        assert len(pages) == 4  # ceil(9001/3000) = 4

    def test_empty_file_returns_single_empty_page(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        _, pages = _extract_plaintext(f)
        assert len(pages) == 1
        assert pages[0].text == ""


# ---------------------------------------------------------------------------
# _sha256_prefix
# ---------------------------------------------------------------------------

def test_sha256_prefix_length(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("some content")
    prefix = _sha256_prefix(f)
    assert len(prefix) == 12


def test_sha256_prefix_same_content_same_hash(tmp_path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("same content")
    f2.write_text("same content")
    assert _sha256_prefix(f1) == _sha256_prefix(f2)


# ---------------------------------------------------------------------------
# ingest_file — integration with mocked repo
# ---------------------------------------------------------------------------

class TestIngestFile:
    def _make_repo(self):
        repo = MagicMock()
        repo.create_document = MagicMock()
        repo.bulk_create_anchors = MagicMock()
        return repo

    def test_ingest_plaintext_creates_document_and_anchors(self, tmp_path):
        f = tmp_path / "brief.txt"
        f.write_text("The cheque was dishonoured on 14 March 2026.\nThe complainant is Ramesh Kumar.")
        repo = self._make_repo()

        with patch("themis.ingestion.documents._STORAGE_ROOT", tmp_path / "store"):
            result = ingest_file(f, matter_id="M-001", firm_id="firm_a", repo=repo)

        assert isinstance(result, IngestedDocument)
        assert result.record.filename == "brief.txt"
        assert result.record.parser == "plaintext"
        assert len(result.pages) == 1
        repo.create_document.assert_called_once()
        repo.bulk_create_anchors.assert_called_once()
        # Anchors should exist for non-blank lines
        assert result.anchor_count > 0

    def test_ingest_missing_file_raises(self, tmp_path):
        repo = self._make_repo()
        with pytest.raises(FileNotFoundError):
            ingest_file(tmp_path / "nonexistent.txt", "M-001", "firm_a", repo)

    def test_ingest_copies_file_to_storage(self, tmp_path):
        f = tmp_path / "order.txt"
        f.write_text("Court order dated 1 January 2026.")
        repo = self._make_repo()
        store = tmp_path / "store"

        with patch("themis.ingestion.documents._STORAGE_ROOT", store):
            result = ingest_file(f, matter_id="M-001", firm_id="firm_a", repo=repo)

        stored = Path(result.record.storage_uri)
        assert stored.exists()
        assert stored.read_text() == "Court order dated 1 January 2026."

    def test_ingest_duplicate_file_does_not_overwrite(self, tmp_path):
        """Uploading the same file twice reuses the content-addressed copy."""
        f = tmp_path / "doc.txt"
        f.write_text("Unique content")
        repo = self._make_repo()
        store = tmp_path / "store"

        with patch("themis.ingestion.documents._STORAGE_ROOT", store):
            r1 = ingest_file(f, matter_id="M-001", firm_id="firm_a", repo=repo)
            r2 = ingest_file(f, matter_id="M-001", firm_id="firm_a", repo=repo)

        # Both should point to the same storage path
        assert r1.record.storage_uri == r2.record.storage_uri
