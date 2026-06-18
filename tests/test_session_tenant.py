"""Tests for session store tenant isolation, schema migration, and AES-GCM encryption."""
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


def test_update_session_is_firm_scoped(tmp_db):
    """update_session from firm_b must not overwrite firm_a's row."""
    from themis.memory.session_store import update_session

    state_a = _make_state("M001")
    save_session(state_a, sessions_db=tmp_db, firm_id="firm_a", user_id="u1")

    state_b = _make_state("M001")
    state_b["purpose"] = "firm_b_purpose"
    update_session(state_b, sessions_db=tmp_db, firm_id="firm_b", user_id="u2")

    result_a = get_session_state("M001", sessions_db=tmp_db, firm_id="firm_a")
    assert result_a["purpose"] == "test", "firm_a session must not be overwritten by firm_b update"

    result_b = get_session_state("M001", sessions_db=tmp_db, firm_id="firm_b")
    assert result_b is not None
    assert result_b["purpose"] == "firm_b_purpose"


# ── AES-GCM encryption of state_json ────────────────────────────────────────

import os


def test_state_json_encrypted_when_key_set(tmp_db, monkeypatch):
    """When LEX_ENCRYPTION_KEY and LEX_MULTI_TENANT are set, state_json must be encrypted."""
    from themis.memory.session_store import _session_cfg
    _session_cfg.cache_clear()  # ensure fresh LexConfig with monkeypatched env
    monkeypatch.setenv("LEX_ENCRYPTION_KEY", "a" * 64)   # 64 hex chars = 32 bytes
    monkeypatch.setenv("LEX_MULTI_TENANT", "true")

    state = _make_state("M-ENC")
    save_session(state, sessions_db=tmp_db, firm_id="firm_enc", user_id="u1")

    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT state_json FROM sessions WHERE matter_id='M-ENC'").fetchone()
    conn.close()

    raw_blob = row[0]
    # LEXENC: prefix is 7 bytes = "LEXENC:" in ASCII; when hex-encoded it's 14 chars "4c455845" prefix
    # Actually the sentinel is stored as hex string starting with the hex of "LEXENC:"
    assert "M-ENC" not in raw_blob, "Plaintext matter_id must NOT appear in encrypted blob"


def test_state_json_decrypts_correctly(tmp_db, monkeypatch):
    """get_session_state must transparently decrypt and return the original state."""
    from themis.memory.session_store import _session_cfg
    _session_cfg.cache_clear()
    monkeypatch.setenv("LEX_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("LEX_MULTI_TENANT", "true")

    state = _make_state("M-ENC2")
    save_session(state, sessions_db=tmp_db, firm_id="firm_enc", user_id="u1")

    recovered = get_session_state("M-ENC2", sessions_db=tmp_db, firm_id="firm_enc")
    assert recovered is not None
    assert recovered["matter_id"] == "M-ENC2"


def test_state_json_plaintext_when_no_key(tmp_db):
    """Without LEX_ENCRYPTION_KEY, state_json must be plaintext JSON."""
    from themis.memory.session_store import _session_cfg
    _session_cfg.cache_clear()  # ensure no leaked encryption key from prior test
    state = _make_state("M-PLAIN")
    save_session(state, sessions_db=tmp_db, firm_id="default", user_id="u1")

    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT state_json FROM sessions WHERE matter_id='M-PLAIN'").fetchone()
    conn.close()

    parsed = json.loads(row[0])   # must parse as JSON without decryption
    assert parsed["matter_id"] == "M-PLAIN"
