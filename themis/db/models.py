"""SQLAlchemy ORM models for the V3 canonical matter store.

These are the *business state* models — status machine, next_action for the
ARQ worker, firm/lawyer identity. They live in themis/db/ and are separate
from the workspace Pydantic models in themis/workspace/models.py which track
rich legal objects (facts, authorities, drafts).

The matters table already exists (created by 001_workspace.sql). V3.1 adds
Firm, Lawyer, and the new V3 columns via Alembic migration 001_matters.py.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Firm(Base):
    """Tenant identity. Every matter belongs to exactly one firm."""

    __tablename__ = "firms"

    firm_id: str = Column(String, primary_key=True)
    name: str = Column(Text, nullable=False)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())

    lawyers = relationship("Lawyer", back_populates="firm")
    matters = relationship("MatterRow", back_populates="firm", foreign_keys="MatterRow.firm_id")


class Lawyer(Base):
    """Lawyer identity within a firm. Single writer of SOUL.md and mem0."""

    __tablename__ = "lawyers"

    lawyer_id: str = Column(String, primary_key=True)
    firm_id: str = Column(String, ForeignKey("firms.firm_id"), nullable=False)
    name: str = Column(Text, nullable=False)
    email: Optional[str] = Column(Text)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())

    firm = relationship("Firm", back_populates="lawyers")
    matters = relationship("MatterRow", back_populates="lawyer", foreign_keys="MatterRow.lawyer_id")


# V3 status values (§4 of V3_ARCHITECTURE.md)
# Legacy workspace statuses (active, closed, archived) kept for backward compat.
MATTER_STATUSES = frozenset({
    "intake", "researching", "drafting", "reviewing",
    "awaiting_approval", "verifying", "complete", "paused", "error",
    "active", "closed", "archived",
})


class MatterRow(Base):
    """Canonical V3 matter business state.

    This is the single source of truth for matter status and workflow.
    The ARQ worker reads next_action from here to resume paused matters.
    Senior Counsel is the ONLY node that writes to this via persist_matter().
    """

    __tablename__ = "matters"
    # WHY extend_existing: the workspace migration already created this table.
    # We add V3 columns via Alembic; the ORM definition here reflects the
    # full merged schema post-migration.
    __table_args__ = {"extend_existing": True}

    # --- Identity (existing columns) ---
    matter_id: str = Column(String, primary_key=True)
    firm_id: str = Column(String, ForeignKey("firms.firm_id"), nullable=False)
    user_id: Optional[str] = Column(String)  # workspace compat; prefer lawyer_id
    title: str = Column(Text, nullable=False)
    matter_type: str = Column(Text, nullable=False)
    jurisdiction: Optional[str] = Column(Text)

    # --- V3: lawyer identity ---
    # WHY nullable: existing workspace rows have user_id but not lawyer_id.
    # The migration populates lawyer_id = user_id for legacy rows.
    lawyer_id: Optional[str] = Column(String, ForeignKey("lawyers.lawyer_id"))

    # --- V3: workflow state ---
    status: str = Column(Text, nullable=False, default="intake")
    # next_action: {"node": "research", "params": {...}} — ARQ deserialises directly
    next_action: Optional[dict] = Column(JSONB)
    priority: int = Column(Integer, default=5)
    deadline: Optional[date] = Column(Date)

    # --- V3: semantic fields (mirrored to Qdrant async) ---
    parties: list = Column(JSONB, default=list)
    summary: Optional[str] = Column(Text)
    key_facts: list = Column(JSONB, default=list)
    statutes_cited: list = Column(JSONB, default=list)
    risk_score: Optional[float] = Column(Float)

    # --- Timestamps ---
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    firm = relationship("Firm", back_populates="matters", foreign_keys=[firm_id])
    lawyer = relationship("Lawyer", back_populates="matters", foreign_keys=[lawyer_id])
