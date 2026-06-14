# tests/test_voice_session.py — Unit tests for VoiceSession and VoiceSessionStore.

import pytest

from themis.voice.session import VoiceSession, VoiceSessionStore, get_voice_session_store


# ─── VoiceSession ────────────────────────────────────────────────────────────

def test_voice_session_creation():
    s = VoiceSession(session_id="test-sid", matter_id="M-AAAA0001")
    assert s.session_id == "test-sid"
    assert s.matter_id  == "M-AAAA0001"
    assert s.channel    == "websocket"
    assert s.completed  is False
    assert s.turn_count == 0


def test_voice_session_update_from_node_state():
    s = VoiceSession(session_id="s1", matter_id="M-1")
    s.update_from_node_state({"matter_type": "writ petition", "intake_complete": False})
    assert s.graph_state["matter_type"] == "writ petition"


def test_voice_session_marks_completed_on_draft():
    s = VoiceSession(session_id="s2", matter_id="M-2")
    s.update_from_node_state({"draft_output": "This is the draft."})
    assert s.completed is True


def test_voice_session_marks_completed_on_contract_review():
    s = VoiceSession(session_id="s3", matter_id="M-3")
    s.update_from_node_state({"contract_review_output": "Risk: high."})
    assert s.completed is True


def test_voice_session_next_question_text_binary():
    s = VoiceSession(session_id="s4", matter_id="M-4")
    s.pending_questions = [
        {"field": "citations_required", "question": "Do you need citations?", "type": "binary"}
    ]
    q = s.next_question_text()
    assert "Do you need citations?" in q
    assert "yes or no" in q.lower()
    assert s.awaiting_free_text_for == "citations_required"
    assert len(s.pending_questions) == 0


def test_voice_session_next_question_text_mcq():
    s = VoiceSession(session_id="s5", matter_id="M-5")
    s.pending_questions = [
        {
            "field": "matter_type",
            "question": "What kind of document?",
            "type": "mcq",
            "options": ["Writ Petition", "Bail Application", "Legal Notice"]
        }
    ]
    q = s.next_question_text()
    assert "What kind of document?" in q
    assert "Writ Petition" in q
    assert s.awaiting_free_text_for == "matter_type"


def test_voice_session_next_question_text_returns_none_when_empty():
    s = VoiceSession(session_id="s6", matter_id="M-6")
    assert s.next_question_text() is None


def test_voice_session_pending_questions_synced_from_node_state():
    s = VoiceSession(session_id="s7", matter_id="M-7")
    qs = [{"field": "parties", "question": "Who are the parties?", "type": "open"}]
    s.update_from_node_state({"pending_questions": qs, "intake_complete": False})
    assert len(s.pending_questions) == 1


# ─── VoiceSessionStore ───────────────────────────────────────────────────────

def test_session_store_get_or_create():
    store = VoiceSessionStore()
    s = store.get_or_create("abc-123")
    assert s.session_id == "abc-123"
    assert s.matter_id.startswith("M-")


def test_session_store_returns_same_session():
    store = VoiceSessionStore()
    s1 = store.get_or_create("same-id")
    s2 = store.get_or_create("same-id")
    assert s1.matter_id == s2.matter_id


def test_session_store_get_missing():
    store = VoiceSessionStore()
    assert store.get("does-not-exist") is None


def test_session_store_delete():
    store = VoiceSessionStore()
    store.get_or_create("to-delete")
    store.delete("to-delete")
    assert store.get("to-delete") is None


def test_session_store_list_active():
    store = VoiceSessionStore()
    s1 = store.get_or_create("active-1")
    s2 = store.get_or_create("active-2")
    s2.completed = True
    active = store.list_active()
    assert any(s.session_id == "active-1" for s in active)
    assert all(s.session_id != "active-2" for s in active)


def test_session_store_len():
    store = VoiceSessionStore()
    store.get_or_create("a")
    store.get_or_create("b")
    assert len(store) == 2


def test_get_voice_session_store_is_singleton():
    """Module-level singleton should be the same object on repeated calls."""
    s1 = get_voice_session_store()
    s2 = get_voice_session_store()
    assert s1 is s2
