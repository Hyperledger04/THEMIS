# WHY: SQLite with FTS5 gives full-text search over all past sessions.
# A lawyer can ask "show me all matters about property disputes in Delhi"
# and the session store can find them instantly without loading every MEMORY.md.
#
# LANGGRAPH: This is outside the graph — it's called from cli.py after the graph
# completes. The graph itself stays stateless; persistence is the CLI's job.
# This matches how LangGraph's own checkpointer pattern works: graph runs,
# then state is persisted externally.
#
# SQLite is used (not Postgres) because it's a single file, zero-config,
# works offline, and ships with Python's standard library. Perfect for a
# lawyer's laptop that may not have Docker installed.

import functools
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

from themis.state import SeniorCounselState

_logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _session_cfg():
    """Cached LexConfig — encryption settings are deployment-time, not per-request."""
    from themis.config import LexConfig
    return LexConfig()

SCHEMA_VERSION = 2


def _encrypt_state(raw_json: str, firm_id: str = "default") -> str:
    """
    Encrypt state_json string if encryption is enabled. Returns hex ciphertext.
    In personal mode (no encryption_key), returns the JSON string unchanged.

    WHY: state_json contains matter facts and party names. At-rest encryption
    ensures a stolen database file cannot be read without the master key.
    """
    try:
        from themis.security.crypto import is_encryption_enabled, encrypt_str
        cfg = _session_cfg()
        if is_encryption_enabled(cfg) and cfg.encryption_key:
            return encrypt_str(raw_json, cfg.encryption_key, firm_id)
    except Exception as e:
        _logger.warning("state_json encryption failed, storing plaintext: %s", e)
    return raw_json


def _decrypt_state(stored: str, firm_id: str = "default") -> str:
    """
    Decrypt state_json if encrypted (has LEXENC: sentinel). Returns JSON string.
    Plaintext strings are returned unchanged (personal mode / pre-encryption rows).
    """
    try:
        from themis.security.crypto import decrypt_str
        cfg = _session_cfg()
        if cfg.encryption_key:
            return decrypt_str(stored, cfg.encryption_key, firm_id)
    except Exception as e:
        _logger.warning("state_json decryption failed, returning raw value: %s", e)
    return stored


def db_path(sessions_db: str = "~/.themis/sessions.db") -> Path:
    """Return the absolute Path to the sessions database."""
    return Path(sessions_db).expanduser()


@contextmanager
def _connect(sessions_db: str = "~/.themis/sessions.db") -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager that opens the SQLite connection and ensures it is closed.
    WHY: contextmanager keeps connection handling out of every call site.
    """
    path = db_path(sessions_db)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    # WHY: WAL mode allows concurrent readers alongside one writer — required for
    # multiple Telegram users hitting the same SQLite file simultaneously.
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(sessions_db: str = "~/.themis/sessions.db") -> None:
    """
    Create the sessions database and tables if they do not already exist.
    Called once on first run (from `lex setup` or lazily before first save).

    FTS5 table: enables full-text search over matter_type, parties, jurisdiction,
    purpose, and the draft summary without loading entire MEMORY.md files.
    """
    with _connect(sessions_db) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id   TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                matter_type TEXT,
                parties     TEXT,
                jurisdiction TEXT,
                purpose     TEXT,
                summary     TEXT,
                state_json  TEXT,
                firm_id     TEXT NOT NULL DEFAULT 'default',
                user_id     TEXT NOT NULL DEFAULT 'default'
            );

            -- Phase 8: Hearing reminders — fire N days before hearing_date.
            -- WHY separate table: reminder lifecycle (add/delete/fired) is orthogonal
            -- to session state; mixing them into state_json would make queries painful.
            CREATE TABLE IF NOT EXISTS reminders (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id    TEXT NOT NULL,
                telegram_user_id TEXT,
                hearing_date TEXT NOT NULL,
                note         TEXT,
                days_before  INTEGER NOT NULL DEFAULT 1,
                fire_at      TEXT NOT NULL,
                fired        INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL,
                firm_id      TEXT NOT NULL DEFAULT 'default',
                user_id      TEXT NOT NULL DEFAULT 'default'
            );

            -- FTS5 virtual table that indexes the text columns for full-text search.
            -- LANGGRAPH concept: FTS5 here is analogous to a vector store but for
            -- exact keyword matching. Phase 5 will add a proper embedding-based
            -- retrieval store on top of this foundation.
            CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts
            USING fts5(
                matter_id,
                matter_type,
                parties,
                jurisdiction,
                purpose,
                summary,
                content='sessions',
                content_rowid='id'
            );

            -- Triggers keep the FTS index in sync with the main table.
            CREATE TRIGGER IF NOT EXISTS sessions_ai
            AFTER INSERT ON sessions BEGIN
                INSERT INTO sessions_fts(rowid, matter_id, matter_type, parties, jurisdiction, purpose, summary)
                VALUES (new.id, new.matter_id, new.matter_type, new.parties, new.jurisdiction, new.purpose, new.summary);
            END;

            CREATE TRIGGER IF NOT EXISTS sessions_ad
            AFTER DELETE ON sessions BEGIN
                INSERT INTO sessions_fts(sessions_fts, rowid, matter_id, matter_type, parties, jurisdiction, purpose, summary)
                VALUES ('delete', old.id, old.matter_id, old.matter_type, old.parties, old.jurisdiction, old.purpose, old.summary);
            END;

            CREATE TRIGGER IF NOT EXISTS sessions_au
            AFTER UPDATE ON sessions BEGIN
                INSERT INTO sessions_fts(sessions_fts, rowid, matter_id, matter_type, parties, jurisdiction, purpose, summary)
                VALUES ('delete', old.id, old.matter_id, old.matter_type, old.parties, old.jurisdiction, old.purpose, old.summary);
                INSERT INTO sessions_fts(rowid, matter_id, matter_type, parties, jurisdiction, purpose, summary)
                VALUES (new.id, new.matter_id, new.matter_type, new.parties, new.jurisdiction, new.purpose, new.summary);
            END;

            -- T1-B: persistent chat history across CLI invocations.
            -- WHY: LiteLLM chat_model starts fresh each run (messages=[]).
            -- Storing turns here lets run_chat() resume where it left off.
            CREATE TABLE IF NOT EXISTS chat_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                firm_id     TEXT NOT NULL DEFAULT 'default',
                user_id     TEXT NOT NULL DEFAULT 'default'
            );

            CREATE INDEX IF NOT EXISTS idx_chat_messages_session
            ON chat_messages(session_id, created_at);

            CREATE TABLE IF NOT EXISTS schema_version (version INTEGER);
        """)

        # Migration: add tenant columns if missing (upgrade from schema v1).
        # WHY: ALTER TABLE ... ADD COLUMN IF NOT EXISTS is not supported in all
        # SQLite versions, so we use PRAGMA table_info to check first.
        for table in ("sessions", "reminders", "chat_messages"):
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "firm_id" not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN firm_id TEXT NOT NULL DEFAULT 'default'")
            if "user_id" not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")

        # Indexes on firm_id for fast per-tenant queries.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_firm ON sessions(firm_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_firm ON reminders(firm_id)")

        # Record schema version (for future migrations)
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if not row:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        elif row[0] < SCHEMA_VERSION:
            conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))


def save_session(
    state: SeniorCounselState,
    sessions_db: str = "~/.themis/sessions.db",
    firm_id: str = "default",
    user_id: str = "default",
) -> int:
    """
    Save a completed session to the database.
    Returns the new row ID.
    Called by cli.py after the graph finishes.

    firm_id/user_id default to 'default' so personal-mode callers (CLI, Telegram)
    that don't pass these params continue to work with zero changes.
    WHY: state may also carry firm_id/user_id injected by the control plane —
    prefer those values if present so the row lands in the right tenant partition.
    """
    init_db(sessions_db)

    # Prefer tenant values already embedded in state (set by the control plane);
    # fall back to the explicit params; fall back to 'default'.
    resolved_firm = state.get("firm_id") or firm_id
    resolved_user = state.get("user_id") or user_id

    parties = state.get("parties") or {}
    if isinstance(parties, dict):
        parties_str = "; ".join(f"{k}: {v}" for k, v in parties.items() if v)
    else:
        parties_str = str(parties)

    # Serialise the state (excluding un-serialisable message objects)
    state_snapshot = {
        k: v for k, v in state.items()
        if k != "messages" and isinstance(v, (str, dict, list, bool, int, float, type(None)))
    }

    with _connect(sessions_db) as conn:
        cursor = conn.execute(
            """
            INSERT INTO sessions
                (matter_id, created_at, matter_type, parties, jurisdiction, purpose, summary, state_json, firm_id, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.get("matter_id") or "",
                datetime.now().isoformat(),
                state.get("matter_type") or "",
                parties_str,
                state.get("jurisdiction") or "",
                state.get("purpose") or "",
                state.get("plain_english_summary") or "",
                _encrypt_state(json.dumps(state_snapshot, ensure_ascii=False), resolved_firm),
                resolved_firm,
                resolved_user,
            ),
        )
        return cursor.lastrowid


def search_sessions(
    query: str,
    limit: int = 10,
    sessions_db: str = "~/.themis/sessions.db",
    firm_id: str = "default",
) -> List[dict]:
    """
    Full-text search over sessions scoped to the given firm.
    Returns a list of session dicts sorted by relevance.

    Example: search_sessions("property dispute Delhi", firm_id="firm_a")
    """
    init_db(sessions_db)

    with _connect(sessions_db) as conn:
        rows = conn.execute(
            """
            SELECT s.matter_id, s.created_at, s.matter_type, s.parties,
                   s.jurisdiction, s.purpose, s.summary
            FROM sessions s
            JOIN sessions_fts fts ON s.id = fts.rowid
            WHERE sessions_fts MATCH ?
              AND s.firm_id = ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, firm_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def list_sessions(
    limit: int = 20,
    sessions_db: str = "~/.themis/sessions.db",
    firm_id: str = "default",
) -> List[dict]:
    """List the most recent sessions for the given firm, newest first."""
    init_db(sessions_db)

    with _connect(sessions_db) as conn:
        rows = conn.execute(
            """
            SELECT matter_id, created_at, matter_type, parties, jurisdiction, purpose, summary
            FROM sessions
            WHERE firm_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (firm_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def get_session_state(
    matter_id: str,
    sessions_db: str = "~/.themis/sessions.db",
    firm_id: str = "default",
) -> Optional[dict]:
    """
    Load the most recent state snapshot for a matter_id, scoped to the given firm.
    Used when `lex draft --matter-id M001` continues a prior matter.
    Returns None if no sessions exist for this matter within the firm's tenant partition.
    """
    init_db(sessions_db)

    with _connect(sessions_db) as conn:
        row = conn.execute(
            """
            SELECT state_json FROM sessions
            WHERE matter_id = ? AND firm_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (matter_id, firm_id),
        ).fetchone()

        if not row or not row["state_json"]:
            return None
        raw = _decrypt_state(row["state_json"], firm_id)
        return json.loads(raw)


def update_session(
    state: SeniorCounselState,
    sessions_db: str = "~/.themis/sessions.db",
    firm_id: str = "default",
    user_id: str = "default",
) -> None:
    """
    Upsert a partial session snapshot — called after every intake turn, not just on completion.
    WHY: Telegram sessions need to survive bot restarts. Saving on every turn (not just
    on completion) ensures in-progress matters can be resumed even if the bot crashes.

    If a row for this matter_id+firm_id already exists, replaces it. Otherwise inserts.
    The firm_id scope ensures upsert logic cannot collide across tenants.
    """
    init_db(sessions_db)

    resolved_firm = state.get("firm_id") or firm_id
    resolved_user = state.get("user_id") or user_id

    parties = state.get("parties") or {}
    if isinstance(parties, dict):
        parties_str = "; ".join(f"{k}: {v}" for k, v in parties.items() if v)
    else:
        parties_str = str(parties)

    state_snapshot = {
        k: v for k, v in state.items()
        if k != "messages" and isinstance(v, (str, dict, list, bool, int, float, type(None)))
    }

    with _connect(sessions_db) as conn:
        existing = conn.execute(
            "SELECT id FROM sessions WHERE matter_id = ? AND firm_id = ? ORDER BY created_at DESC LIMIT 1",
            (state.get("matter_id") or "", resolved_firm),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE sessions
                SET matter_type=?, parties=?, jurisdiction=?, purpose=?, summary=?, state_json=?, user_id=?
                WHERE id=?
                """,
                (
                    state.get("matter_type") or "",
                    parties_str,
                    state.get("jurisdiction") or "",
                    state.get("purpose") or "",
                    state.get("plain_english_summary") or "",
                    _encrypt_state(json.dumps(state_snapshot, ensure_ascii=False), resolved_firm),
                    resolved_user,
                    existing["id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO sessions
                    (matter_id, created_at, matter_type, parties, jurisdiction, purpose, summary, state_json, firm_id, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.get("matter_id") or "",
                    datetime.now().isoformat(),
                    state.get("matter_type") or "",
                    parties_str,
                    state.get("jurisdiction") or "",
                    state.get("purpose") or "",
                    state.get("plain_english_summary") or "",
                    _encrypt_state(json.dumps(state_snapshot, ensure_ascii=False), resolved_firm),
                    resolved_firm,
                    resolved_user,
                ),
            )


# ---------------------------------------------------------------------------
# Phase 8: Hearing reminder CRUD
# ---------------------------------------------------------------------------


def add_reminder(
    matter_id: str,
    hearing_date: str,
    note: str = "",
    days_before: int = 1,
    telegram_user_id: Optional[str] = None,
    sessions_db: str = "~/.themis/sessions.db",
) -> int:
    """
    Store a hearing reminder that will fire `days_before` days before `hearing_date`.
    Returns the new reminder row ID.

    fire_at is computed as: hearing_date − days_before days (at 09:00).
    """
    from datetime import date as _date, timedelta

    init_db(sessions_db)

    try:
        hearing_dt = datetime.fromisoformat(hearing_date).date()
    except ValueError:
        # If the date doesn't parse as ISO, store it verbatim and set fire_at = now
        # so the reminder surfaces immediately on next check.
        hearing_dt = None

    if hearing_dt:
        fire_dt = hearing_dt - timedelta(days=days_before)
        fire_at = datetime.combine(fire_dt, datetime.min.time().replace(hour=9)).isoformat()
    else:
        fire_at = datetime.now().isoformat()

    with _connect(sessions_db) as conn:
        cursor = conn.execute(
            """
            INSERT INTO reminders
                (matter_id, telegram_user_id, hearing_date, note, days_before, fire_at, fired, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (matter_id, telegram_user_id, hearing_date, note, days_before, fire_at, datetime.now().isoformat()),
        )
        return cursor.lastrowid


def list_reminders(
    matter_id: Optional[str] = None,
    include_fired: bool = False,
    sessions_db: str = "~/.themis/sessions.db",
    telegram_user_id: Optional[str] = None,
) -> List[dict]:
    """
    List reminders, optionally filtered by matter_id, fired status, and Telegram user.

    WHY telegram_user_id filter: in multi-user Telegram deployments a single SQLite
    file is shared across users. Without scoping, user A's reminder queries would
    return user B's rows. V3.4 interim fix — domain events replace this in V3.5.
    """
    init_db(sessions_db)

    with _connect(sessions_db) as conn:
        clauses: list[str] = []
        params: list = []

        if matter_id:
            clauses.append("matter_id = ?")
            params.append(matter_id)
        if telegram_user_id is not None:
            clauses.append("telegram_user_id = ?")
            params.append(telegram_user_id)
        if not include_fired:
            clauses.append("fired = 0")

        query = "SELECT * FROM reminders"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY fire_at ASC"

        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def delete_reminder(
    reminder_id: int,
    sessions_db: str = "~/.themis/sessions.db",
    telegram_user_id: Optional[str] = None,
) -> bool:
    """
    Delete a reminder by ID. Returns True if a row was deleted.

    WHY telegram_user_id: scoping the DELETE prevents one Telegram user from
    deleting another user's reminder by guessing a reminder_id integer.
    When None (CLI / non-Telegram callers), no user scope is applied.
    """
    init_db(sessions_db)

    with _connect(sessions_db) as conn:
        if telegram_user_id is not None:
            cursor = conn.execute(
                "DELETE FROM reminders WHERE id = ? AND telegram_user_id = ?",
                (reminder_id, telegram_user_id),
            )
        else:
            cursor = conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# T1-B + T1-C: Chat history persistence
# ---------------------------------------------------------------------------


def get_today_session_id() -> str:
    """Session ID for today's chat — one window per calendar day."""
    return datetime.now().strftime("%Y-%m-%d")


def save_chat_message(
    session_id: str,
    role: str,
    content: str,
    sessions_db: str = "~/.themis/sessions.db",
    firm_id: str = "default",
) -> None:
    """Persist a single chat turn (user or assistant) to SQLite."""
    init_db(sessions_db)
    with _connect(sessions_db) as conn:
        conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, created_at, firm_id) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, datetime.now().isoformat(), firm_id),
        )


def load_chat_history(
    session_id: str,
    limit: int = 20,
    sessions_db: str = "~/.themis/sessions.db",
    firm_id: str = "default",
) -> List[dict]:
    """
    Load the last `limit` messages for a session, oldest-first.
    Returns list of {role, content} dicts ready to pass to LiteLLM.
    """
    init_db(sessions_db)
    with _connect(sessions_db) as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM (
                SELECT role, content, created_at FROM chat_messages
                WHERE session_id = ? AND firm_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ) ORDER BY created_at ASC
            """,
            (session_id, firm_id, limit),
        ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]


def get_due_reminders(
    sessions_db: str = "~/.themis/sessions.db",
    telegram_user_id: Optional[str] = None,
) -> List[dict]:
    """
    Return all unfired reminders whose fire_at time has passed.

    WHY telegram_user_id: the scheduler calls this without a user filter (it
    sees all due reminders and routes each to the correct user via the
    telegram_user_id field in the row). Pass a user ID to scope to one user,
    e.g. when a user polls for their own due reminders via the gateway.
    """
    init_db(sessions_db)

    now = datetime.now().isoformat()
    with _connect(sessions_db) as conn:
        if telegram_user_id is not None:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE fired = 0 AND fire_at <= ? AND telegram_user_id = ? ORDER BY fire_at ASC",
                (now, telegram_user_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE fired = 0 AND fire_at <= ? ORDER BY fire_at ASC",
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]


def mark_reminder_fired(reminder_id: int, sessions_db: str = "~/.themis/sessions.db") -> None:
    """Mark a reminder as fired so it doesn't fire again."""
    init_db(sessions_db)

    with _connect(sessions_db) as conn:
        conn.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,))
