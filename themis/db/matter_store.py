"""MatterStore — canonical CRUD for the V3 matter business state.

V3 Invariants enforced here (§22 of V3_ARCHITECTURE.md):
  #1 — Only Senior Counsel calls persist_matter(). Other callers must not.
  #3 — next_action is always structured JSON (dict). Never free text.
  #4 — Every query to matters sets app.firm_id first via scoped_session().
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from themis.db.engine import scoped_session
from themis.db.models import MatterRow


class MatterStore:
    """Async CRUD for the canonical V3 matter table.

    Constructed with a session_factory from build_session_factory(). Every
    public method enforces firm_id scoping via scoped_session() so callers
    never have to remember to set app.firm_id manually.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_matter(
        self, matter_id: str, firm_id: str
    ) -> Optional[MatterRow]:
        """Fetch a matter by ID, scoped to firm_id.

        Returns None if the matter doesn't exist or belongs to a different
        firm (RLS policy filters it; we never distinguish the two cases to
        avoid leaking existence information).
        """
        async with scoped_session(self._session_factory, firm_id) as session:
            result = await session.execute(
                select(MatterRow).where(
                    MatterRow.matter_id == matter_id,
                    MatterRow.firm_id == firm_id,
                )
            )
            return result.scalar_one_or_none()

    async def list_matters(
        self,
        firm_id: str,
        status: Optional[str] = None,
    ) -> list[MatterRow]:
        """List matters for a firm, optionally filtered by status."""
        async with scoped_session(self._session_factory, firm_id) as session:
            q = select(MatterRow).where(MatterRow.firm_id == firm_id)
            if status is not None:
                q = q.where(MatterRow.status == status)
            q = q.order_by(MatterRow.updated_at.desc())
            result = await session.execute(q)
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create_matter(self, row: MatterRow) -> MatterRow:
        """Insert a new matter row. Caller provides the full MatterRow object."""
        async with scoped_session(self._session_factory, row.firm_id) as session:
            session.add(row)
            await session.flush()
        return row

    async def update_matter(
        self,
        matter_id: str,
        firm_id: str,
        fields: dict[str, Any],
    ) -> None:
        """Patch specific columns on a matter. No-op if fields is empty.

        Only pass fields that changed — do not send the full row.
        Always stamps updated_at to now().
        """
        if not fields:
            return
        fields["updated_at"] = datetime.now(tz=timezone.utc)
        async with scoped_session(self._session_factory, firm_id) as session:
            await session.execute(
                update(MatterRow)
                .where(MatterRow.matter_id == matter_id, MatterRow.firm_id == firm_id)
                .values(**fields)
            )

    # ------------------------------------------------------------------
    # persist_matter — Senior Counsel only (V3 Invariant #1)
    # ------------------------------------------------------------------

    async def persist_matter(self, state: dict[str, Any]) -> None:
        """Sync SeniorCounselState → Postgres. Called ONLY by Senior Counsel.

        This is the single write path from graph state to canonical matter
        business state. It MUST:
          - Extract matter_id and firm_id from state
          - Validate next_action is a dict or None (never free text)
          - Map relevant SeniorCounselState fields to MatterRow columns
          - Call update_matter() with the mapped fields

        V3 Invariant #3: next_action must be structured JSON.
        The ARQ worker deserialises it directly — no LLM parsing step.

        ── YOUR TURN ────────────────────────────────────────────────────
        Implement the field mapping below. Consider:

        1. Which fields from SeniorCounselState should write back to Postgres?
           (status, next_action, summary, key_facts, statutes_cited, risk_score)

        2. Should research_findings write to key_facts directly, or only after
           the Reviewer node confirms them?

        3. What triggers the Qdrant async index? (index_matter_job from V3.4)
           For now, leave that call as a TODO comment.

        Guidance: update_matter() is already wired. You need to build the
        fields dict from state and call self.update_matter(). Keep it under
        10 lines of logic.
        ─────────────────────────────────────────────────────────────────
        """
        matter_id: str = state.get("matter_id", "")
        firm_id: str = state.get("firm_id", "")

        # V3 Invariant #3: next_action must be a dict or None, never a string.
        next_action = state.get("next_action")
        if next_action is not None and not isinstance(next_action, dict):
            raise ValueError(
                f"next_action must be a dict (got {type(next_action).__name__!r}). "
                "V3 Invariant #3: ARQ worker deserialises next_action directly — "
                "free text would require an extra LLM step and is forbidden."
            )

        fields: dict[str, Any] = {}

        if state.get("status"):
            fields["status"] = state["status"]
        if next_action is not None:
            fields["next_action"] = next_action

        # statutes_cited: Researcher output — write when available
        if state.get("statutes_cited"):
            fields["statutes_cited"] = state["statutes_cited"]

        # key_facts: only after Reviewer has signed off (review_result non-empty)
        # WHY: raw research_findings are unvetted. Writing them before review
        # would make hallucinated propositions look like confirmed legal facts.
        if state.get("review_result") and state.get("research_findings"):
            fields["key_facts"] = [
                f.get("title", "")
                for f in state["research_findings"]
                if f.get("verified")
            ]

        # risk_score: Reviewer output — optional, skip if Reviewer hasn't run
        review = state.get("review_result") or {}
        if review.get("risk_score") is not None:
            fields["risk_score"] = review["risk_score"]

        await self.update_matter(matter_id, firm_id, fields)
        # TODO (V3.4): enqueue index_matter_job(matter_id) on ARQ so Qdrant
        # summary embeddings stay fresh without blocking Senior Counsel.
