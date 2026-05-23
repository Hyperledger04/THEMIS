"""Tests for the Telegram gateway — allowlist, session management, routing."""

import pytest

from lexagent.config import LexConfig
from lexagent.gateway.telegram import (
    TelegramSession,
    _get_or_create_session,
    _is_allowed,
    _sessions,
)


# ---------------------------------------------------------------------------
# Helper: build a minimal LexConfig with no real tokens
# ---------------------------------------------------------------------------

def _cfg(allowed_users: list[int] | None = None) -> LexConfig:
    # WHY: LexConfig uses Pydantic Settings; constructor accepts Python field names
    # (snake_case), not env var names (UPPER_CASE).
    kwargs: dict = {}
    if allowed_users is not None:
        kwargs["telegram_allowed_users"] = allowed_users
    return LexConfig(**kwargs)


# ---------------------------------------------------------------------------
# _is_allowed
# ---------------------------------------------------------------------------

def test_empty_allowlist_permits_everyone():
    cfg = _cfg(allowed_users=[])
    assert _is_allowed(12345, cfg) is True
    assert _is_allowed(99999, cfg) is True


def test_allowlist_permits_listed_users():
    cfg = _cfg(allowed_users=[111, 222, 333])
    assert _is_allowed(111, cfg) is True
    assert _is_allowed(222, cfg) is True


def test_allowlist_blocks_unlisted_users():
    cfg = _cfg(allowed_users=[111, 222])
    assert _is_allowed(999, cfg) is False


def test_none_allowlist_treated_as_empty():
    cfg = _cfg(allowed_users=None)
    # None allowlist → open access
    assert _is_allowed(54321, cfg) is True


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def test_get_or_create_session_creates_new_session():
    _sessions.clear()
    session = _get_or_create_session(user_id=42, cfg=_cfg())
    assert isinstance(session, TelegramSession)
    assert session.matter_id.startswith("M-")
    assert session.completed is False
    assert session.graph_state is None


def test_get_or_create_session_returns_existing_session():
    _sessions.clear()
    first = _get_or_create_session(user_id=42, cfg=_cfg())
    first.matter_id = "M-PINNED"
    second = _get_or_create_session(user_id=42, cfg=_cfg())
    assert second.matter_id == "M-PINNED"


def test_different_users_get_different_sessions():
    _sessions.clear()
    cfg = _cfg()
    s1 = _get_or_create_session(user_id=1, cfg=cfg)
    s2 = _get_or_create_session(user_id=2, cfg=cfg)
    s1.matter_id = "M-USER1"
    assert s2.matter_id != "M-USER1"


def test_session_matter_id_is_unique_across_users():
    _sessions.clear()
    cfg = _cfg()
    ids = {_get_or_create_session(user_id=i, cfg=cfg).matter_id for i in range(10)}
    assert len(ids) == 10


# ---------------------------------------------------------------------------
# TelegramSession dataclass
# ---------------------------------------------------------------------------

def test_telegram_session_defaults():
    s = TelegramSession(matter_id="M-TEST")
    assert s.matter_id == "M-TEST"
    assert s.graph_state is None
    assert s.completed is False


def test_telegram_session_stores_graph_state():
    s = TelegramSession(matter_id="M-TEST")
    s.graph_state = {"matter_type": "injunction", "intake_complete": True}
    assert s.graph_state["matter_type"] == "injunction"


def test_telegram_session_can_be_marked_completed():
    s = TelegramSession(matter_id="M-TEST")
    s.completed = True
    assert s.completed is True


# ---------------------------------------------------------------------------
# _escape_md (helper used in formatting)
# ---------------------------------------------------------------------------

def test_escape_md_escapes_special_chars():
    from lexagent.gateway.telegram import _escape_md
    result = _escape_md("Hello (world) — test!")
    assert "\\(" in result
    assert "\\)" in result
    assert "\\!" in result


def test_escape_md_leaves_plain_text_unchanged():
    from lexagent.gateway.telegram import _escape_md
    result = _escape_md("Hello world")
    assert result == "Hello world"
