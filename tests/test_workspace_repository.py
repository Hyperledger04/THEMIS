"""
Tests for PostgresWorkspaceRepository — themis/workspace/repository.py

Uses an in-memory SQLite3 adapter shim (not Postgres) so tests run without
a live database. The shim translates the psycopg connection interface to
sqlite3 for method signatures we exercise here.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from themis.workspace.models import (
    Authority,
    ChronologyItem,
    Deadline,
    DocumentRecord,
    Draft,
    ExtractedFact,
    FeedbackItem,
    Issue,
    Matter,
    Party,
    SourceAnchor,
    Task,
)
from themis.workspace.repository import PostgresWorkspaceRepository


# ---------------------------------------------------------------------------
# SQLite shim so repository tests run without Postgres
# ---------------------------------------------------------------------------

class _SQLiteConn:
    """Minimal psycopg-compatible wrapper around a sqlite3 connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def execute(self, sql: str, params=()) -> "_SQLiteCursor":
        # Translate Postgres-specific syntax to sqlite3
        sql = _pg_to_sqlite(sql)
        cur = self._conn.execute(sql, params)
        return _SQLiteCursor(cur)

    def executemany(self, sql: str, seq) -> None:
        sql = _pg_to_sqlite(sql)
        self._conn.executemany(sql, seq)

    def commit(self) -> None:
        self._conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _SQLiteCursor:
    def __init__(self, cur: sqlite3.Cursor) -> None:
        self._cur = cur

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return tuple(row)

    def fetchall(self):
        return [tuple(r) for r in self._cur.fetchall()]


def _pg_to_sqlite(sql: str) -> str:
    """Translate Postgres SQL to SQLite-compatible SQL."""
    import re
    # Replace %s placeholders with ?
    sql = sql.replace("%s", "?")
    # Remove Postgres type casts
    sql = re.sub(r"::(jsonb|json|text|date|timestamptz|boolean|integer)", "", sql)
    # Remove NULLS LAST (unsupported in older SQLite)
    sql = re.sub(r"\s+NULLS\s+(LAST|FIRST)", "", sql, flags=re.IGNORECASE)
    return sql


_WORKSPACE_DDL = """
CREATE TABLE IF NOT EXISTS matters (
    matter_id TEXT PRIMARY KEY, firm_id TEXT, user_id TEXT,
    title TEXT, matter_type TEXT, jurisdiction TEXT,
    status TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY, matter_id TEXT, firm_id TEXT,
    filename TEXT, mime_type TEXT, storage_uri TEXT, parser TEXT,
    page_count INTEGER, status TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS source_anchors (
    anchor_id TEXT PRIMARY KEY, matter_id TEXT, document_id TEXT,
    page INTEGER, line_start INTEGER, line_end INTEGER,
    excerpt TEXT, confidence REAL, extractor_agent TEXT,
    extraction_run_id TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS extracted_facts (
    fact_id TEXT PRIMARY KEY, matter_id TEXT, text TEXT,
    status TEXT, confidence REAL, source_anchor_ids TEXT,
    extractor_agent TEXT, extraction_run_id TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS chronology_items (
    chronology_id TEXT PRIMARY KEY, matter_id TEXT, date_text TEXT,
    event TEXT, normalized_date TEXT, confidence REAL,
    source_anchor_ids TEXT, extractor_agent TEXT,
    extraction_run_id TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id TEXT PRIMARY KEY, matter_id TEXT, title TEXT,
    description TEXT, document_id TEXT, source_anchor_ids TEXT,
    confidence REAL, created_at TEXT
);
CREATE TABLE IF NOT EXISTS parties (
    party_id TEXT PRIMARY KEY, matter_id TEXT, name TEXT,
    role TEXT, address TEXT, contact TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS issues (
    issue_id TEXT PRIMARY KEY, matter_id TEXT, text TEXT,
    category TEXT, status TEXT, source_anchor_ids TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS authorities (
    authority_id TEXT PRIMARY KEY, matter_id TEXT, authority_type TEXT,
    title TEXT, citation TEXT, court TEXT, url TEXT, proposition TEXT,
    treatment TEXT,
    jurisdiction TEXT DEFAULT 'india', country TEXT DEFAULT 'india',
    court_tier TEXT DEFAULT 'persuasive_domestic',
    corpus_namespace TEXT DEFAULT 'corpus:india_sc',
    verified_excerpt TEXT, paragraph_number TEXT,
    verification_status TEXT DEFAULT 'unverified',
    verified INTEGER, source_anchor_ids TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY, matter_id TEXT, doc_type TEXT,
    version INTEGER, content TEXT, status TEXT,
    verification_report_id TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS feedback_items (
    feedback_id TEXT PRIMARY KEY, matter_id TEXT, user_id TEXT,
    target_type TEXT, target_id TEXT, signal TEXT,
    note TEXT, diff TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS deadlines (
    deadline_id TEXT PRIMARY KEY, matter_id TEXT, title TEXT,
    due_date TEXT, deadline_type TEXT, status TEXT,
    source_anchor_ids TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY, matter_id TEXT, title TEXT,
    status TEXT, assigned_to TEXT, due_date TEXT, created_at TEXT
);
"""


@pytest.fixture
def repo() -> PostgresWorkspaceRepository:
    """Return a repository backed by in-memory SQLite."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_WORKSPACE_DDL)
    conn.commit()

    sqlite_conn = _SQLiteConn(conn)
    r = PostgresWorkspaceRepository.__new__(PostgresWorkspaceRepository)
    r._postgres_url = ":memory:"

    @contextmanager
    def _patched_connect():
        yield sqlite_conn

    r._connect = _patched_connect
    return r


@pytest.fixture
def matter(repo) -> Matter:
    m = Matter(title="NI Act 138 Complaint", matter_type="criminal", firm_id="firm_a")
    repo.create_matter(m)
    return m


# ---------------------------------------------------------------------------
# Matter
# ---------------------------------------------------------------------------

class TestMatter:
    def test_create_and_get(self, repo):
        m = Matter(title="Writ Petition", matter_type="constitutional", firm_id="firm_a")
        repo.create_matter(m)
        fetched = repo.get_matter(m.matter_id, "firm_a")
        assert fetched is not None
        assert fetched.title == "Writ Petition"

    def test_get_wrong_firm_returns_none(self, repo, matter):
        result = repo.get_matter(matter.matter_id, "other_firm")
        assert result is None

    def test_list_matters(self, repo):
        repo.create_matter(Matter(title="A", matter_type="civil", firm_id="firm_a"))
        repo.create_matter(Matter(title="B", matter_type="criminal", firm_id="firm_a"))
        repo.create_matter(Matter(title="C", matter_type="civil", firm_id="firm_b"))
        results = repo.list_matters("firm_a")
        assert len(results) == 2
        assert all(m.firm_id == "firm_a" for m in results)

    def test_update_status(self, repo, matter):
        repo.update_matter_status(matter.matter_id, "firm_a", "closed")
        fetched = repo.get_matter(matter.matter_id, "firm_a")
        assert fetched.status == "closed"


# ---------------------------------------------------------------------------
# DocumentRecord
# ---------------------------------------------------------------------------

class TestDocument:
    def test_create_and_list(self, repo, matter):
        doc = DocumentRecord(
            matter_id=matter.matter_id,
            firm_id=matter.firm_id,
            filename="cheque.pdf",
            storage_uri="/tmp/cheque.pdf",
        )
        repo.create_document(doc)
        docs = repo.list_documents(matter.matter_id, matter.firm_id)
        assert len(docs) == 1
        assert docs[0].filename == "cheque.pdf"

    def test_get_wrong_firm_returns_none(self, repo, matter):
        doc = DocumentRecord(
            matter_id=matter.matter_id, firm_id=matter.firm_id,
            filename="x.pdf", storage_uri="/tmp/x.pdf",
        )
        repo.create_document(doc)
        assert repo.get_document(doc.document_id, matter.matter_id, "wrong_firm") is None

    def test_update_status(self, repo, matter):
        doc = DocumentRecord(
            matter_id=matter.matter_id, firm_id=matter.firm_id,
            filename="y.pdf", storage_uri="/tmp/y.pdf",
        )
        repo.create_document(doc)
        repo.update_document_status(doc.document_id, matter.matter_id, matter.firm_id, "indexed", page_count=5, parser="pdfplumber")
        fetched = repo.get_document(doc.document_id, matter.matter_id, matter.firm_id)
        assert fetched.status == "indexed"
        assert fetched.page_count == 5


# ---------------------------------------------------------------------------
# ExtractedFact
# ---------------------------------------------------------------------------

class TestExtractedFact:
    def test_bulk_create_and_list(self, repo, matter):
        facts = [
            ExtractedFact(matter_id=matter.matter_id, text=f"Fact {i}", confidence=0.9)
            for i in range(3)
        ]
        repo.bulk_create_facts(facts)
        listed = repo.list_facts(matter.matter_id, matter.firm_id)
        assert len(listed) == 3

    def test_list_with_status_filter(self, repo, matter):
        repo.create_fact(ExtractedFact(matter_id=matter.matter_id, text="X", status="extracted"))
        repo.create_fact(ExtractedFact(matter_id=matter.matter_id, text="Y", status="confirmed"))
        extracted = repo.list_facts(matter.matter_id, matter.firm_id, status="extracted")
        assert len(extracted) == 1
        assert extracted[0].text == "X"


# ---------------------------------------------------------------------------
# ChronologyItem
# ---------------------------------------------------------------------------

class TestChronologyItem:
    def test_bulk_create_and_list_ordered(self, repo, matter):
        items = [
            ChronologyItem(matter_id=matter.matter_id, date_text="1 Jan 2026",
                           event="First event", normalized_date="2026-01-01"),
            ChronologyItem(matter_id=matter.matter_id, date_text="1 Mar 2026",
                           event="Second event", normalized_date="2026-03-01"),
            ChronologyItem(matter_id=matter.matter_id, date_text="Unknown date",
                           event="Undated event"),
        ]
        repo.bulk_create_chronology(items)
        listed = repo.list_chronology(matter.matter_id, matter.firm_id)
        assert len(listed) == 3
        # Dated items should come before undated
        dated = [i for i in listed if i.normalized_date]
        assert len(dated) == 2


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------

class TestAuthority:
    def test_create_and_list(self, repo, matter):
        auth = Authority(
            matter_id=matter.matter_id,
            title="Rangappa v. Mohan",
            proposition="Drawee bank's memo is sufficient proof of dishonour",
        )
        repo.create_authority(auth)
        authorities = repo.list_authorities(matter.matter_id, matter.firm_id)
        assert len(authorities) == 1
        assert authorities[0].title == "Rangappa v. Mohan"

    def test_filter_verified(self, repo, matter):
        repo.create_authority(Authority(matter_id=matter.matter_id, title="A", proposition="p1", verified=False))
        repo.create_authority(Authority(matter_id=matter.matter_id, title="B", proposition="p2", verified=True))
        verified = repo.list_authorities(matter.matter_id, matter.firm_id, verified=True)
        assert len(verified) == 1
        assert verified[0].title == "B"


# ---------------------------------------------------------------------------
# Draft  (immutable versioning)
# ---------------------------------------------------------------------------

class TestDraft:
    def test_create_and_get_latest(self, repo, matter):
        d1 = Draft(matter_id=matter.matter_id, doc_type="legal_notice", version=1, content="v1 content")
        d2 = Draft(matter_id=matter.matter_id, doc_type="legal_notice", version=2, content="v2 content")
        repo.create_draft(d1)
        repo.create_draft(d2)
        latest = repo.get_latest_draft(matter.matter_id, matter.firm_id, "legal_notice")
        assert latest is not None
        assert latest.version == 2
        assert latest.content == "v2 content"

    def test_get_latest_wrong_doc_type_returns_none(self, repo, matter):
        repo.create_draft(Draft(matter_id=matter.matter_id, doc_type="legal_notice", version=1, content="x"))
        result = repo.get_latest_draft(matter.matter_id, matter.firm_id, "writ_petition")
        assert result is None
