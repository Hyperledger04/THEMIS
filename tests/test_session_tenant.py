"""Tests for session store tenant isolation and schema migration."""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from themis.memory.session_store import (
    init_db,
    list_sessions,
    save_session,
    search_sessions,
    get_session_state,
    update_session,
)


def _make_state(matter_id: str, matter_type: str = "writ") -> dict:
    return {
        "matter_id": matter_id,
        "matter_type": matter_type,
        "parties": {"petitioner": "Ravi Singh", "respondent": "State"},
        "jurisdiction": "Delhi HC",
        "purpose": "test",
        "plain_english_summary": f"summary for {matter_id}",
        "messages": [],
    }


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "sessions.db")


def test_schema_has_firm_id_column(tmp_db):
    init_db(tmp_db)
    conn = sqlite3.connect(tmp_db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    conn.close()
    assert "firm_id" in cols, "sessions table must have firm_id column"
    assert "user_id" in cols, "sessions table must have user_id column"


def test_reminders_schema_has_firm_id(tmp_db):
    init_db(tmp_db)
    conn = sqlite3.connect(tmp_db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(reminders)")}
    conn.close()
    assert "firm_id" in cols


def test_firm_a_cannot_read_firm_b_sessions(tmp_db):
    save_session(_make_state("M001"), sessions_db=tmp_db, firm_id="firm_a", user_id="u1")
    save_session(_make_state("M002"), sessions_db=tmp_db, firm_id="firm_b", user_id="u2")

    rows_a = list_sessions(sessions_db=tmp_db, firm_id="firm_a")
    ids_a = {r["matter_id"] for r in rows_a}

    assert "M001" in ids_a
    assert "M002" not in ids_a, "firm_b matter must not appear in firm_a listing"


def test_get_session_state_is_firm_scoped(tmp_db):
    state_a = _make_state("M001")
    state_a["purpose"] = "firm_a_purpose"
    save_session(state_a, sessions_db=tmp_db, firm_id="firm_a", user_id="u1")

    # firm_b should not find firm_a's matter
    result = get_session_state("M001", sessions_db=tmp_db, firm_id="firm_b")
    assert result is None, "firm_b must not read firm_a state"


def test_search_sessions_is_firm_scoped(tmp_db):
    save_session(_make_state("M001", "writ"), sessions_db=tmp_db, firm_id="firm_a", user_id="u1")
    save_session(_make_state("M002", "writ"), sessions_db=tmp_db, firm_id="firm_b", user_id="u2")

    hits = search_sessions("writ", sessions_db=tmp_db, firm_id="firm_a")
    ids = {h["matter_id"] for h in hits}
    assert "M001" in ids
    assert "M002" not in ids
