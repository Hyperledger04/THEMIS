"""
§11A Failure Mode 3 — Confidentiality Bleed isolation test.

Creates two matters in different firms, populates each with distinct named
facts and authorities, then asserts that queries for one matter return zero
objects from the other matter or firm.

This test is mandatory per the V3 architecture (§11A, §15). It must pass
before any multi-tenant deployment.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

import pytest

from lexagent.workspace.models import (
    Authority,
    Draft,
    ExtractedFact,
    Matter,
    Party,
)
from lexagent.workspace.repository import PostgresWorkspaceRepository

# ---------------------------------------------------------------------------
# Reuse the SQLite shim from test_workspace_repository
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS matters (
    matter_id TEXT PRIMARY KEY, firm_id TEXT, user_id TEXT,
    title TEXT, matter_type TEXT, jurisdiction TEXT,
    status TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS extracted_facts (
    fact_id TEXT PRIMARY KEY, matter_id TEXT, text TEXT,
    status TEXT, confidence REAL, source_anchor_ids TEXT,
    extractor_agent TEXT, extraction_run_id TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS authorities (
    authority_id TEXT PRIMARY KEY, matter_id TEXT, authority_type TEXT,
    title TEXT, citation TEXT, court TEXT, url TEXT, proposition TEXT,
    treatment TEXT, verified INTEGER, source_anchor_ids TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY, matter_id TEXT, doc_type TEXT,
    version INTEGER, content TEXT, status TEXT,
    verification_report_id TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS parties (
    party_id TEXT PRIMARY KEY, matter_id TEXT, name TEXT,
    role TEXT, address TEXT, contact TEXT, created_at TEXT
);
"""

import re as _re


def _pg_to_sqlite(sql: str) -> str:
    sql = sql.replace("%s", "?")
    sql = _re.sub(r"::(jsonb|json|text|date|timestamptz|boolean|integer)", "", sql)
    sql = _re.sub(r"\s+NULLS\s+(LAST|FIRST)", "", sql, flags=_re.IGNORECASE)
    return sql


class _Row:
    def __init__(self, row):
        self._row = tuple(row)

    def __iter__(self):
        return iter(self._row)


class _Cur:
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        row = self._cur.fetchone()
        return tuple(row) if row else None

    def fetchall(self):
        return [tuple(r) for r in self._cur.fetchall()]


class _Conn:
    def __init__(self, c):
        self._c = c

    def execute(self, sql, params=()):
        return _Cur(self._c.execute(_pg_to_sqlite(sql), params))

    def executemany(self, sql, seq):
        self._c.executemany(_pg_to_sqlite(sql), seq)

    def commit(self):
        self._c.commit()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_DDL)
    conn.commit()
    wrapped = _Conn(conn)

    r = PostgresWorkspaceRepository.__new__(PostgresWorkspaceRepository)
    r._postgres_url = ":memory:"

    @contextmanager
    def _connect():
        yield wrapped

    r._connect = _connect
    return r


# ---------------------------------------------------------------------------
# The isolation test
# ---------------------------------------------------------------------------

class TestMatterIsolation:
    """
    Verify that no legal object from matter A is accessible when querying
    matter B, even within the same Postgres instance.
    """

    def _setup_two_matters(self, repo):
        """Create two fully-populated matters in different firms."""
        matter_a = Matter(matter_id="M-ALPHA", firm_id="firm_a",
                          title="Alpha v Beta", matter_type="civil")
        matter_b = Matter(matter_id="M-BETA", firm_id="firm_b",
                          title="Gamma v Delta", matter_type="criminal")
        repo.create_matter(matter_a)
        repo.create_matter(matter_b)

        # Facts unique to each matter
        repo.create_fact(ExtractedFact(matter_id="M-ALPHA", text="ALPHA_FACT: cheque issued by Alpha Corp"))
        repo.create_fact(ExtractedFact(matter_id="M-BETA", text="BETA_FACT: accused Beta Enterprises"))

        # Authorities unique to each matter
        repo.create_authority(Authority(
            matter_id="M-ALPHA", title="ALPHA_CASE: Alpha Holdings",
            proposition="Alpha proposition",
        ))
        repo.create_authority(Authority(
            matter_id="M-BETA", title="BETA_CASE: Beta Industries",
            proposition="Beta proposition",
        ))

        # Drafts
        repo.create_draft(Draft(matter_id="M-ALPHA", doc_type="legal_notice",
                                version=1, content="ALPHA_DRAFT content"))
        repo.create_draft(Draft(matter_id="M-BETA", doc_type="legal_notice",
                                version=1, content="BETA_DRAFT content"))

        # Parties
        repo.create_party(Party(matter_id="M-ALPHA", name="ALPHA_PARTY", role="complainant"))
        repo.create_party(Party(matter_id="M-BETA", name="BETA_PARTY", role="respondent"))

        return matter_a, matter_b

    def test_facts_scoped_to_matter_and_firm(self, repo):
        """Facts from matter A must not appear in matter B's query."""
        self._setup_two_matters(repo)

        facts_a = repo.list_facts("M-ALPHA", "firm_a")
        facts_b = repo.list_facts("M-BETA", "firm_b")

        assert all("ALPHA_FACT" in f.text for f in facts_a)
        assert all("BETA_FACT" in f.text for f in facts_b)
        # No cross-contamination
        assert not any("BETA_FACT" in f.text for f in facts_a)
        assert not any("ALPHA_FACT" in f.text for f in facts_b)

    def test_wrong_firm_id_returns_empty_facts(self, repo):
        """Querying matter A with firm B's ID must return zero facts."""
        self._setup_two_matters(repo)
        facts = repo.list_facts("M-ALPHA", "firm_b")
        assert facts == []

    def test_authorities_scoped_to_matter_and_firm(self, repo):
        self._setup_two_matters(repo)

        auths_a = repo.list_authorities("M-ALPHA", "firm_a")
        auths_b = repo.list_authorities("M-BETA", "firm_b")

        assert all("ALPHA_CASE" in a.title for a in auths_a)
        assert not any("BETA_CASE" in a.title for a in auths_a)
        assert all("BETA_CASE" in a.title for a in auths_b)
        assert not any("ALPHA_CASE" in a.title for a in auths_b)

    def test_wrong_firm_id_returns_empty_authorities(self, repo):
        self._setup_two_matters(repo)
        assert repo.list_authorities("M-ALPHA", "firm_b") == []

    def test_drafts_scoped_to_matter_and_firm(self, repo):
        self._setup_two_matters(repo)

        drafts_a = repo.list_drafts("M-ALPHA", "firm_a")
        assert len(drafts_a) == 1
        assert "ALPHA_DRAFT" in drafts_a[0].content

        drafts_b = repo.list_drafts("M-BETA", "firm_b")
        assert len(drafts_b) == 1
        assert "BETA_DRAFT" in drafts_b[0].content

        # Cross-firm query returns empty
        assert repo.list_drafts("M-ALPHA", "firm_b") == []

    def test_parties_scoped_to_matter_and_firm(self, repo):
        self._setup_two_matters(repo)

        parties_a = repo.list_parties("M-ALPHA", "firm_a")
        assert len(parties_a) == 1
        assert parties_a[0].name == "ALPHA_PARTY"

        parties_b = repo.list_parties("M-BETA", "firm_b")
        assert len(parties_b) == 1
        assert parties_b[0].name == "BETA_PARTY"

        assert repo.list_parties("M-ALPHA", "firm_b") == []

    def test_get_matter_firm_boundary(self, repo):
        """get_matter must not return matter A when queried with firm B's ID."""
        self._setup_two_matters(repo)
        assert repo.get_matter("M-ALPHA", "firm_b") is None
        assert repo.get_matter("M-BETA", "firm_a") is None
        # Correct firm IDs work
        assert repo.get_matter("M-ALPHA", "firm_a") is not None
        assert repo.get_matter("M-BETA", "firm_b") is not None
