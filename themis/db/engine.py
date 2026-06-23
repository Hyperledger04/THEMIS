"""Async SQLAlchemy engine + firm-scoped session factory.

Every session that touches the matters table MUST go through scoped_session()
so that SET LOCAL app.firm_id fires before any query. This is the enforcement
point for Postgres Row-Level Security (V3 Invariant #4).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql import text


def _normalize_url(postgres_url: str) -> str:
    """Convert postgres:// or postgresql:// to the psycopg3 async dialect."""
    for prefix in ("postgresql://", "postgres://"):
        if postgres_url.startswith(prefix):
            # WHY: SQLAlchemy 2.0 uses postgresql+psycopg:// for the psycopg3
            # driver (both sync and async). psycopg is already in pyproject.toml;
            # no extra asyncpg dependency needed.
            return postgres_url.replace(prefix, "postgresql+psycopg://", 1)
    return postgres_url


def build_session_factory(postgres_url: str) -> async_sessionmaker[AsyncSession]:
    url = _normalize_url(postgres_url)
    engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def scoped_session(
    session_factory: async_sessionmaker[AsyncSession],
    firm_id: str,
) -> AsyncGenerator[AsyncSession, None]:
    """Open a session and immediately scope it to firm_id via SET LOCAL.

    WHY SET LOCAL (not SET): SET LOCAL applies only to the current transaction.
    Without LOCAL, the setting would persist across pooled connections and
    silently expose one firm's data to another firm's queries.
    """
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text("SET LOCAL app.firm_id = :fid").bindparams(fid=str(firm_id))
            )
            yield session
