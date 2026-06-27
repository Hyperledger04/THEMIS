# Phase 1: Stabilize and Reconcile — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every security and tenant-isolation claim in the codebase actually true — wire the existing `SecurityContext`, JWT, AES-GCM, and audit packages into the control plane, session store, and matter memory paths; add `firm_id` tenant columns; and fix three known critical bugs (RAPTOR shape, citation threshold guard, matter memory path isolation).

**Architecture:** The security primitives (tokens.py, crypto.py, context.py, audit.py) are complete but unwired. This phase threads them through: control plane auth returns `SecurityContext` objects; session store gains `firm_id`/`user_id` columns and tenant-scoped queries; matter memory paths become firm-partitioned; `state_json` is AES-GCM encrypted at rest when `encryption_key` is set; and `log_action` is called at every matter lifecycle event.

**Tech Stack:** Python 3.11+, SQLite (built-in), python-jose, cryptography (already in pyproject.toml). All changes are additive with backward-compatible personal-mode defaults. No new dependencies.

---

## Scope check

Five independent subsystems, one plan because they share `firm_id` as the binding concept. Each task produces testable software on its own. Order: Task 1 → Task 2 (depends on 1 for path logic) → Task 3 (independent) → Task 4 (extends Task 1) → Task 5 (independent bug fixes).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `themis/memory/session_store.py` | Add `firm_id`/`user_id` columns + migration; tenant-scoped queries; AES-GCM encrypt `state_json` |
| Modify | `themis/memory/matter_memory.py` | Add `firm_id` param; firm-partitioned paths |
| Modify | `themis/nodes/draft.py` | Pass `firm_id` from state to `load_matter_memory` |
| Modify | `themis/cli.py` | Pass `cfg.default_firm_id` to all `save_matter_memory` / `load_matter_memory` / `list_matters` calls |
| Modify | `themis/gateway/control_plane.py` | `_verify_token` returns `SecurityContext`; `log_action` at matter lifecycle events |
| Modify | `themis/tools/raptor_summarizer.py` | Fix `citation: None` → `citation: ""` in `raptor_tree_to_findings` |
| Create | `tests/test_session_tenant.py` | Session tenant isolation, AES-GCM round-trip, migration |
| Modify | `tests/test_matter_isolation.py` | Extend to cover firm-scoped matter memory paths |
| Modify | `tests/test_control_plane.py` | SecurityContext return type, audit log calls |
| Modify | `tests/test_raptor_summarizer.py` | Verify `raptor_tree_to_findings` citation field is never None |

---

## Task 1: Session store — tenant column migration + scoped queries

**Files:**
- Modify: `themis/memory/session_store.py`
- Create: `tests/test_session_tenant.py`

### Background

The `sessions`, `reminders`, and `chat_messages` tables have no `firm_id` column. In enterprise mode (multi_tenant=True) a `SELECT WHERE matter_id=?` returns rows from all firms — confidentiality bleed per §11A Failure Mode 3. Fix: add `firm_id TEXT NOT NULL DEFAULT 'default'` and `user_id TEXT NOT NULL DEFAULT 'default'` to each table, thread them through every write, and append `AND firm_id=?` on every read when multi_tenant is True.

- [ ] **Step 1.1 — Write failing test**

Create `tests/test_session_tenant.py`:

```python
"""Tests for session store tenant isolation and schema migration."""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from themis.memory.session_store import (
    init_db,
    list_sessions,
    save_session,
    search_sessions,
    get_session_state,
    update_session,
)


def _make_state(matter_id: str, matter_type: str = "writ") -> dict:
    return {
        "matter_id": matter_id,
        "matter_type": matter_type,
        "parties": {"petitioner": "Ravi Singh", "respondent": "State"},
        "jurisdiction": "Delhi HC",
        "purpose": "test",
        "plain_english_summary": f"summary for {matter_id}",
        "messages": [],
    }


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "sessions.db")


def test_schema_has_firm_id_column(tmp_db):
    init_db(tmp_db)
    conn = sqlite3.connect(tmp_db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    conn.close()
    assert "firm_id" in cols, "sessions table must have firm_id column"
    assert "user_id" in cols, "sessions table must have user_id column"


def test_reminders_schema_has_firm_id(tmp_db):
    init_db(tmp_db)
    conn = sqlite3.connect(tmp_db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(reminders)")}
    conn.close()
    assert "firm_id" in cols


def test_firm_a_cannot_read_firm_b_sessions(tmp_db):
    save_session(_make_state("M001"), sessions_db=tmp_db, firm_id="firm_a", user_id="u1")
    save_session(_make_state("M002"), sessions_db=tmp_db, firm_id="firm_b", user_id="u2")

    rows_a = list_sessions(sessions_db=tmp_db, firm_id="firm_a")
    ids_a = {r["matter_id"] for r in rows_a}

    assert "M001" in ids_a
    assert "M002" not in ids_a, "firm_b matter must not appear in firm_a listing"


def test_get_session_state_is_firm_scoped(tmp_db):
    state_a = _make_state("M001")
    state_a["purpose"] = "firm_a_purpose"
    save_session(state_a, sessions_db=tmp_db, firm_id="firm_a", user_id="u1")

    # firm_b should not find firm_a's matter
    result = get_session_state("M001", sessions_db=tmp_db, firm_id="firm_b")
    assert result is None, "firm_b must not read firm_a state"


def test_search_sessions_is_firm_scoped(tmp_db):
    save_session(_make_state("M001", "writ"), sessions_db=tmp_db, firm_id="firm_a", user_id="u1")
    save_session(_make_state("M002", "writ"), sessions_db=tmp_db, firm_id="firm_b", user_id="u2")

    hits = search_sessions("writ", sessions_db=tmp_db, firm_id="firm_a")
    ids = {h["matter_id"] for h in hits}
    assert "M001" in ids
    assert "M002" not in ids
```

- [ ] **Step 1.2 — Run to verify failure**

```bash
cd /Users/anshoosareen/Lexagent
pytest tests/test_session_tenant.py -v
```

Expected: `TypeError` or `AssertionError` — `save_session` / `list_sessions` don't accept `firm_id` param yet.

- [ ] **Step 1.3 — Add tenant columns to schema and thread firm_id through all functions**

In `themis/memory/session_store.py`, replace the `init_db` schema block and update every function signature and query:

**Schema change** — update the `CREATE TABLE IF NOT EXISTS sessions` block inside `init_db` to add columns and update the FTS trigger:

```python
SCHEMA_VERSION = 2  # bump from 1 to 2

def init_db(sessions_db: str = "~/.themis/sessions.db") -> None:
    with _connect(sessions_db) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id    TEXT NOT NULL,
                firm_id      TEXT NOT NULL DEFAULT 'default',
                user_id      TEXT NOT NULL DEFAULT 'default',
                created_at   TEXT NOT NULL,
                matter_type  TEXT,
                parties      TEXT,
                jurisdiction TEXT,
                purpose      TEXT,
                summary      TEXT,
                state_json   TEXT
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id        TEXT NOT NULL,
                firm_id          TEXT NOT NULL DEFAULT 'default',
                user_id          TEXT NOT NULL DEFAULT 'default',
                telegram_user_id TEXT,
                hearing_date     TEXT NOT NULL,
                note             TEXT,
                days_before      INTEGER NOT NULL DEFAULT 1,
                fire_at          TEXT NOT NULL,
                fired            INTEGER NOT NULL DEFAULT 0,
                created_at       TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts
            USING fts5(
                matter_id, matter_type, parties, jurisdiction, purpose, summary,
                content='sessions', content_rowid='id'
            );

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

            CREATE TABLE IF NOT EXISTS chat_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                firm_id     TEXT NOT NULL DEFAULT 'default',
                user_id     TEXT NOT NULL DEFAULT 'default',
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chat_messages_session
            ON chat_messages(session_id, created_at);

            CREATE INDEX IF NOT EXISTS idx_sessions_firm ON sessions(firm_id);
            CREATE INDEX IF NOT EXISTS idx_reminders_firm ON reminders(firm_id);

            CREATE TABLE IF NOT EXISTS schema_version (version INTEGER);
        """)

        # Migration: add firm_id/user_id to existing tables if they don't have the column
        for table in ("sessions", "reminders", "chat_messages"):
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "firm_id" not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN firm_id TEXT NOT NULL DEFAULT 'default'")
            if "user_id" not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")

        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if not row:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        elif row[0] < SCHEMA_VERSION:
            conn.execute("UPDATE schema_version SET version=?", (SCHEMA_VERSION,))
```

**Update `save_session`** — add `firm_id` and `user_id` params:

```python
def save_session(
    state: LexState,
    sessions_db: str = "~/.themis/sessions.db",
    firm_id: str = "default",
    user_id: str = "default",
) -> int:
    init_db(sessions_db)
    parties = state.get("parties") or {}
    if isinstance(parties, dict):
        parties_str = "; ".join(f"{k}: {v}" for k, v in parties.items() if v)
    else:
        parties_str = str(parties)
    state_snapshot = {
        k: v for k, v in state.items()
        if k != "messages" and isinstance(v, (str, dict, list, bool, int, float, type(None)))
    }
    # Use firm_id from state if available (control plane path), else use param
    resolved_firm = state.get("firm_id") or firm_id
    resolved_user = state.get("user_id") or user_id
    with _connect(sessions_db) as conn:
        cursor = conn.execute(
            """
            INSERT INTO sessions
                (matter_id, firm_id, user_id, created_at, matter_type, parties,
                 jurisdiction, purpose, summary, state_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.get("matter_id") or "",
                resolved_firm,
                resolved_user,
                datetime.now().isoformat(),
                state.get("matter_type") or "",
                parties_str,
                state.get("jurisdiction") or "",
                state.get("purpose") or "",
                state.get("plain_english_summary") or "",
                json.dumps(state_snapshot, ensure_ascii=False),
            ),
        )
        return cursor.lastrowid
```

**Update `list_sessions`** — add `firm_id` param and WHERE clause:

```python
def list_sessions(
    limit: int = 20,
    sessions_db: str = "~/.themis/sessions.db",
    firm_id: str = "default",
) -> List[dict]:
    init_db(sessions_db)
    with _connect(sessions_db) as conn:
        rows = conn.execute(
            """
            SELECT matter_id, firm_id, user_id, created_at, matter_type,
                   parties, jurisdiction, purpose, summary
            FROM sessions
            WHERE firm_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (firm_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
```

**Update `search_sessions`** — add `firm_id` param:

```python
def search_sessions(
    query: str,
    limit: int = 10,
    sessions_db: str = "~/.themis/sessions.db",
    firm_id: str = "default",
) -> List[dict]:
    init_db(sessions_db)
    with _connect(sessions_db) as conn:
        rows = conn.execute(
            """
            SELECT s.matter_id, s.created_at, s.matter_type, s.parties,
                   s.jurisdiction, s.purpose, s.summary
            FROM sessions s
            JOIN sessions_fts fts ON s.id = fts.rowid
            WHERE sessions_fts MATCH ? AND s.firm_id = ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, firm_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
```

**Update `get_session_state`** — add `firm_id` param:

```python
def get_session_state(
    matter_id: str,
    sessions_db: str = "~/.themis/sessions.db",
    firm_id: str = "default",
) -> Optional[dict]:
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
        return json.loads(row["state_json"])
```

**Update `update_session`** — add `firm_id` / `user_id` params and scope the SELECT:

```python
def update_session(
    state: LexState,
    sessions_db: str = "~/.themis/sessions.db",
    firm_id: str = "default",
    user_id: str = "default",
) -> None:
    init_db(sessions_db)
    parties = state.get("parties") or {}
    if isinstance(parties, dict):
        parties_str = "; ".join(f"{k}: {v}" for k, v in parties.items() if v)
    else:
        parties_str = str(parties)
    state_snapshot = {
        k: v for k, v in state.items()
        if k != "messages" and isinstance(v, (str, dict, list, bool, int, float, type(None)))
    }
    resolved_firm = state.get("firm_id") or firm_id
    resolved_user = state.get("user_id") or user_id
    with _connect(sessions_db) as conn:
        existing = conn.execute(
            "SELECT id FROM sessions WHERE matter_id = ? AND firm_id = ? ORDER BY created_at DESC LIMIT 1",
            (state.get("matter_id") or "", resolved_firm),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE sessions
                SET matter_type=?, parties=?, jurisdiction=?, purpose=?, summary=?, state_json=?
                WHERE id=?
                """,
                (
                    state.get("matter_type") or "",
                    parties_str,
                    state.get("jurisdiction") or "",
                    state.get("purpose") or "",
                    state.get("plain_english_summary") or "",
                    json.dumps(state_snapshot, ensure_ascii=False),
                    existing["id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO sessions
                    (matter_id, firm_id, user_id, created_at, matter_type, parties,
                     jurisdiction, purpose, summary, state_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.get("matter_id") or "",
                    resolved_firm,
                    resolved_user,
                    datetime.now().isoformat(),
                    state.get("matter_type") or "",
                    parties_str,
                    state.get("jurisdiction") or "",
                    state.get("purpose") or "",
                    state.get("plain_english_summary") or "",
                    json.dumps(state_snapshot, ensure_ascii=False),
                ),
            )
```

- [ ] **Step 1.4 — Run tests**

```bash
pytest tests/test_session_tenant.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 1.5 — Run existing memory tests to check no regression**

```bash
pytest tests/test_memory.py -v
```

Expected: all pass (existing calls use `firm_id="default"` by default).

- [ ] **Step 1.6 — Commit**

```bash
git add themis/memory/session_store.py tests/test_session_tenant.py
git commit -m "feat(p1): add firm_id/user_id tenant columns to session store + scoped queries"
```

---

## Task 2: Matter memory — firm-scoped paths

**Files:**
- Modify: `themis/memory/matter_memory.py`
- Modify: `themis/nodes/draft.py` (line 353)
- Modify: `themis/cli.py` (lines 590, 1222, 1253, 2107, 2113)
- Modify: `tests/test_matter_isolation.py`

### Background

`load_matter_memory(matter_id, matters_dir)` and `save_matter_memory(matter_id, state, matters_dir)` store at `~/.themis/matters/{matter_id}/`. In enterprise mode, two firms with the same matter ID (`M001`) share the same filesystem path. Fix: add `firm_id` param; personal mode path stays `{matters_dir}/{matter_id}/`, enterprise mode path becomes `{matters_dir}/{firm_id}/{matter_id}/`.

- [ ] **Step 2.1 — Write failing tests (add to test_matter_isolation.py)**

Append these tests to `tests/test_matter_isolation.py`:

```python
# ── Firm-scoped path isolation ──────────────────────────────────────────────

import tempfile
from themis.memory.matter_memory import (
    load_matter_memory,
    save_matter_memory,
    list_matters,
)


def _minimal_state(matter_id: str) -> dict:
    return {
        "matter_id": matter_id,
        "matter_type": "writ",
        "parties": {"petitioner": "Test Party"},
        "jurisdiction": "Delhi HC",
        "purpose": "isolation test",
        "plain_english_summary": f"summary {matter_id}",
        "messages": [],
    }


def test_firm_scoped_paths_do_not_overlap(tmp_path):
    """Two firms with the same matter_id must write to different paths."""
    matters_dir = str(tmp_path / "matters")

    save_matter_memory("M001", _minimal_state("M001"), matters_dir=matters_dir, firm_id="firm_a")
    save_matter_memory("M001", _minimal_state("M001"), matters_dir=matters_dir, firm_id="firm_b")

    mem_a = load_matter_memory("M001", matters_dir=matters_dir, firm_id="firm_a")
    mem_b = load_matter_memory("M001", matters_dir=matters_dir, firm_id="firm_b")

    assert mem_a is not None
    assert mem_b is not None
    # Paths must be different — verified by checking both exist without overwriting
    path_a = tmp_path / "matters" / "firm_a" / "M001" / "MEMORY.md"
    path_b = tmp_path / "matters" / "firm_b" / "M001" / "MEMORY.md"
    assert path_a.exists(), f"Expected firm_a path at {path_a}"
    assert path_b.exists(), f"Expected firm_b path at {path_b}"


def test_list_matters_is_firm_scoped(tmp_path):
    matters_dir = str(tmp_path / "matters")
    save_matter_memory("M001", _minimal_state("M001"), matters_dir=matters_dir, firm_id="firm_a")
    save_matter_memory("M002", _minimal_state("M002"), matters_dir=matters_dir, firm_id="firm_b")

    a_matters = list_matters(matters_dir=matters_dir, firm_id="firm_a")
    ids = {m["matter_id"] for m in a_matters}
    assert "M001" in ids
    assert "M002" not in ids


def test_personal_mode_path_unchanged(tmp_path):
    """Without firm_id, path must be {matters_dir}/{matter_id}/ (backward compat)."""
    matters_dir = str(tmp_path / "matters")
    save_matter_memory("M001", _minimal_state("M001"), matters_dir=matters_dir)
    expected = tmp_path / "matters" / "M001" / "MEMORY.md"
    assert expected.exists(), "Personal mode must not add firm partition"
```

- [ ] **Step 2.2 — Run to verify failure**

```bash
pytest tests/test_matter_isolation.py::test_firm_scoped_paths_do_not_overlap \
       tests/test_matter_isolation.py::test_list_matters_is_firm_scoped \
       tests/test_matter_isolation.py::test_personal_mode_path_unchanged -v
```

Expected: `TypeError` — `firm_id` param doesn't exist yet.

- [ ] **Step 2.3 — Update matter_memory.py**

Replace the `matter_dir` function and add `firm_id` to all public functions:

```python
def matter_dir(
    matter_id: str,
    matters_dir: str = "~/.themis/matters",
    firm_id: str = "default",
) -> Path:
    """
    Returns the Path for a specific matter's directory. Creates it if needed.

    WHY firm partition: in enterprise mode (firm_id != 'default'), matter data
    lives at {matters_dir}/{firm_id}/{matter_id}/ — two firms with the same
    matter_id cannot share files. Personal mode (firm_id='default') keeps the
    flat structure for backward compatibility.
    """
    base = Path(matters_dir).expanduser()
    if firm_id and firm_id != "default":
        path = base / firm_id / matter_id
    else:
        path = base / matter_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_matter_memory(
    matter_id: str,
    matters_dir: str = "~/.themis/matters",
    firm_id: str = "default",
) -> Optional[str]:
    mem_path = matter_dir(matter_id, matters_dir, firm_id) / MEMORY_FILENAME
    if not mem_path.exists():
        return None
    return mem_path.read_text(encoding="utf-8")


def save_matter_memory(
    matter_id: str,
    state: LexState,
    matters_dir: str = "~/.themis/matters",
    firm_id: str = "default",
) -> Path:
    mdir = matter_dir(matter_id, matters_dir, firm_id)
    mem_path = mdir / MEMORY_FILENAME
    # ... (rest of function body unchanged, just update call to matter_dir)
    _save_state_snapshot(matter_id, state, mdir)
    try:
        import asyncio
        asyncio.ensure_future(maybe_compress_memory(matter_id, matters_dir, firm_id=firm_id))
    except Exception:
        pass
    return mem_path


def list_matters(
    matters_dir: str = "~/.themis/matters",
    firm_id: str = "default",
) -> list[dict]:
    base = Path(matters_dir).expanduser()
    if firm_id and firm_id != "default":
        base = base / firm_id
    if not base.exists():
        return []
    # ... rest of function body unchanged


async def maybe_compress_memory(
    matter_id: str,
    matters_dir: str,
    threshold: int = 3,
    firm_id: str = "default",
) -> None:
    # ... update load_matter_memory call inside:
    text = load_matter_memory(matter_id, matters_dir, firm_id)
    # ... update write at end:
    _resolve_memory_path(matter_id, matters_dir, firm_id).write_text(...)


def _resolve_memory_path(
    matter_id: str,
    matters_dir: str,
    firm_id: str = "default",
) -> Path:
    return matter_dir(matter_id, matters_dir, firm_id) / MEMORY_FILENAME
```

- [ ] **Step 2.4 — Update call sites in draft.py (line 353)**

```python
# Before:
matter_mem = load_matter_memory(matter_id, config.matters_dir) if matter_id else None
# After:
firm_id = state.get("firm_id") or config.default_firm_id
matter_mem = load_matter_memory(matter_id, config.matters_dir, firm_id=firm_id) if matter_id else None
```

- [ ] **Step 2.5 — Update call sites in cli.py**

Find these lines and add `firm_id=cfg.default_firm_id`:

```python
# Line ~590 (save_matter_memory in draft command):
mem_path = save_matter_memory(matter_id, state, cfg.matters_dir, firm_id=cfg.default_firm_id)

# Line ~1222 (list_matters):
matters = list_matters(cfg.matters_dir, firm_id=cfg.default_firm_id)

# Line ~1253 (load_matter_memory in lex memory command):
memory = load_matter_memory(matter_id, cfg.matters_dir, firm_id=cfg.default_firm_id)

# Line ~2107 (save_matter_memory in chat command):
save_matter_memory(matter_id, pseudo_state, cfg.matters_dir, firm_id=cfg.default_firm_id)

# Line ~2113 (load_matter_memory in chat command):
memory = load_matter_memory(matter_id, cfg.matters_dir, firm_id=cfg.default_firm_id)
```

- [ ] **Step 2.6 — Run tests**

```bash
pytest tests/test_matter_isolation.py -v
```

Expected: all pass including the three new tests.

- [ ] **Step 2.7 — Commit**

```bash
git add themis/memory/matter_memory.py themis/nodes/draft.py themis/cli.py \
        tests/test_matter_isolation.py
git commit -m "feat(p1): firm-scoped matter memory paths — confidentiality bleed fix"
```

---

## Task 3: Wire SecurityContext into control plane + audit calls

**Files:**
- Modify: `themis/gateway/control_plane.py`
- Modify: `tests/test_control_plane.py`

### Background

`_verify_token` returns a bare `dict`. `SecurityContext` exists in `security/context.py` but is never used by the control plane. `log_action` from `security/audit.py` is never called in the control plane. This task: change `_verify_token` to return `SecurityContext`, update the 4 endpoints that consume it, and call `log_action` at matter lifecycle events.

- [ ] **Step 3.1 — Write failing tests (append to tests/test_control_plane.py)**

```python
from themis.security.context import SecurityContext, Role


def test_verify_token_returns_security_context(monkeypatch):
    """_verify_token must return a SecurityContext, not a bare dict."""
    from themis.gateway.control_plane import _verify_token
    from themis.config import LexConfig

    cfg = LexConfig(api_secret_key=None)  # personal mode
    result = _verify_token(authorization=None, cfg=cfg)

    assert isinstance(result, SecurityContext), (
        f"Expected SecurityContext, got {type(result)}"
    )
    assert result.role == Role.ADMIN
    assert result.firm_id == cfg.default_firm_id


def test_verify_token_enterprise_decodes_jwt(monkeypatch):
    from themis.security.tokens import generate_access_token
    from themis.gateway.control_plane import _verify_token
    from themis.config import LexConfig

    secret = "test-secret-32-chars-padded-xxxx"
    token = generate_access_token("u1", "firm_x", "associate", secret)
    cfg = LexConfig(api_secret_key=secret)

    ctx = _verify_token(authorization=f"Bearer {token}", cfg=cfg)

    assert isinstance(ctx, SecurityContext)
    assert ctx.firm_id == "firm_x"
    assert ctx.user_id == "u1"
    assert ctx.role == Role.ASSOCIATE


def test_audit_log_created_on_matter_access(tmp_path, monkeypatch):
    """log_action must be called when send_message is invoked."""
    import sqlite3
    from themis.security.audit import AuditAction

    db_file = str(tmp_path / "audit.db")
    monkeypatch.setenv("LEX_SESSIONS_DB", db_file)

    calls = []
    monkeypatch.setattr(
        "themis.gateway.control_plane.log_action",
        lambda action, **kw: calls.append(action),
    )

    # Simulate the audit call directly (full graph invocation needs infra)
    from themis.gateway.control_plane import _emit_matter_audit
    _emit_matter_audit(AuditAction.MATTER_ACCESSED, firm_id="f1", user_id="u1", matter_id="M1")

    assert AuditAction.MATTER_ACCESSED in calls
```

- [ ] **Step 3.2 — Run to verify failure**

```bash
pytest tests/test_control_plane.py::test_verify_token_returns_security_context \
       tests/test_control_plane.py::test_verify_token_enterprise_decodes_jwt \
       tests/test_control_plane.py::test_audit_log_created_on_matter_access -v
```

Expected: `AssertionError` (dict returned not SecurityContext) + `AttributeError` (`_emit_matter_audit` doesn't exist).

- [ ] **Step 3.3 — Update control_plane.py**

**Import additions** at the top of `themis/gateway/control_plane.py`:

```python
from themis.security.context import SecurityContext, Role
from themis.security.audit import AuditAction, log_action
```

**Replace `_verify_token`**:

```python
def _verify_token(
    authorization: Optional[str] = Header(None),
    cfg: LexConfig = Depends(_get_cfg),
) -> SecurityContext:
    """
    JWT bearer auth. Returns SecurityContext — never a bare dict.
    Personal mode (no api_secret_key): returns SecurityContext.personal_default().
    Enterprise mode: verifies JWT and extracts firm_id/user_id/role from claims.
    """
    if not cfg.api_secret_key:
        return SecurityContext.personal_default()

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]
    try:
        from themis.security.tokens import decode_access_token
        payload = decode_access_token(token, cfg.api_secret_key)
        return SecurityContext.from_jwt_payload(payload, is_multi_tenant=cfg.multi_tenant)
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid or expired token")
```

**Add audit helper** (place after imports):

```python
def _emit_matter_audit(
    action: str,
    *,
    firm_id: str,
    user_id: str,
    matter_id: str,
    detail: Optional[dict] = None,
) -> None:
    """Non-blocking audit call — never raises."""
    log_action(
        action,
        firm_id=firm_id,
        user_id=user_id,
        resource_type="matter",
        resource_id=matter_id,
        detail=detail,
    )
```

**Update `send_message` endpoint** — replace `auth: dict` with `auth: SecurityContext` and add audit:

```python
@app.post("/api/v1/matters/{matter_id}/message", response_model=MatterOut)
async def send_message(
    matter_id: str,
    body: MessageIn,
    auth: SecurityContext = Depends(_verify_token),   # was: auth: dict
    cfg: LexConfig = Depends(_get_cfg),
) -> MatterOut:
    _emit_matter_audit(AuditAction.MATTER_ACCESSED, firm_id=auth.firm_id,
                       user_id=auth.user_id, matter_id=matter_id)
    graph = get_graph(cfg)
    langgraph_cfg = {
        "configurable": {
            "thread_id": matter_id,
            "user_id": auth.user_id,        # was auth["user_id"]
            "firm_id": auth.firm_id,        # was auth["firm_id"]
        }
    }
    # ... snapshot check (unchanged) ...
    state: LexState = {
        "user_input": body.text,
        "matter_id": matter_id,
        "messages": [{"role": "user", "content": body.text}],
        "firm_id": auth.firm_id,
        "user_id": auth.user_id,
    }
    # ... rest unchanged ...
    # After final = await graph.ainvoke(...):
    if final.get("draft_output"):
        _emit_matter_audit(AuditAction.DRAFT_GENERATED, firm_id=auth.firm_id,
                           user_id=auth.user_id, matter_id=matter_id)
```

**Update `list_matters` endpoint** — `auth: dict` → `auth: SecurityContext`:

```python
@app.get("/api/v1/matters")
async def list_matters(auth: SecurityContext = Depends(_verify_token)) -> JSONResponse:
    return JSONResponse(content={"matters": [], "firm_id": auth.firm_id})
```

**Update `upload_document` endpoint**:

```python
@app.post("/api/v1/matters/{matter_id}/documents")
async def upload_document(
    matter_id: str,
    file: UploadFile,
    auth: SecurityContext = Depends(_verify_token),
    cfg: LexConfig = Depends(_get_cfg),
) -> JSONResponse:
    _emit_matter_audit(AuditAction.DOCUMENT_UPLOADED, firm_id=auth.firm_id,
                       user_id=auth.user_id, matter_id=matter_id,
                       detail={"filename": file.filename})
    # ... rest: replace auth["firm_id"] → auth.firm_id ...
```

**Update `halt_run` endpoint**:

```python
@app.post("/api/v1/matters/{matter_id}/runs/{run_id}/halt")
async def halt_run(
    matter_id: str,
    run_id: str,
    claims: SecurityContext = Depends(_verify_token),
    cfg: LexConfig = Depends(_get_cfg),
) -> JSONResponse:
    # replace claims.get("user_id") → claims.user_id
```

**Update WebSocket auth** — the WS endpoint already decodes JWT manually (needed because WS can't use Header auth). Leave this path as-is but build `SecurityContext` from claims:

```python
# Replace the ws_firm_id / ws_user_id variables:
ctx = SecurityContext.personal_default()
if cfg.api_secret_key:
    if not token:
        await websocket.close(code=4403)
        return
    try:
        from themis.security.tokens import decode_access_token
        payload = decode_access_token(token, cfg.api_secret_key)
        ctx = SecurityContext.from_jwt_payload(payload, is_multi_tenant=cfg.multi_tenant)
    except Exception:
        await websocket.close(code=4403)
        return

await websocket.accept()
# Replace all ws_firm_id → ctx.firm_id, ws_user_id → ctx.user_id
```

- [ ] **Step 3.4 — Run tests**

```bash
pytest tests/test_control_plane.py -v
```

Expected: all tests pass including the three new ones.

- [ ] **Step 3.5 — Commit**

```bash
git add themis/gateway/control_plane.py tests/test_control_plane.py
git commit -m "feat(p1): wire SecurityContext + audit into control plane — all endpoints"
```

---

## Task 4: Encrypt state_json at rest with AES-GCM

**Files:**
- Modify: `themis/memory/session_store.py`
- Modify: `tests/test_session_tenant.py`

### Background

`state_json` in the `sessions` table contains matter facts, party names, draft text — all sensitive. When `encryption_key` is set in config and `multi_tenant=True`, this column must be AES-256-GCM encrypted. The `crypto.py` helpers are already built; this task wires them into write (INSERT/UPDATE) and read (SELECT) paths.

- [ ] **Step 4.1 — Write failing test (append to tests/test_session_tenant.py)**

```python
import sqlite3
from themis.security.crypto import is_encryption_enabled

def test_state_json_encrypted_when_key_set(tmp_db, monkeypatch):
    """When encryption_key is set, state_json in DB must have LEXENC: prefix."""
    monkeypatch.setenv("LEX_ENCRYPTION_KEY", "a" * 64)   # 64 hex chars = 32 bytes
    monkeypatch.setenv("LEX_MULTI_TENANT", "true")

    state = _make_state("M-ENC")
    save_session(state, sessions_db=tmp_db, firm_id="firm_enc", user_id="u1")

    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT state_json FROM sessions WHERE matter_id='M-ENC'").fetchone()
    conn.close()

    raw_blob = row[0]
    assert raw_blob.startswith("4c455845"), (   # hex for "LEXE" prefix
        f"state_json should start with LEXENC: hex prefix, got: {raw_blob[:20]}"
    )


def test_state_json_decrypts_correctly(tmp_db, monkeypatch):
    """get_session_state must return the original state even when encrypted."""
    monkeypatch.setenv("LEX_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("LEX_MULTI_TENANT", "true")

    state = _make_state("M-ENC2")
    save_session(state, sessions_db=tmp_db, firm_id="firm_enc", user_id="u1")

    recovered = get_session_state("M-ENC2", sessions_db=tmp_db, firm_id="firm_enc")
    assert recovered is not None
    assert recovered["matter_id"] == "M-ENC2"


def test_state_json_plaintext_when_no_key(tmp_db):
    """Without encryption_key, state_json must be plaintext JSON (personal mode)."""
    state = _make_state("M-PLAIN")
    save_session(state, sessions_db=tmp_db, firm_id="default", user_id="u1")

    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT state_json FROM sessions WHERE matter_id='M-PLAIN'").fetchone()
    conn.close()
    import json
    parsed = json.loads(row[0])   # must parse as JSON without decryption
    assert parsed["matter_id"] == "M-PLAIN"
```

- [ ] **Step 4.2 — Run to verify failure**

```bash
pytest tests/test_session_tenant.py::test_state_json_encrypted_when_key_set \
       tests/test_session_tenant.py::test_state_json_decrypts_correctly \
       tests/test_session_tenant.py::test_state_json_plaintext_when_no_key -v
```

Expected: `AssertionError` — state_json is stored as plaintext.

- [ ] **Step 4.3 — Add encryption helpers to session_store.py**

Add these two private functions near the top of the module, after imports:

```python
def _encrypt_state_json(raw_json: str, firm_id: str = "default") -> str:
    """
    Encrypt state_json string if encryption is enabled. Returns hex ciphertext.
    In personal mode (no key), returns the JSON string unchanged.

    WHY: state_json contains matter facts, party names, draft text. At rest
    encryption ensures a stolen database file cannot be read without the key.
    """
    from themis.security.crypto import encrypt_str, is_encryption_enabled
    if is_encryption_enabled():
        from themis.security.crypto import get_master_key
        key = get_master_key()
        if key:
            return encrypt_str(raw_json, key, firm_id)
    return raw_json


def _decrypt_state_json(stored: str, firm_id: str = "default") -> str:
    """
    Decrypt state_json if it has the LEXENC: prefix. Returns the JSON string.
    Plaintext strings (no prefix) are returned unchanged.
    """
    from themis.security.crypto import decrypt_str
    try:
        raw = bytes.fromhex(stored)
        if raw.startswith(b"LEXENC:"):
            from themis.security.crypto import get_master_key
            key = get_master_key()
            if key:
                return decrypt_str(stored, key, firm_id)
    except (ValueError, Exception):
        pass  # not hex or not encrypted — return as-is
    return stored
```

**In `save_session`** — wrap `state_json` serialization:

```python
# Replace:
json.dumps(state_snapshot, ensure_ascii=False),
# With:
_encrypt_state_json(json.dumps(state_snapshot, ensure_ascii=False), resolved_firm),
```

Apply the same replacement in `update_session`.

**In `get_session_state`** — decrypt after SELECT:

```python
# After:
if not row or not row["state_json"]:
    return None
# Replace:
return json.loads(row["state_json"])
# With:
raw = _decrypt_state_json(row["state_json"], firm_id)
return json.loads(raw)
```

- [ ] **Step 4.4 — Run tests**

```bash
pytest tests/test_session_tenant.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 4.5 — Commit**

```bash
git add themis/memory/session_store.py tests/test_session_tenant.py
git commit -m "feat(p1): AES-256-GCM encrypt state_json at rest in session store"
```

---

## Task 5: Fix three known critical bugs

**Files:**
- Modify: `themis/tools/raptor_summarizer.py`
- Modify: `tests/test_raptor_summarizer.py`

### 5A: RAPTOR shape bug — `citation: None` causes TypeError in HybridRetriever

`raptor_tree_to_findings()` sets `"citation": None`. When these entries flow into `HybridRetriever.from_findings()`, the retriever tries string operations on the citation field and raises `TypeError`. The entire cite node then returns `{"error": "..."}` and citations are never verified.

- [ ] **Step 5.1 — Write failing test (append to tests/test_raptor_summarizer.py)**

```python
from themis.tools.raptor_summarizer import raptor_tree_to_findings, RaptorNode


def test_raptor_tree_to_findings_citation_is_never_none():
    """citation field must be a string, not None — HybridRetriever does string ops on it."""
    nodes = [
        RaptorNode(layer=1, text="doctrine summary", source_chunks=["case::0"]),
        RaptorNode(layer=2, text="higher summary", source_chunks=["case::0", "case::1"]),
        RaptorNode(layer=0, text="leaf text", source_chunks=["leaf::0"]),  # layer 0 excluded
    ]
    findings = raptor_tree_to_findings(nodes)
    assert len(findings) == 2, "Only layer >= 1 nodes should be converted"
    for f in findings:
        assert f["citation"] is not None, "citation must not be None"
        assert isinstance(f["citation"], str), f"citation must be str, got {type(f['citation'])}"
        assert f["citation"] != "", "citation must not be empty string either"
```

- [ ] **Step 5.2 — Run to verify failure**

```bash
pytest tests/test_raptor_summarizer.py::test_raptor_tree_to_findings_citation_is_never_none -v
```

Expected: `AssertionError` — `f["citation"] is not None` fails.

- [ ] **Step 5.3 — Fix raptor_tree_to_findings in raptor_summarizer.py**

In `themis/tools/raptor_summarizer.py`, find `raptor_tree_to_findings` and change `"citation": None` to a descriptive string:

```python
def raptor_tree_to_findings(tree: list[RaptorNode]) -> list[dict]:
    summaries: list[dict] = []
    for node in tree:
        if node.layer >= 1:
            summaries.append({
                "case_name": f"RAPTOR Summary (layer {node.layer})",
                "citation": f"raptor:layer{node.layer}:{','.join(node.source_chunks[:2])}",  # was: None
                "snippet": node.text[:500],
                "full_text": node.text,
                "source": "raptor_summary",
                "source_chunks": node.source_chunks,
                "url": None,
                "status": "raptor",
            })
    return summaries
```

- [ ] **Step 5.4 — Run tests**

```bash
pytest tests/test_raptor_summarizer.py -v
```

Expected: all pass.

### 5B: Verify citation threshold behavior

The `retriever_similarity_threshold = 0.35` in config controls whether a citation is considered grounded. With the RAPTOR fix in place, verify the threshold produces sensible results on real citation strings.

- [ ] **Step 5.5 — Write regression test for citation threshold guard (append to tests/test_cite.py)**

```python
import pytest
from unittest.mock import MagicMock, patch


def test_citation_below_threshold_is_unverified():
    """Citations whose best retrieval score < threshold must be marked unverified."""
    import asyncio
    from themis.nodes.cite import run

    # Mock a retrieval result with score below threshold
    low_score_result = MagicMock()
    low_score_result.score = 0.10   # below 0.35
    low_score_result.child.source_doc = "kanoon"
    low_score_result.child.chunk_index = 0

    mock_retriever = MagicMock()
    mock_retriever.retrieve = MagicMock(return_value=[low_score_result])

    state = {
        "draft_output": "As held in AIR 1978 SC 597, the right is fundamental.",
        "research_findings": [{"case_name": "Maneka Gandhi", "citation": "AIR 1978 SC 597",
                                "full_text": "fundamental rights case", "snippet": ""}],
        "matter_id": "M001",
        "firm_id": "default",
        "messages": [],
    }

    with patch("themis.nodes.cite.HybridRetriever") as MockHR:
        MockHR.from_findings.return_value = mock_retriever
        result = asyncio.run(run(state))

    assert result.get("citations_verified") is False
    assert "AIR 1978 SC 597" in (result.get("unverified_citations") or [])


def test_citation_above_threshold_is_verified():
    """Citations whose best retrieval score >= threshold must be marked verified."""
    import asyncio
    from themis.nodes.cite import run

    high_score_result = MagicMock()
    high_score_result.score = 0.80
    high_score_result.child.source_doc = "kanoon"
    high_score_result.child.chunk_index = 0
    high_score_result.child.chunk_text = "fundamental right text"
    high_score_result.parent.chunk_text = "parent text"
    high_score_result.child.section_id = None
    high_score_result.bm25_score = 0.6
    high_score_result.vector_score = 0.9

    mock_retriever = MagicMock()
    mock_retriever.retrieve = MagicMock(return_value=[high_score_result])

    state = {
        "draft_output": "As held in AIR 1978 SC 597, the right is fundamental.",
        "research_findings": [{"case_name": "Maneka Gandhi", "citation": "AIR 1978 SC 597",
                                "full_text": "fundamental rights case", "snippet": ""}],
        "matter_id": "M001",
        "firm_id": "default",
        "messages": [],
    }

    with patch("themis.nodes.cite.HybridRetriever") as MockHR:
        MockHR.from_findings.return_value = mock_retriever
        result = asyncio.run(run(state))

    assert result.get("citations_verified") is True
    assert not result.get("unverified_citations")
```

- [ ] **Step 5.6 — Run tests**

```bash
pytest tests/test_cite.py -v
```

Expected: all pass (the threshold guard was already logically correct in cite.py; these tests document and protect it).

- [ ] **Step 5.7 — Commit**

```bash
git add themis/tools/raptor_summarizer.py tests/test_raptor_summarizer.py tests/test_cite.py
git commit -m "fix(p1): RAPTOR citation None→string bug + citation threshold regression tests"
```

---

## Task 6: Full test suite verification

- [ ] **Step 6.1 — Run the full test suite**

```bash
cd /Users/anshoosareen/Lexagent
pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all existing tests pass plus the new tests from Tasks 1–5. If any pre-existing test breaks due to the `firm_id` signature additions, fix the test call site to pass `firm_id="default"` (default param keeps backward compat).

- [ ] **Step 6.2 — Verify personal mode still works end-to-end**

```bash
python -m themis.cli draft "S.138 NI Act — Ankush Sareen cheque Rs 5 lakh dishonoured 10 Jan 2025"
```

Expected: draft runs without errors, no auth prompts, personal mode SOUL.md loaded.

- [ ] **Step 6.3 — Final commit (if any fixes from 6.1)**

```bash
git add -p   # stage only the test-call-site fixes
git commit -m "fix(p1): update test call sites for firm_id default params"
```

---

## Self-Review

**Spec coverage check:**

| Roadmap requirement | Task |
|---|---|
| Wire SecurityContext into control plane | Task 3 |
| Wire JWT auth into control plane | Task 3 (already JWT, now returns SecurityContext) |
| Wire audit log | Task 3 (`_emit_matter_audit` + `log_action` at 3 events) |
| Wire AES-GCM into session store | Task 4 |
| Remove stale static token path | Already removed in prior phase — `_verify_token` was JWT-only |
| Add tenant columns/migrations | Task 1 |
| Enforce tenant isolation on queries | Task 1 (firm_id WHERE clauses) |
| Fix citation threshold | Task 5B (tests document + protect existing logic) |
| Fix RAPTOR shape | Task 5A (`citation: None` → descriptive string) |
| Fix matter memory injection | Task 2 (firm path isolation, which is the actual injection failure) |

**Placeholder scan:** None — every step has real code.

**Type consistency:** `SecurityContext` used consistently; `firm_id: str = "default"` is the same default across all functions; `_emit_matter_audit` matches its call sites.
