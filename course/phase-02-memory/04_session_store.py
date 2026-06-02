"""
Phase 02 — Memory | Lesson 04: SessionStore
============================================
LexAgent needs a place to remember every matter it has ever worked on.
This lesson teaches the SessionStore class: SQLite + FTS5 for instant
full-text search across all past session summaries.

Run this file directly:
    python course/phase-02-memory/04_session_store.py

Real implementation: lexagent/memory/session_store.py
Caller:             lexagent/cli.py  (after graph.astream completes)
"""

# ── SECTION 1: WHY SQLITE ──────────────────────────────────────────────────

# SQLite ships with Python — zero installation, zero server, single file.
# For a single-user CLI tool like LexAgent, it is the perfect default.
#
# Key advantages for LexAgent:
#   • The database is just ~/.lexagent/sessions.db — easy to back up / share
#   • FTS5 (Full-Text Search 5) is a SQLite extension bundled by default
#     in Python's sqlite3 module since Python 3.8
#   • Transactions are ACID-safe: no corruption if the process is killed mid-save
#   • No background daemon, no port conflicts

import json
import sqlite3
from datetime import datetime
from pathlib import Path


# ── SECTION 2: THE SESSIONSTORE CLASS ─────────────────────────────────────

class SessionStore:
    """Persist and search LexAgent session summaries via SQLite + FTS5.

    Usage:
        store = SessionStore(Path("/tmp/demo.db"))
        store.save("matter-001", "Writ of Mandamus: speedy trial")
        results = store.search("mandamus")
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        # WHY: we call _init_db here so callers never need to think about
        # schema creation — the store is always ready after __init__.
        self._init_db()

    def _init_db(self) -> None:
        """Create tables on first run; no-op if they already exist."""
        with sqlite3.connect(self.db_path) as conn:
            # Primary data table — matter_id is the natural key
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    matter_id  TEXT PRIMARY KEY,
                    summary    TEXT,
                    state_json TEXT,
                    created_at TEXT
                )
            """)
            # FTS5 virtual table mirrors the summary column.
            # content='sessions' tells FTS5 to read from the sessions table.
            # content_rowid='rowid' links FTS rows to real rows.
            # WHY virtual/content table: we don't duplicate text on disk;
            # FTS5 stores only the index, the original text lives in sessions.
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts
                USING fts5(summary, content='sessions', content_rowid='rowid')
            """)

    # ── SECTION 3: FTS5 AND THE REBUILD TRICK ─────────────────────────────

    # FTS5 content tables are NOT automatically updated when you INSERT into
    # the base table.  You must explicitly sync the index.
    #
    # The canonical way is:
    #   INSERT INTO sessions_fts(sessions_fts) VALUES('rebuild')
    #
    # This rebuilds the entire FTS index from the base table — cheap for a
    # single-user database with thousands of rows, but would be slow for
    # millions of rows (use row-level triggers there instead).
    #
    # WHY 'rebuild' instead of a per-row insert?
    #   Simpler code, zero risk of index drift, acceptable for our scale.

    def save(self, matter_id: str, summary: str, state_json: str = "{}") -> None:
        """Upsert a session and rebuild the FTS index."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?)",
                (matter_id, summary, state_json, datetime.now().isoformat()),
            )
            # Rebuild FTS index so the new/updated summary is searchable
            conn.execute("INSERT INTO sessions_fts(sessions_fts) VALUES('rebuild')")

    def search(self, query: str) -> list[dict]:
        """Full-text search across summaries. Returns list of dicts."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                # WHY subquery: FTS5 gives us rowids; we join back to get
                # the human-readable matter_id and summary columns.
                "SELECT matter_id, summary FROM sessions WHERE rowid IN "
                "(SELECT rowid FROM sessions_fts WHERE sessions_fts MATCH ?)",
                (query,),
            ).fetchall()
        return [{"matter_id": r[0], "summary": r[1]} for r in rows]

    def list_recent(self, limit: int = 10) -> list[tuple]:
        """Return the N most-recent sessions as (matter_id, summary, created_at)."""
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                "SELECT matter_id, summary, created_at FROM sessions "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()


# ── SECTION 4: LIVE DEMO ──────────────────────────────────────────────────

def run_demo() -> None:
    db_path = Path("/tmp/lexagent_session_demo.db")
    if db_path.exists():
        db_path.unlink()           # clean slate for each demo run

    store = SessionStore(db_path)

    # Save three realistic LexAgent sessions
    store.save(
        "sharma-v-state-2024",
        "Writ of Mandamus: speedy trial petition for Sharma detained 18 months",
        json.dumps({"matter_type": "writ", "jurisdiction": "Delhi HC"}),
    )
    store.save(
        "infosys-rent-dispute-2024",
        "Commercial lease dispute between Infosys and landlord over force majeure clause",
        json.dumps({"matter_type": "commercial", "jurisdiction": "NCLT"}),
    )
    store.save(
        "meera-bail-2025",
        "Anticipatory bail application for Meera under IPC 420 — cheating allegation",
        json.dumps({"matter_type": "criminal", "jurisdiction": "Sessions Court"}),
    )

    print("=== Search for 'writ' ===")
    for result in store.search("writ"):
        print(f"  [{result['matter_id']}] {result['summary']}")

    print("\n=== Search for 'bail' ===")
    for result in store.search("bail"):
        print(f"  [{result['matter_id']}] {result['summary']}")

    print("\n=== List recent (limit=2) ===")
    for matter_id, summary, created_at in store.list_recent(limit=2):
        print(f"  {matter_id} | {created_at[:19]} | {summary[:50]}...")

    print(f"\nDatabase written to: {db_path}")


# ── SECTION 5: HOW THIS CONNECTS TO LEXAGENT CLI ──────────────────────────

# In lexagent/cli.py, after `graph.astream(initial_state)` finishes:
#
#   session_store = SessionStore(config.sessions_db_path)
#   session_store.save(
#       matter_id=final_state["matter_id"],
#       summary=final_state["user_input"][:200],
#       state_json=json.dumps({
#           "matter_type": final_state.get("matter_type"),
#           "jurisdiction": final_state.get("jurisdiction"),
#       }),
#   )
#
# The CLI also uses `store.list_recent()` to show the lawyer a "recent
# matters" panel on startup, and `store.search(query)` for the
# `lex search "<query>"` subcommand.
#
# Real file to read: lexagent/memory/session_store.py
# Real caller:       lexagent/cli.py


if __name__ == "__main__":
    run_demo()


# ── PAUSE AND THINK ───────────────────────────────────────────────────────
#
# 1. Why does FTS5 use a subquery (SELECT rowid FROM sessions_fts WHERE ...)
#    instead of a JOIN directly on the virtual table?
#
# 2. What happens if you INSERT a new session but forget the 'rebuild' step?
#    How would you detect that the index is stale?
#
# 3. `INSERT OR REPLACE` deletes the old row and inserts a new one.
#    How does this affect the FTS index if you don't rebuild after?
#
# 4. The demo calls db_path.unlink() at the start — why is this important
#    when running an educational demo that uses CREATE TABLE IF NOT EXISTS?
#
# 5. Look at lexagent/cli.py — where exactly does the CLI call session_store
#    .save(), and what data does it pass as state_json?
