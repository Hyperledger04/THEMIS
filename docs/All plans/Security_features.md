# LexAgent — Security, Enterprise & Multi-Tenant Plan
## Phase 9.1–9.6

---

## Context

LexAgent is currently at Phase 8 (279 tests passing). The config and state already have multi-tenant scaffolding (`firm_id`, `user_id` in `LexState`; `multi_tenant`, `default_firm_id`, `api_secret_key` in `LexConfig`) but **none of it is enforced**. Key gaps:

- Sessions DB has no `user_id`/`firm_id` columns — all lawyers share the same flat table
- Auth is a single static string compare, not JWT; WebSocket endpoint has **zero auth**
- `state_json` stored as plaintext JSON — client matter data unencrypted
- SOUL.md and per-matter MEMORY.md are unencrypted flat files
- No audit log, no rate limiting, no budget caps, no GDPR erasure path
- CORS is `allow_origins=["*"]` in control_plane.py

**Lavern** (AnttiHero/lavern, Apache 2.0, TypeScript) solves the same multi-tenant legal SaaS problem. Its DB schema, auth token pattern, rate limiting env vars, audit log design, and GDPR export/erasure pattern are directly applicable. Key patterns to adapt (not copy verbatim — it's TypeScript, we're Python):

- Row-level isolation: `user_id` FK on every table, queries always filtered
- scrypt hashed auth tokens stored in DB; plaintext only in HTTP response
- `LAVERN_AUTH_ENABLED=true` flag pattern (maps to `multi_tenant=True` in LexConfig)
- Audit log: `(timestamp, user_id, action, resource, ip, user_agent, detail_json)`
- Rate limiting per-user and global via env vars
- GDPR: `exportUserData()` + `softDeleteUser()` patterns
- `is_global` flag on knowledge collections for shared legal datasets

---

## Files to Modify

| File | Changes |
|------|---------|
| `lexagent/memory/session_store.py` | Add `user_id`, `firm_id` columns; filter all queries by them; add `audit_log` and `users` tables; add `api_tokens` table |
| `lexagent/config.py` | Add rate limit fields, audit dir, encryption key field, GDPR config |
| `lexagent/gateway/control_plane.py` | Replace static token auth with DB token lookup; add rate limiting middleware; restrict CORS in prod; add WebSocket auth; add GDPR endpoints |
| `lexagent/memory/soul.py` | Encrypt SOUL.md at rest using `LEX_ENCRYPTION_KEY` |
| `lexagent/memory/matter_memory.py` | Encrypt MEMORY.md files at rest |
| `pyproject.toml` | Add `cryptography`, `slowapi` dependencies |
| New: `lexagent/security/` | `crypto.py` (encrypt/decrypt helpers), `tokens.py` (token hashing, JWT), `audit.py` (audit log writer) |
| New: `tests/test_security.py` | Tests for all new security primitives |

---

## Phase 9.1 — Multi-Tenant DB Isolation

**Goal:** Every session, reminder, and future table is scoped to a `(firm_id, user_id)` pair.

### DB Schema Migration (`session_store.py`)

Add a `schema_version` migration runner. On `SCHEMA_VERSION = 2`:

```sql
-- Add tenant columns to sessions
ALTER TABLE sessions ADD COLUMN firm_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE sessions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';
CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions(firm_id, user_id);

-- Add tenant column to reminders
ALTER TABLE reminders ADD COLUMN firm_id TEXT NOT NULL DEFAULT 'default';

-- Users table (for multi-tenant mode)
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,           -- UUID
    firm_id     TEXT NOT NULL,
    email       TEXT NOT NULL,
    password_hash TEXT,                     -- scrypt: "salt:key" hex
    display_name TEXT,
    role        TEXT NOT NULL DEFAULT 'lawyer',  -- 'admin' | 'lawyer' | 'viewer'
    created_at  TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0,
    UNIQUE(firm_id, email)
);

-- Hashed bearer tokens (plaintext shown once, hash stored)
CREATE TABLE IF NOT EXISTS api_tokens (
    token_hash  TEXT PRIMARY KEY,           -- SHA-256 of plaintext
    user_id     TEXT NOT NULL REFERENCES users(id),
    firm_id     TEXT NOT NULL,
    label       TEXT,
    expires_at  TEXT,
    created_at  TEXT NOT NULL,
    last_used_at TEXT
);

-- Audit log
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    firm_id     TEXT,
    user_id     TEXT,
    action      TEXT NOT NULL,
    resource    TEXT,
    ip          TEXT,
    user_agent  TEXT,
    detail_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(firm_id, user_id);
```

### Query Changes

All `save_session`, `update_session`, `search_sessions`, `list_sessions`, `get_session_state` must accept optional `firm_id` and `user_id` parameters and filter by them. Existing calls from CLI use defaults (`default`, `default`) — no breaking change.

**New function signatures:**
```python
def save_session(state: LexState, sessions_db: str = ...) -> int
# state now carries firm_id and user_id → extracted and stored
```

---

## Phase 9.2 — Auth Layer

**Goal:** Replace static string compare with DB-backed hashed tokens. Gate WebSocket too.

### `lexagent/security/` package

> **Crypto choices (from CRG deep analysis):** Use **AES-256-GCM** (via `cryptography` AESGCM) for field/file encryption — more standard than Fernet (Fernet is AES-128-CBC). Use **argon2** (via `argon2-cffi`) for password hashing — preferred over scrypt for new code.

**`crypto.py`**
```python
import hashlib, os, hmac
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def hash_token(plaintext: str) -> str:
    """SHA-256 hex digest — stored in api_tokens.token_hash."""
    return hashlib.sha256(plaintext.encode()).hexdigest()

def generate_token() -> str:
    """URL-safe 32-byte random token."""
    return secrets.token_urlsafe(32)

def get_fernet(key: str) -> Fernet:
    """Return a Fernet instance from a base64-encoded 32-byte key."""
    return Fernet(key.encode())

def encrypt_text(plaintext: str, key: str) -> str:
    return get_fernet(key).encrypt(plaintext.encode()).decode()

def decrypt_text(ciphertext: str, key: str) -> str:
    return get_fernet(key).decrypt(ciphertext.encode()).decode()
```

**`tokens.py`**
```python
# DB-backed token auth (replaces static cfg.api_secret_key compare)
def verify_db_token(token: str, sessions_db: str) -> Optional[dict]:
    """Look up token by hash. Return {firm_id, user_id} or None."""
    h = hash_token(token)
    with _connect(sessions_db) as conn:
        row = conn.execute(
            "SELECT firm_id, user_id FROM api_tokens WHERE token_hash = ? AND (expires_at IS NULL OR expires_at > ?)",
            (h, datetime.now().isoformat())
        ).fetchone()
    if row:
        conn.execute("UPDATE api_tokens SET last_used_at = ? WHERE token_hash = ?",
                     (datetime.now().isoformat(), h))
        return dict(row)
    return None
```

**`audit.py`**
```python
def log_action(sessions_db: str, action: str, firm_id=None, user_id=None,
               resource=None, ip=None, user_agent=None, detail: dict = None) -> None:
    with _connect(sessions_db) as conn:
        conn.execute(
            "INSERT INTO audit_log (timestamp, firm_id, user_id, action, resource, ip, user_agent, detail_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), firm_id, user_id, action, resource, ip, user_agent,
             json.dumps(detail or {}))
        )
```

### `control_plane.py` Changes

1. **Replace `_verify_token`** — if `multi_tenant=True`, query `api_tokens` table via `verify_db_token()`. Falls back to static key or open in single-user mode.

2. **WebSocket auth** — read token from `?token=` query param or first WS message before graph invocation:
```python
@app.websocket("/ws/{matter_id}")
async def ws_endpoint(websocket: WebSocket, matter_id: str, token: Optional[str] = None):
    cfg = LexConfig()
    if cfg.multi_tenant:
        if not token:
            await websocket.close(code=4001, reason="Missing token")
            return
        auth = verify_db_token(token, cfg.sessions_db)
        if not auth:
            await websocket.close(code=4003, reason="Invalid token")
            return
```

3. **CORS tightening** — use `cfg.cors_origins` (new config field, defaults to `["*"]` for dev):
```python
app.add_middleware(CORSMiddleware,
    allow_origins=cfg.cors_origins,  # set to lexanodes domain in prod
    ...)
```

4. **New config fields** in `LexConfig`:
```python
cors_origins: List[str] = Field(["*"], ...)
encryption_key: Optional[str] = Field(None, ...)     # Fernet key for at-rest encryption
rate_limit_max: int = Field(100, ...)                 # global req/min
rate_limit_user_max: int = Field(20, ...)             # per-user req/min
audit_log_retain_days: int = Field(90, ...)
```

---

## Phase 9.3 — Encryption at Rest

**Goal:** SOUL.md, per-matter MEMORY.md, and `state_json` in sessions.db encrypted when `LEX_ENCRYPTION_KEY` is set.

### Strategy

Use **Fernet symmetric encryption** (from `cryptography` package — already a common Python dep). Key stored in `LEX_ENCRYPTION_KEY` env var (base64-encoded 32-byte key). Single-user mode: key is optional (unencrypted, backward-compatible).

### `soul.py` and `matter_memory.py`

Both currently read/write plain markdown. Add optional encrypt/decrypt wrapper:

```python
def _read_file(path: Path, encryption_key: Optional[str]) -> str:
    raw = path.read_bytes()
    if encryption_key and raw.startswith(b"LEXENC:"):
        return decrypt_text(raw[7:].decode(), encryption_key)
    return raw.decode()

def _write_file(path: Path, content: str, encryption_key: Optional[str]) -> None:
    if encryption_key:
        encrypted = encrypt_text(content, encryption_key)
        path.write_bytes(b"LEXENC:" + encrypted.encode())
    else:
        path.write_text(content)
```

The `LEXENC:` prefix lets the reader detect whether a file is encrypted (safe to open with `lex setup` even after a key change).

### `session_store.py` — `state_json` Column

Wrap `json.dumps(state_snapshot)` in `encrypt_text()` before INSERT, and `decrypt_text()` before `json.loads()` on read. Only when `encryption_key` is set.

---

## Phase 9.4 — Audit Logging

**Goal:** Every draft creation, tool invocation, login, and matter access logged to `audit_log` table.

### Enforcement Points

| Action | Where to instrument |
|--------|-------------------|
| Matter draft created | `control_plane.py:send_message` — after graph completes |
| Matter accessed | `control_plane.py:send_message` — on request receipt |
| Document uploaded | `control_plane.py:upload_document` |
| Token verified | `security/tokens.py:verify_db_token` |
| Token created/revoked | New `/api/v1/tokens` endpoint |
| Session saved | `session_store.py:save_session` |
| Research tool invoked | `nodes/research.py` — log which tools were called |

Call `log_action()` from `security/audit.py` at each point. Non-blocking — log failure must not break the request.

### Audit Retention

Add `rotate_audit_log(retain_days: int, sessions_db: str)` to session_store — deletes rows older than retain_days. Called by `lex setup` and optionally on control plane startup.

> **Indian Legal Compliance:** Indian legal matters require 7-year document retention (Limitation Act context). `audit_log_retain_days` should default to `2555` (7 years) in `LexConfig`, not 90 days. The `config.py` default must be updated accordingly.

---

## Phase 9.5 — Rate Limiting & Budget Caps

**Goal:** Protect control plane and Telegram gateway from abuse; enforce per-firm LLM spend caps.

### Rate Limiting (`control_plane.py`)

Use `slowapi` (FastAPI-compatible `limits` wrapper):

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/v1/matters/{matter_id}/message")
@limiter.limit(f"{cfg.rate_limit_user_max}/minute")
async def send_message(...): ...
```

Per-user rate key: use `auth["firm_id"] + ":" + auth["user_id"]` once auth is DB-backed.

### Budget Caps

Add to `LexConfig`:
```python
default_budget_usd: float = Field(10.0, ...)  # per matter
max_monthly_spend_usd: float = Field(100.0, ...)
```

Add `daily_spend` table (mirrors lavern pattern):
```sql
CREATE TABLE IF NOT EXISTS daily_spend (
    date_utc TEXT PRIMARY KEY,
    firm_id  TEXT NOT NULL,
    total_usd REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL
);
```

Increment in `nodes/_llm.py` after each LLM call using LangChain callback token counts. Check against cap before invoking graph — return `{"error": "budget_exceeded"}` if over limit.

---

## Phase 9.6 — GDPR & Deployment Hardening

**Goal:** Data portability + erasure for client matters; prod-ready Docker config.

### GDPR Functions (`session_store.py`)

```python
def export_user_data(firm_id: str, user_id: str, sessions_db: str) -> dict:
    """Article 20: return all sessions, reminders, audit entries for user."""

def soft_delete_user(firm_id: str, user_id: str, sessions_db: str) -> None:
    """Article 17: anonymize email in users table, delete api_tokens,
    set state_json='[deleted]' on sessions, clear reminder telegrams."""
```

### Deployment Hardening

**`docker-compose.yml` additions** (new file for LexAgent):
```yaml
environment:
  - LEX_ENCRYPTION_KEY=${LEX_ENCRYPTION_KEY}
  - LEX_API_SECRET=${LEX_API_SECRET}
  - LEX_MULTI_TENANT=true
  - LEX_CORS_ORIGINS=https://lexanodes.com
secrets:
  - anthropic_key
```

**`.env.example` additions:**
```
LEX_ENCRYPTION_KEY=          # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
LEX_MULTI_TENANT=false       # Set true for SaaS / multi-firm mode
LEX_CORS_ORIGINS=*           # Restrict to your domain in production
LEX_RATE_LIMIT_MAX=100       # Global requests per minute
LEX_RATE_LIMIT_USER_MAX=20   # Per user per minute
LEX_ENCRYPTION_KEY=          # Fernet key — leave blank for unencrypted (single-user)
LEX_AUDIT_LOG_RETAIN_DAYS=90
```

**`SECURITY.md`** (new file) — document: vulnerability disclosure, in-scope assets, auth architecture, encryption scheme, known gaps (no CSP headers, no sandboxed PDF parsing).

---

## Lavern Feature Mapping — What to Adopt vs Skip

| Lavern Feature | Adopt? | Notes |
|----------------|--------|-------|
| Row-level user_id isolation | ✅ YES | Core of Phase 9.1 |
| Hashed auth tokens in DB | ✅ YES | Phase 9.2 |
| scrypt password hashing | ✅ YES | If adding user accounts |
| Audit log table | ✅ YES | Phase 9.4 |
| Per-user + global rate limits | ✅ YES | Phase 9.5 |
| Budget caps with daily_spend | ✅ YES | Phase 9.5 |
| GDPR export + soft delete | ✅ YES | Phase 9.6 |
| `is_global` flag on KB collections | ✅ YES | For shared Indian legal datasets (CUAD-equivalent) |
| Google OAuth + Stripe billing | ⏳ LATER | Phase 10 — SaaS monetization |
| 67 specialized debate agents | ❌ SKIP | Different architecture — lavern is contract review, LexAgent is litigation drafting |
| React dashboard (viz/) | ❌ SKIP | lexanodes/ already handles web UI |
| macOS menu bar app | ❌ SKIP | Out of scope |
| Clawern daemon (28 modules) | ❌ SKIP | LexAgent CLI + Telegram gateway cover this use case |

---

## Build Order & Checkpoints

| Step | Files | Checkpoint |
|------|-------|-----------|
| 1. `lexagent/security/` package | `crypto.py`, `tokens.py`, `audit.py` | `pytest tests/test_security.py` passes |
| 2. DB migration (schema v2) | `session_store.py` | `pytest tests/test_session_store.py` passes; existing sessions still load |
| 3. Config fields | `config.py` | `pytest tests/test_config.py` passes |
| 4. Auth layer in control plane | `control_plane.py` | `curl -H "Authorization: Bearer <token>" /api/v1/matters` returns 200 |
| 5. WebSocket auth | `control_plane.py` | WS connect without token → 4003 close |
| 6. Encryption at rest | `soul.py`, `matter_memory.py`, `session_store.py` | `lex draft "test"` round-trips; SOUL.md starts with `LEXENC:` when key set |
| 7. Audit log | `audit.py` + enforcement points | `lex draft "test"` → audit_log has 2+ rows |
| 8. Rate limiting | `control_plane.py` + `slowapi` | 21st request in 1 min → 429 |
| 9. GDPR endpoints | `session_store.py` + control plane routes | `GET /api/v1/me/export` returns all user data |
| 10. `.env.example` + `SECURITY.md` | Root | `lex setup` prompts for encryption key |

---

## Dependencies to Add (`pyproject.toml`)

```toml
"cryptography>=43.0",      # Fernet encryption
"slowapi>=0.1.9",          # Rate limiting for FastAPI
"python-jose[cryptography]>=3.3",  # JWT (Phase 9.2 stretch — for proper multi-user JWT)
```

---

## What NOT to Build Yet

- Google OAuth / Stripe — lavern has it, but LexAgent's SaaS phase is later
- CSP/HSTS headers — valid gap but requires nginx/reverse-proxy config, not app code  
- Sandboxed PDF parsing — important but separate from auth/multi-tenant work
- Vector-level tenant isolation in Qdrant — already handled by `firm_id` namespace prefix in `PersistentQdrantRetriever`; no change needed
