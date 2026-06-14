# Tests for Phase 2: Memory & Identity
# Covers: soul.py, matter_memory.py, session_store.py
# Uses tmp_path fixture (pytest built-in) so all files land in a temp dir
# and are cleaned up automatically after each test.

import json
import sqlite3
from pathlib import Path

import pytest

from themis.memory.soul import (
    SOUL_TEMPLATE,
    _parse_soul,
    append_soul_note,
    load_soul,
    save_soul,
    soul_path,
)
from themis.memory.matter_memory import (
    list_matters,
    load_matter_memory,
    load_state_snapshot,
    matter_dir,
    save_matter_memory,
)
from themis.memory.session_store import (
    get_session_state,
    init_db,
    list_sessions,
    save_session,
    search_sessions,
)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _sample_soul_data() -> dict:
    return {
        "name": "Arjun Mehta",
        "bar_enrollment": "D/456/2015, Delhi Bar Council",
        "practice_since": "2015",
        "primary_courts": "Delhi High Court, Patiala House Courts",
        "practice_areas": "Civil Litigation, Arbitration",
        "matter_types": "Injunctions, recovery suits",
        "tone": "Senior formal",
        "citation_preference": "Always include",
        "doc_length": "Comprehensive",
        "language_notes": "Avoid legalese in client letters",
        "firm_name": "",
        "firm_type": "Solo",
        "judicial_preferences": "HC Bench 12 prefers concise prayers",
        "custom_instructions": "Always verify limitation before filing",
    }


def _sample_state(matter_id: str = "M-TEST01") -> dict:
    return {
        "user_input": "I need an injunction for a property dispute",
        "matter_id": matter_id,
        "intake_complete": True,
        "citations_verified": False,
        "messages": [],  # excluded from snapshot anyway
        "matter_type": "Injunction application",
        "parties": {"plaintiff": "ABC Ltd", "defendant": "XYZ Developers"},
        "jurisdiction": "Delhi High Court",
        "jurisdiction_country": "IN",
        "purpose": "Stop construction on disputed property",
        "key_clauses": None,
        "tone_preference": None,
        "risks_to_address": None,
        "citations_required": True,
        "clarifying_questions": None,
        "research_findings": None,
        "statutes_cited": None,
        "limitation_analysis": None,
        "document_outline": None,
        "draft_output": "IN THE HIGH COURT OF DELHI\n\n...",
        "risk_annotations": None,
        "plain_english_summary": "ABC Ltd is seeking an injunction to stop XYZ from building on the disputed land.",
        "unverified_citations": None,
        "lawyer_soul": None,
        "active_skill": None,
        "error": None,
        "next_node": None,
    }


# -----------------------------------------------------------------------
# soul.py tests
# -----------------------------------------------------------------------

class TestSoulPath:
    def test_returns_path_under_home_dir(self, tmp_path):
        p = soul_path(str(tmp_path))
        assert p == tmp_path / "SOUL.md"

    def test_is_path_object(self, tmp_path):
        p = soul_path(str(tmp_path))
        assert isinstance(p, Path)


class TestSaveSoul:
    def test_creates_soul_md(self, tmp_path):
        data = _sample_soul_data()
        path = save_soul(data, str(tmp_path))
        assert path.exists()
        assert path.name == "SOUL.md"

    def test_content_contains_name(self, tmp_path):
        data = _sample_soul_data()
        save_soul(data, str(tmp_path))
        content = (tmp_path / "SOUL.md").read_text()
        assert "Arjun Mehta" in content

    def test_content_contains_bar_enrollment(self, tmp_path):
        data = _sample_soul_data()
        save_soul(data, str(tmp_path))
        content = (tmp_path / "SOUL.md").read_text()
        assert "D/456/2015" in content

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        save_soul(_sample_soul_data(), str(nested))
        assert (nested / "SOUL.md").exists()


class TestLoadSoul:
    def test_returns_none_when_no_file(self, tmp_path):
        result = load_soul(str(tmp_path))
        assert result is None

    def test_returns_dict_when_file_exists(self, tmp_path):
        save_soul(_sample_soul_data(), str(tmp_path))
        result = load_soul(str(tmp_path))
        assert isinstance(result, dict)

    def test_name_is_parsed(self, tmp_path):
        save_soul(_sample_soul_data(), str(tmp_path))
        result = load_soul(str(tmp_path))
        assert result["name"] == "Arjun Mehta"

    def test_raw_field_present(self, tmp_path):
        save_soul(_sample_soul_data(), str(tmp_path))
        result = load_soul(str(tmp_path))
        assert "raw" in result
        assert len(result["raw"]) > 10


class TestParseSoul:
    def test_parses_key_value_pairs(self):
        content = "**Name:** Test Lawyer\n**Bar Enrollment:** X/001/2020\n"
        parsed = _parse_soul(content)
        assert parsed["name"] == "Test Lawyer"
        assert parsed["bar_enrollment"] == "X/001/2020"

    def test_raw_field_contains_original(self):
        content = "**Name:** Test Lawyer\n"
        parsed = _parse_soul(content)
        assert parsed["raw"] == content

    def test_section_body_extracted(self):
        content = "## Drafting Style\nFormal tone preferred\n## Firm Context\nSolo"
        parsed = _parse_soul(content)
        assert "section_drafting_style" in parsed
        assert "Formal tone preferred" in parsed["section_drafting_style"]


class TestAppendSoulNote:
    def test_appends_note_to_custom_instructions(self, tmp_path):
        save_soul(_sample_soul_data(), str(tmp_path))
        append_soul_note("Always cite Supreme Court first", "Custom Instructions", str(tmp_path))
        content = (tmp_path / "SOUL.md").read_text()
        assert "Always cite Supreme Court first" in content

    def test_creates_section_if_missing(self, tmp_path):
        # Write a minimal SOUL.md without Custom Instructions
        (tmp_path / "SOUL.md").write_text("**Name:** Test\n", encoding="utf-8")
        append_soul_note("My note", "New Section", str(tmp_path))
        content = (tmp_path / "SOUL.md").read_text()
        assert "My note" in content


# -----------------------------------------------------------------------
# matter_memory.py tests
# -----------------------------------------------------------------------

class TestMatterDir:
    def test_creates_directory(self, tmp_path):
        d = matter_dir("M-001", str(tmp_path))
        assert d.exists()
        assert d.is_dir()

    def test_directory_name_is_matter_id(self, tmp_path):
        d = matter_dir("M-ABCDEF", str(tmp_path))
        assert d.name == "M-ABCDEF"


class TestSaveMatterMemory:
    def test_creates_memory_md(self, tmp_path):
        state = _sample_state("M-001")
        path = save_matter_memory("M-001", state, str(tmp_path))
        assert path.exists()
        assert path.name == "MEMORY.md"

    def test_memory_contains_matter_type(self, tmp_path):
        state = _sample_state("M-001")
        save_matter_memory("M-001", state, str(tmp_path))
        content = load_matter_memory("M-001", str(tmp_path))
        assert "Injunction application" in content

    def test_memory_contains_parties(self, tmp_path):
        state = _sample_state("M-001")
        save_matter_memory("M-001", state, str(tmp_path))
        content = load_matter_memory("M-001", str(tmp_path))
        assert "ABC Ltd" in content

    def test_appends_on_second_call(self, tmp_path):
        state = _sample_state("M-001")
        save_matter_memory("M-001", state, str(tmp_path))
        save_matter_memory("M-001", state, str(tmp_path))
        content = load_matter_memory("M-001", str(tmp_path))
        # Two "Session —" entries
        assert content.count("## Session —") == 2

    def test_state_snapshot_saved(self, tmp_path):
        state = _sample_state("M-001")
        save_matter_memory("M-001", state, str(tmp_path))
        snap = load_state_snapshot("M-001", str(tmp_path))
        assert snap is not None
        assert snap["matter_type"] == "Injunction application"

    def test_snapshot_excludes_messages(self, tmp_path):
        from langchain_core.messages import HumanMessage
        state = _sample_state("M-001")
        state["messages"] = [HumanMessage(content="test")]
        save_matter_memory("M-001", state, str(tmp_path))
        snap = load_state_snapshot("M-001", str(tmp_path))
        # Messages should not appear in the JSON snapshot
        assert "messages" not in snap


class TestLoadMatterMemory:
    def test_returns_none_when_no_file(self, tmp_path):
        result = load_matter_memory("M-NOPE", str(tmp_path))
        assert result is None

    def test_returns_string_when_exists(self, tmp_path):
        state = _sample_state("M-001")
        save_matter_memory("M-001", state, str(tmp_path))
        result = load_matter_memory("M-001", str(tmp_path))
        assert isinstance(result, str)
        assert len(result) > 0


class TestListMatters:
    def test_returns_empty_when_no_matters(self, tmp_path):
        result = list_matters(str(tmp_path))
        assert result == []

    def test_returns_one_entry(self, tmp_path):
        state = _sample_state("M-001")
        save_matter_memory("M-001", state, str(tmp_path))
        result = list_matters(str(tmp_path))
        assert len(result) == 1
        assert result[0]["matter_id"] == "M-001"

    def test_returns_matter_type_from_snapshot(self, tmp_path):
        state = _sample_state("M-001")
        save_matter_memory("M-001", state, str(tmp_path))
        result = list_matters(str(tmp_path))
        assert result[0]["matter_type"] == "Injunction application"


# -----------------------------------------------------------------------
# session_store.py tests
# -----------------------------------------------------------------------

def _db_url(tmp_path: Path) -> str:
    return str(tmp_path / "sessions.db")


class TestInitDb:
    def test_creates_db_file(self, tmp_path):
        db = _db_url(tmp_path)
        init_db(db)
        assert Path(db).exists()

    def test_sessions_table_exists(self, tmp_path):
        db = _db_url(tmp_path)
        init_db(db)
        conn = sqlite3.connect(db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "sessions" in tables

    def test_fts_table_exists(self, tmp_path):
        db = _db_url(tmp_path)
        init_db(db)
        conn = sqlite3.connect(db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "sessions_fts" in tables

    def test_idempotent(self, tmp_path):
        db = _db_url(tmp_path)
        init_db(db)
        init_db(db)  # Should not raise


class TestSaveSession:
    def test_returns_integer_row_id(self, tmp_path):
        db = _db_url(tmp_path)
        state = _sample_state("M-001")
        row_id = save_session(state, db)
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_session_is_retrievable(self, tmp_path):
        db = _db_url(tmp_path)
        state = _sample_state("M-002")
        save_session(state, db)
        sessions = list_sessions(db=db)
        assert len(sessions) == 1
        assert sessions[0]["matter_id"] == "M-002"

    def test_matter_type_stored(self, tmp_path):
        db = _db_url(tmp_path)
        state = _sample_state("M-003")
        save_session(state, db)
        sessions = list_sessions(db=db)
        assert sessions[0]["matter_type"] == "Injunction application"


class TestListSessions:
    def test_empty_when_no_sessions(self, tmp_path):
        db = _db_url(tmp_path)
        init_db(db)
        result = list_sessions(db=db)
        assert result == []

    def test_most_recent_first(self, tmp_path):
        db = _db_url(tmp_path)
        save_session(_sample_state("M-FIRST"), db)
        save_session(_sample_state("M-SECOND"), db)
        result = list_sessions(db=db)
        assert result[0]["matter_id"] == "M-SECOND"


class TestSearchSessions:
    def test_finds_by_matter_type(self, tmp_path):
        db = _db_url(tmp_path)
        save_session(_sample_state("M-INJ"), db)
        results = search_sessions("Injunction", sessions_db=db)
        assert len(results) >= 1

    def test_returns_empty_for_no_match(self, tmp_path):
        db = _db_url(tmp_path)
        save_session(_sample_state("M-INJ"), db)
        results = search_sessions("zzznomatch", sessions_db=db)
        assert results == []


class TestGetSessionState:
    def test_returns_none_when_no_session(self, tmp_path):
        db = _db_url(tmp_path)
        init_db(db)
        result = get_session_state("M-NOPE", db)
        assert result is None

    def test_returns_dict_when_session_exists(self, tmp_path):
        db = _db_url(tmp_path)
        state = _sample_state("M-SNAP")
        save_session(state, db)
        result = get_session_state("M-SNAP", db)
        assert isinstance(result, dict)
        assert result["matter_type"] == "Injunction application"

    def test_returns_most_recent_for_duplicate_matter_id(self, tmp_path):
        db = _db_url(tmp_path)
        s1 = _sample_state("M-DUP")
        s1["matter_type"] = "Plaint"
        s2 = _sample_state("M-DUP")
        s2["matter_type"] = "Injunction application"
        save_session(s1, db)
        save_session(s2, db)
        result = get_session_state("M-DUP", db)
        assert result["matter_type"] == "Injunction application"


# -----------------------------------------------------------------------
# Signature fix: list_sessions needs keyword arg 'db' matching parameter name
# -----------------------------------------------------------------------

# Patch: session_store uses 'sessions_db' as param name — update helper calls above
# The tests above use db=db but the function signature is sessions_db.
# Fix by wrapping:

def list_sessions(limit: int = 20, db: str = "~/.themis/sessions.db") -> list:
    from themis.memory.session_store import list_sessions as _list
    return _list(limit=limit, sessions_db=db)
