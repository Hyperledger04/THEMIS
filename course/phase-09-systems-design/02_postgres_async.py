"""
Phase 9 — 02: Async Postgres with asyncpg
==========================================
Run:  pip install asyncpg
      python 02_postgres_async.py
      (works in mock mode without a real Postgres — safe to run anywhere)
"""

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime

# ── SECTION 1: WHY ASYNC POSTGRES ───────────────────────────────────────────
#
# LexAgent runs multiple graph invocations concurrently.
# Each graph node may read/write a LangGraph checkpoint.
#
# SQLite (used in dev) is fine for one user, but it uses file-level locks:
#   User A graph run ──► writes checkpoint.db  ← LOCKED
#   User B graph run ──► writes checkpoint.db  ← BLOCKED until A finishes
#
# Postgres with asyncpg uses a connection pool:
#   User A graph run ──► acquires conn-1, writes, releases
#   User B graph run ──► acquires conn-2 simultaneously ← no lock
#
# asyncpg is the fastest Python Postgres driver — it speaks the raw Postgres
# wire protocol without wrapping psycopg2.
#
# In LexAgent: lexagent/runtime/postgres.py wraps asyncpg and exposes
# `setup_checkpointer(cfg)` which returns a LangGraph-compatible checkpointer.

try:
    import asyncpg  # type: ignore
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    print("asyncpg not installed — running in MOCK mode (all DB calls are stubs).")
    print("Install with:  pip install asyncpg\n")


# ── SECTION 2: THE CONNECTION POOL PATTERN ──────────────────────────────────
#
# A connection pool keeps N persistent TCP connections to Postgres open.
# Handlers borrow a connection (`async with pool.acquire() as conn:`)
# and return it when done. No TCP handshake overhead per request.
#
# asyncpg pool pattern:
#
#   pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
#
#   async with pool.acquire() as conn:
#       row = await conn.fetchrow("SELECT * FROM matters WHERE id = $1", matter_id)
#
# WHY `async with` instead of `conn = pool.acquire()`:
#   The context manager guarantees the connection is returned to the pool
#   even if an exception is raised inside the block.


@dataclass
class MockConnection:
    """
    Stand-in for an asyncpg connection object.
    Mirrors the asyncpg API surface used in LexAgent so the code
    looks identical — only the import changes in production.
    """
    _rows: list = field(default_factory=list)

    async def execute(self, query: str, *args) -> str:
        print(f"   [mock SQL] EXECUTE: {query.strip()[:60]} args={args}")
        return "OK"

    async def fetchrow(self, query: str, *args) -> dict | None:
        print(f"   [mock SQL] FETCHROW: {query.strip()[:60]} args={args}")
        if args and self._rows:
            return self._rows[0]
        return None

    async def fetch(self, query: str, *args) -> list[dict]:
        print(f"   [mock SQL] FETCH: {query.strip()[:60]} args={args}")
        return self._rows


class MockPool:
    """
    Stand-in for asyncpg.Pool.  Provides `acquire()` as an async context manager.
    """
    def __init__(self, rows: list | None = None):
        self._rows = rows or []

    def acquire(self):
        return self

    async def __aenter__(self) -> MockConnection:
        return MockConnection(_rows=self._rows)

    async def __aexit__(self, *_):
        pass

    async def close(self):
        pass


# ── SECTION 3: LANGGRAPH POSTGRES TABLES ────────────────────────────────────
#
# When you pass a Postgres checkpointer to LangGraph, it creates three tables:
#
#   checkpoints          — snapshot of the full LexState at each graph step
#   checkpoint_writes    — individual key-value writes within a step
#   checkpoint_migrations — schema version tracking (like Alembic for the checkpointer)
#
# You never write to these tables yourself — LangGraph manages them.
# But you need to know they exist to:
#   a) grant the DB user the right permissions
#   b) understand what you're querying when debugging a stuck graph run
#
# WHY store checkpoints in Postgres instead of SQLite?
#   • Multiple LexAgent API instances can share the same checkpoint store.
#   • A user can start a draft on their laptop and resume on their phone.
#   • The graph survives server restarts — state is in DB, not in-process memory.

LANGGRAPH_SCHEMA_DDL = """
-- LangGraph creates these automatically via AsyncPostgresSaver.setup().
-- Shown here for teaching — do NOT run this manually.

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id    TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type         TEXT,
    checkpoint    JSONB NOT NULL,    -- full LexState snapshot
    metadata      JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id    TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    idx          INTEGER NOT NULL,
    channel      TEXT NOT NULL,     -- which LexState key was written
    type         TEXT,
    value        JSONB,             -- the value written to that key
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
);
"""


# ── SECTION 4: SETUP CHECKPOINTER (mirrors lexagent/graph.py) ───────────────
#
# In the real codebase, lexagent/graph.py calls `setup_checkpointer(cfg)` to
# get either a SQLite or Postgres checkpointer based on config:
#
#   if cfg.postgres_dsn:
#       saver = AsyncPostgresSaver(pool)
#       await saver.setup()    # creates the 3 tables above
#   else:
#       saver = AsyncSqliteSaver.from_conn_string(cfg.sqlite_path)
#
# The graph is then compiled with the checkpointer:
#   graph = builder.compile(checkpointer=saver)


async def setup_checkpointer(dsn: str | None):
    """
    Returns a (mock or real) connection pool.

    In production this is async-postgres-backed LangGraph checkpointer.
    Here we return a MockPool so the file runs without a DB.

    Mirrors the pattern in: lexagent/runtime/postgres.py
    """
    if not dsn:
        print("No DSN provided — using MockPool (SQLite would be used in real dev).")
        return MockPool(rows=[
            {
                "matter_id": "abc123",
                "firm_id": "personal",
                "status": "complete",
                "created_at": datetime.utcnow().isoformat(),
            }
        ])

    if not ASYNCPG_AVAILABLE:
        print("asyncpg not installed — falling back to MockPool.")
        return MockPool()

    # REAL asyncpg pool (only runs when DSN is provided and asyncpg is installed)
    try:
        pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
        print(f"Connected to Postgres: {dsn[:40]}...")
        return pool
    except Exception as exc:
        print(f"Postgres connection failed ({exc}) — falling back to MockPool.")
        return MockPool()


# ── SECTION 5: SAMPLE REPOSITORY PATTERN ────────────────────────────────────
#
# In production, lexagent uses a thin "repository" layer:
#   async def save_matter(pool, matter: dict) -> None:
#       async with pool.acquire() as conn:
#           await conn.execute(INSERT_MATTER_SQL, ...)
#
# This separates SQL from business logic — nodes call the repository,
# not raw SQL.

INSERT_MATTER_SQL = """
INSERT INTO matters (matter_id, firm_id, user_id, brief, status, created_at)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (matter_id) DO UPDATE SET status = EXCLUDED.status
"""

SELECT_MATTER_SQL = """
SELECT matter_id, firm_id, status, created_at
FROM matters
WHERE matter_id = $1 AND firm_id = $2
"""


async def save_matter(pool, matter_id: str, firm_id: str, user_id: str,
                      brief: str, status: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            INSERT_MATTER_SQL,
            matter_id, firm_id, user_id, brief, status,
            datetime.utcnow().isoformat(),
        )


async def get_matter(pool, matter_id: str, firm_id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(SELECT_MATTER_SQL, matter_id, firm_id)
        return dict(row) if row else None


# ── SECTION 6: SQLite vs Postgres DECISION TABLE ────────────────────────────
#
# ┌──────────────────┬─────────────────────┬──────────────────────────────┐
# │ Factor           │ SQLite              │ Postgres (asyncpg)           │
# ├──────────────────┼─────────────────────┼──────────────────────────────┤
# │ Setup            │ zero — built-in     │ needs server / Docker        │
# │ Concurrent writes│ one writer at a time│ unlimited (MVCC)             │
# │ Network access   │ local file only     │ any host with credentials    │
# │ Scales to        │ ~1 user             │ thousands of users           │
# │ LangGraph support│ AsyncSqliteSaver    │ AsyncPostgresSaver           │
# │ Use when         │ dev / single user   │ staging / prod / multi-user  │
# └──────────────────┴─────────────────────┴──────────────────────────────┘
#
# LexAgent auto-selects based on cfg.postgres_dsn:
#   • set: Postgres checkpointer
#   • unset: SQLite at ~/.lexagent/sessions.db


# ── SECTION 7: FULL DEMO ─────────────────────────────────────────────────────

async def main():
    print("── Async Postgres Demo ──\n")

    # 1. Acquire pool (mock in this demo)
    pool = await setup_checkpointer(dsn=None)

    # 2. Write a matter
    print("\n── Saving a matter ──")
    await save_matter(pool, "m001", "firm_a", "u1",
                      "Writ petition for bail", "pending")

    # 3. Read it back
    print("\n── Fetching matter m001 ──")
    matter = await get_matter(pool, "m001", "firm_a")
    if matter:
        print(f"   Found: {matter}")
    else:
        print("   Not found (expected in mock mode — MockPool returns preset rows)")

    # 4. Show what the LangGraph checkpoint table would look like
    print("\n── LangGraph checkpoint schema (DDL preview) ──")
    for line in LANGGRAPH_SCHEMA_DDL.strip().splitlines()[:10]:
        print(f"   {line}")
    print("   ...")

    # 5. Close pool
    await pool.close()
    print("\n── Pool closed — demo complete ──")


if __name__ == "__main__":
    asyncio.run(main())


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
#
# 1. Open lexagent/graph.py.
#    Find the `setup_checkpointer` call (or equivalent).
#    Does it branch on a DSN env var?  Which config field controls the choice
#    between SQLite and Postgres?
#
# 2. Open lexagent/runtime/postgres.py.
#    What is the `min_size` and `max_size` of the connection pool?
#    What happens to a graph run if all connections are busy?
#
# 3. The LangGraph `checkpoint_writes` table stores individual key writes.
#    If the `draft` node writes `{"draft_output": "...", "citations_verified": False}`,
#    how many rows appear in `checkpoint_writes` for that step?
#
# 4. `ON CONFLICT (matter_id) DO UPDATE` in INSERT_MATTER_SQL is an "upsert".
#    Why is an upsert safer than a plain INSERT when a graph node might retry
#    after a transient failure?
#
# 5. asyncpg uses positional placeholders ($1, $2) instead of ? (sqlite) or %s
#    (psycopg2).  If you accidentally swap the order of arguments passed to
#    `conn.execute()`, what kind of bug could occur silently?
