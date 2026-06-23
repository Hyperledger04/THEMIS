"""
V3.1 gate: tests for themis/db/matter_store.py — canonical matter CRUD.

Unit tests mock the SQLAlchemy async session so no live Postgres is needed.
The RLS isolation test (TestRLSIsolation) also runs without live Postgres —
it verifies that get_matter() passes firm_id to scoped_session and that a
None result from the DB is returned as-is (the RLS policy enforces the actual
filter in production).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from themis.db.matter_store import MatterStore
from themis.db.models import MatterRow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(**overrides: Any) -> MatterRow:
    base = MatterRow(
        matter_id="matter_test_abc",
        firm_id="firm_alpha",
        lawyer_id="lawyer_1",
        user_id="user_1",
        title="NI Act Complaint — HDFC Cheque",
        matter_type="ni_act_138",
        jurisdiction="delhi",
        status="intake",
        next_action=None,
        priority=5,
        deadline=None,
        parties=[],
        summary=None,
        key_facts=[],
        statutes_cited=[],
        risk_score=None,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _mock_store() -> tuple[MatterStore, MagicMock]:
    """Return (store, mock_session_factory) for patching."""
    factory = MagicMock()
    store = MatterStore(session_factory=factory)
    return store, factory


def _scoped(mock_session: AsyncMock):
    """Return an async context manager that yields mock_session."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# MatterRow — model-level checks
# ---------------------------------------------------------------------------

class TestMatterRowModel:
    def test_next_action_accepts_structured_dict(self):
        row = _row(next_action={"node": "research", "params": {"focus": "limitation"}})
        assert row.next_action["node"] == "research"

    def test_parties_defaults_to_list(self):
        row = _row()
        assert isinstance(row.parties, list)

    def test_status_defaults_to_intake(self):
        row = _row()
        assert row.status == "intake"


# ---------------------------------------------------------------------------
# MatterStore — CRUD unit tests (mocked session)
# ---------------------------------------------------------------------------

class TestMatterStoreCRUD:
    @pytest.mark.asyncio
    async def test_create_matter_adds_and_flushes(self):
        store, _ = _mock_store()
        row = _row()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        with patch("themis.db.matter_store.scoped_session", return_value=_scoped(mock_session)):
            result = await store.create_matter(row)

        mock_session.add.assert_called_once_with(row)
        mock_session.flush.assert_called_once()
        assert result is row

    @pytest.mark.asyncio
    async def test_get_matter_returns_row(self):
        store, _ = _mock_store()
        row = _row()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("themis.db.matter_store.scoped_session", return_value=_scoped(mock_session)):
            result = await store.get_matter("matter_test_abc", firm_id="firm_alpha")

        assert result is row

    @pytest.mark.asyncio
    async def test_get_matter_returns_none_when_not_found(self):
        store, _ = _mock_store()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("themis.db.matter_store.scoped_session", return_value=_scoped(mock_session)):
            result = await store.get_matter("missing_id", firm_id="firm_alpha")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_matter_executes_update(self):
        store, _ = _mock_store()
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        with patch("themis.db.matter_store.scoped_session", return_value=_scoped(mock_session)):
            await store.update_matter(
                matter_id="matter_test_abc",
                firm_id="firm_alpha",
                fields={"status": "researching", "priority": 3},
            )

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_matter_empty_fields_is_noop(self):
        """Updating zero fields should not touch the DB."""
        store, _ = _mock_store()
        mock_session = AsyncMock()

        with patch("themis.db.matter_store.scoped_session", return_value=_scoped(mock_session)):
            await store.update_matter(
                matter_id="matter_test_abc",
                firm_id="firm_alpha",
                fields={},
            )

        mock_session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# RLS isolation — firm boundary enforcement
# ---------------------------------------------------------------------------

class TestRLSIsolation:
    """
    Verifies that get_matter() passes firm_id to scoped_session (which runs
    SET LOCAL app.firm_id = '...'). In production Postgres, the RLS policy
    then filters any row whose firm_id doesn't match — so a cross-firm query
    returns None even if the matter_id exists.
    """

    @pytest.mark.asyncio
    async def test_get_matter_passes_firm_id_to_scoped_session(self):
        store, _ = _mock_store()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("themis.db.matter_store.scoped_session", return_value=_scoped(mock_session)) as mock_scope:
            await store.get_matter("matter_test_abc", firm_id="firm_wrong")

        # scoped_session must be called with the firm_id so RLS fires
        mock_scope.assert_called_once()
        _, kwargs = mock_scope.call_args
        assert kwargs.get("firm_id") == "firm_wrong" or mock_scope.call_args.args[1] == "firm_wrong"

    @pytest.mark.asyncio
    async def test_cross_firm_get_returns_none(self):
        """Simulates RLS returning no row for a cross-firm lookup."""
        store, _ = _mock_store()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # RLS filtered it
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("themis.db.matter_store.scoped_session", return_value=_scoped(mock_session)):
            result = await store.get_matter("matter_test_abc", firm_id="firm_other")

        assert result is None


# ---------------------------------------------------------------------------
# persist_matter — Senior Counsel invariant
# ---------------------------------------------------------------------------

class TestPersistMatter:
    """
    persist_matter() is the ONLY path from SeniorCounselState → Postgres.
    (V3 Invariant #1: only Senior Counsel calls this.)
    """

    @pytest.mark.asyncio
    async def test_persist_matter_updates_status_and_next_action(self):
        store, _ = _mock_store()
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        state = {
            "matter_id": "matter_test_abc",
            "firm_id": "firm_alpha",
            "status": "drafting",
            "next_action": {"node": "draft", "params": {}},
            "research_findings": [{"title": "AIR 1978 SC 597"}],
            "draft_output": None,
        }

        with patch("themis.db.matter_store.scoped_session", return_value=_scoped(mock_session)):
            await store.persist_matter(state)

        # Must write to DB — not a no-op
        mock_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_persist_matter_next_action_must_be_dict_or_none(self):
        """next_action free text violates V3 Invariant #3."""
        store, _ = _mock_store()
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        state = {
            "matter_id": "matter_test_abc",
            "firm_id": "firm_alpha",
            "status": "intake",
            "next_action": "go do research",  # invalid — must be dict
        }

        with patch("themis.db.matter_store.scoped_session", return_value=_scoped(mock_session)):
            with pytest.raises(ValueError, match="next_action"):
                await store.persist_matter(state)
