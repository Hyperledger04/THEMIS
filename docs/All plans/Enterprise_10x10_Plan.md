# LexAgent — 10/10 Enterprise Security + Dual-Mode Architecture Plan

## Goal
Achieve **10/10 on every enterprise security benchmark** while keeping `lex draft "brief"` working instantly with zero friction in personal mode. One codebase, one env var controls the mode.

---

## Dual-Mode Contract

| | Personal Mode (`LEX_MULTI_TENANT=false`) | Enterprise SaaS (`LEX_MULTI_TENANT=true`) |
|---|---|---|
| Auth | Skipped — default `SecurityContext` injected | JWT required (15 min access + 7 day refresh) |
| DB isolation | `firm_id='default'` passthrough | `TenantScope` enforces `WHERE firm_id=?` on every query |
| Encryption | Warn if key unset, skip | **Refuse startup** if `LEX_ENCRYPTION_KEY` unset |
| Rate limiting | Disabled (log warning) | `slowapi` mandatory (5/min draft, 20/min user, 100/min global) |
| CORS | `localhost:3000/8080` allow-list | `LEX_CORS_ORIGINS` required, wildcard → `SystemExit` |
| Audit log | Local SQLite, no `firm_id` | Full table, 7-year retention (Indian legal compliance) |
| WebSocket auth | Token optional | Token in `?token=` required before `accept()` |
| TLS | Warn if not behind proxy | `LEX_REQUIRE_TLS=true` blocks HTTP requests |
| Secrets | `.env` file acceptable | Platform env vars only — `.env` file → `SystemExit` |
| Security headers | Always applied | Always applied + HSTS + CSP |

The gate for every conditional check: `if ctx.is_multi_tenant:` — zero impact on personal mode.

---

## Pre-Work: Fix 3 Critical Bugs First (7 SP, 2.5 hours)

These must land **before** enterprise work begins — they cause silent data corruption in production.

| Bug | Location | Fix | Effort |
|---|---|---|---|
| **CRIT-01** Threshold bypass: unrelated chunk marked as verified citation | `tools/retriever.py:145-151` + `cite.py:114` | Score check before `verified=True` | 30 min |
| **CRIT-02** RAPTOR crash: `KeyError: 'relevance'` when `LEX_RAPTOR_ENABLED=true` | `draft.py:156-163` | Filter RAPTOR entries; map `snippet`→`relevance` | 1 hr |
| **CRIT-03** Matter memory never injected: `MEMORY.md` written but never read by LLM | `draft.py:196-199` | Load and inject matter memory before draft call | 1 hr |

---

## New Package: `lexagent/security/`

```
lexagent/security/
├── __init__.py          # Re-exports SecurityContext, Role, require_permission
├── context.py           # SecurityContext (frozen dataclass) + TenantScope CM + get_security_context dep
├── crypto.py            # AES-256-GCM + HKDF per-firm key derivation
├── tokens.py            # JWT encode/decode + argon2id + refresh token + API key lifecycle
├── audit.py             # log_action() (non-blocking) + purge_old_audit_entries()
├── rate_limit.py        # slowapi setup + per-tier limiters + budget cap check
├── permissions.py       # Role enum + PERMISSION_MATRIX + @require_permission decorator
├── secrets.py           # SecretBackend ABC + EnvBackend + VaultBackend + AWSSecretsBackend
└── gdpr.py              # export_user_data() + soft_delete_user()
```

---

## 1. Authentication — 10/10

### SecurityContext (replaces `_verify_token`)

```python
# lexagent/security/context.py
from dataclasses import dataclass
from enum import Enum

class Role(str, Enum):
    ADMIN     = "admin"
    PARTNER   = "partner"
    ASSOCIATE = "associate"
    VIEWER    = "viewer"

@dataclass(frozen=True)
class SecurityContext:
    firm_id: str
    user_id: str
    role: Role
    is_multi_tenant: bool
    ip: str | None = None
    user_agent: str | None = None
    token_jti: str | None = None

    @classmethod
    def personal_default(cls, cfg) -> "SecurityContext":
        return cls(firm_id=cfg.default_firm_id, user_id="default",
                   role=Role.ADMIN, is_multi_tenant=False)
```

### New Tables (`session_store.py` migration v2→v3)

```sql
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,              -- UUID4
    firm_id       TEXT NOT NULL,
    email         TEXT NOT NULL,
    password_hash TEXT,                          -- argon2id
    display_name  TEXT,
    role          TEXT NOT NULL DEFAULT 'associate',
    created_at    TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    UNIQUE(firm_id, email)
);

CREATE TABLE IF NOT EXISTS api_tokens (
    id           TEXT PRIMARY KEY,              -- UUID4; jti for JWTs
    token_hash   TEXT NOT NULL UNIQUE,          -- SHA-256 of plaintext refresh token
    user_id      TEXT NOT NULL REFERENCES users(id),
    firm_id      TEXT NOT NULL,
    type         TEXT NOT NULL,                 -- 'refresh' | 'api_key'
    expires_at   TEXT,
    created_at   TEXT NOT NULL,
    revoked_at   TEXT,
    last_used_at TEXT
);
```

### `lexagent/security/tokens.py` key functions

```python
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS   = 7
ALGORITHM = "HS256"

def hash_password(password: str) -> str:          # argon2id
def verify_password(password: str, hash_: str) -> bool:
def hash_token(plaintext: str) -> str:            # SHA-256 hex for DB storage
def generate_access_token(user_id, firm_id, role, secret) -> str:   # JWT, 15 min
def decode_access_token(token, secret) -> dict:   # raises JWTError on invalid/expired
def generate_refresh_token() -> tuple[str, str]:  # (plaintext, hash) — store hash
def generate_api_key() -> tuple[str, str]:        # ("lex_<random>", hash)
```

### API Endpoints (all under `/api/v1/auth/`)

| Endpoint | Action |
|---|---|
| `POST /register` | argon2id hash + insert `users` row + email verification |
| `POST /login` | verify password + issue JWT + refresh token (hashed in DB) |
| `POST /refresh` | rotate refresh token (revoke old, issue new) — prevents replay |
| `POST /logout` | set `revoked_at` on refresh token |

### CLI: `lex login`
Stores JWT + refresh token in `~/.lexagent/token` with `chmod 600`.

### WebSocket Auth
Token in `?token=` query param, validated **before** `websocket.accept()`. Wrong/missing token → `close(code=4001/4003)`.

---

## 2. Authorization — 10/10

### Permission Matrix

```python
PERMISSION_MATRIX = {
    "admin":     {"matter.*", "draft.*", "research.run", "document.*", "user.*",
                  "token.*", "audit.read", "key.rotate", "firm.settings", "gdpr.*"},
    "partner":   {"matter.create", "matter.read", "draft.*", "research.run",
                  "document.*", "user.read", "token.create", "audit.read", "gdpr.export"},
    "associate": {"matter.create", "matter.read", "draft.*", "research.run",
                  "document.*", "token.create"},
    "viewer":    {"matter.read", "draft.read", "document.read"},
}
```

### `@require_permission("draft.create")` FastAPI dependency
- Personal mode: all permissions granted (no check)
- Enterprise mode: role looked up from JWT claim — 403 if not in matrix

### Matter Ownership Check
Every endpoint taking `matter_id` calls `verify_matter_ownership(matter_id, ctx, db)` — 403 if matter exists under a different `firm_id`.

---

## 3. Multi-Tenant DB Isolation — 10/10

### Schema Migration v2 (in `session_store.py`)

```sql
-- sessions table
ALTER TABLE sessions ADD COLUMN firm_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE sessions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';
CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions(firm_id, user_id);

-- reminders table
ALTER TABLE reminders ADD COLUMN firm_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE reminders ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';

-- New tables: users, api_tokens, audit_log, daily_spend
```

### `TenantScope` Context Manager

```python
class TenantScope:
    def execute(self, sql: str, params: tuple = (), *, tenant_filter: bool = True):
        if tenant_filter and self._ctx.is_multi_tenant:
            sql += (" AND " if "WHERE" in sql.upper() else " WHERE ")
            sql += "firm_id=? AND user_id=?"
            params = params + (self._ctx.firm_id, self._ctx.user_id)
        return self._conn.execute(sql, params)
```

All `session_store.py` query functions wrap with `TenantScope`. In personal mode `is_multi_tenant=False` → zero change to query behavior.

### LangGraph Postgres Thread Namespacing
`thread_id = f"{firm_id}___{matter_id}"` in enterprise mode (triple underscore avoids ambiguity). Existing personal-mode matters use bare `matter_id`.

---

## 4. Encryption at Rest — 10/10

### `lexagent/security/crypto.py` — AES-256-GCM + HKDF

```python
def encrypt_bytes(plaintext: bytes, master_key_hex: str, firm_id: str = "default") -> bytes:
    """
    HKDF-SHA256 derives per-firm 32-byte key from master key.
    AES-256-GCM encrypts with random 12-byte nonce.
    Output: b"LEXENC:" + nonce(12) + ciphertext+tag(variable)
    """

def decrypt_bytes(ciphertext: bytes, master_key_hex: str, firm_id: str = "default") -> bytes:
    """If no LEXENC: prefix → plaintext passthrough (backward compat)."""
```

**Why AES-256-GCM over Fernet (used in Security_features.md):**
- Fernet = AES-128-CBC + HMAC. GCM = AES-256 + AEAD (authenticated encryption, detects tampering without separate HMAC)
- HKDF per-firm key derivation: leaked key for `firm_a` cannot decrypt `firm_b` data
- Hardware-accelerated via AES-NI on every modern CPU

### What Gets Encrypted

| Data | Where | When |
|---|---|---|
| `sessions.state_json` | SQLite | Every `save_session` / `update_session` |
| `SOUL.md` | `~/.lexagent/SOUL.md` | Every `save_soul()` |
| `MEMORY.md` | `~/.lexagent/matters/*/MEMORY.md` | Every `save_matter_memory()` |
| `state.json` snapshots | `~/.lexagent/matters/*/state.json` | Every `_save_state_snapshot()` |

Detection: files starting with `LEXENC:` are encrypted; others pass through unmodified.

### Key Rotation CLI
`lex admin rotate-key --old-key X --new-key Y` — re-encrypts all rows + files, writes `key.rotated` to audit log.

---

## 5. Encryption in Transit — 10/10

### New Files: `docker-compose.yml` + `Caddyfile`

Caddy auto-provisions Let's Encrypt TLS — zero manual cert management:
```
{$LEX_DOMAIN} {
    reverse_proxy lexagent:8000
}
```

### In-App TLS Enforcement Middleware

```python
@app.middleware("http")
async def enforce_tls_and_headers(request, call_next):
    if cfg.multi_tenant and cfg.require_tls:
        if request.headers.get("x-forwarded-proto") != "https":
            return JSONResponse(status_code=400, content={"detail": "HTTPS required"})
    response = await call_next(request)
    # Always-on security headers:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Enterprise-only:
    if cfg.multi_tenant:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["Content-Security-Policy"] = cfg.csp_policy or DEFAULT_CSP
    return response
```

Also: `DATABASE_URL` must contain `sslmode=require` in enterprise mode. `qdrant_url` must be `https://`.

---

## 6. Audit Logging — 10/10

### `audit_log` Table

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    firm_id       TEXT,
    user_id       TEXT,
    action        TEXT NOT NULL,
    resource_type TEXT,
    resource_id   TEXT,
    ip            TEXT,
    user_agent    TEXT,
    detail_json   TEXT,
    schema_version INTEGER NOT NULL DEFAULT 3
);
CREATE INDEX IF NOT EXISTS idx_audit_ts   ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(firm_id, user_id);
CREATE INDEX IF NOT EXISTS idx_audit_act  ON audit_log(action);
```

**Retention:** `audit_retain_days = 2555` (7 years) — Indian legal compliance default.

### Instrumentation Points

| Location | Action |
|---|---|
| `control_plane.py:send_message` on request | `matter.accessed` |
| `control_plane.py:send_message` after graph | `draft.generated` |
| `control_plane.py:upload_document` | `document.uploaded` |
| `nodes/research.py` | `research.run` |
| Auth login success | `auth.login` |
| Auth logout | `auth.logout` |
| Token issued | `auth.token_issued` |
| Token revoked | `auth.token_revoked` |
| Key rotated | `key.rotated` |
| User created | `user.created` |
| GDPR delete | `user.deleted` |
| Session saved | `matter.created` |

`log_action()` is non-blocking — exceptions caught and logged; never propagate to request.

### Audit API: `GET /api/v1/audit` (admin only)
Supports `?action=`, `?start_date=`, `?end_date=`, `?limit=`, `?offset=` filtering.

---

## 7. Rate Limiting — 10/10

### Tiers (`slowapi`)

```python
@app.post("/api/v1/matters/{matter_id}/message")
@limiter.limit("5/minute")        # Draft endpoint: expensive LLM call
@limiter.limit("20/minute", key_func=get_user_key)
async def send_message(...): ...

@app.post("/api/v1/auth/login")
@limiter.limit("10/minute")       # Brute-force protection
```

Personal mode: `Limiter(enabled=False)` — zero impact.

### Budget Cap (`daily_spend` table)

```sql
CREATE TABLE IF NOT EXISTS daily_spend (
    date_utc  TEXT NOT NULL,
    firm_id   TEXT NOT NULL,
    user_id   TEXT NOT NULL,
    cost_usd  REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL,
    UNIQUE(date_utc, firm_id, user_id)
);
```

Before graph invocation: check `cost_usd >= max_daily_spend_usd` → 402 Payment Required.
After LLM call in `nodes/_llm.py`: increment `daily_spend` using LiteLLM `usage` field.

---

## 8. Secrets Management — 10/10

### Backend Abstraction (`lexagent/security/secrets.py`)

```python
class SecretBackend(ABC):
    def get(self, key: str) -> str | None: ...

class EnvBackend(SecretBackend):    # Railway, Render, Fly.io — no .env file
class VaultBackend(SecretBackend):  # HashiCorp Vault via hvac
class AWSSecretsBackend(SecretBackend):  # AWS Secrets Manager via boto3
```

Selected by `LEX_SECRETS_BACKEND=env|vault|aws`.

### Enterprise Startup Check

```python
def _key_loaded_from_file() -> bool:
    """Returns True if secrets found in .env file on disk."""
    for candidate in [".env", "~/.env"]:
        if Path(candidate).expanduser().exists():
            if "LEX_ENCRYPTION_KEY" in Path(candidate).expanduser().read_text():
                return True
    return False
```

If `_key_loaded_from_file()` returns True in enterprise mode → `SystemExit`.

### Per-Lawyer API Keys
`POST /api/v1/tokens` → generates `lex_<random>` key, stores argon2id hash, returns plaintext **once**. `lex token create --label "My CLI Key"`.

---

## 9. CORS — 10/10

```python
def _build_cors_config(cfg: LexConfig) -> dict:
    if cfg.multi_tenant:
        if not cfg.cors_origins or "*" in cfg.cors_origins:
            raise ValueError("LEX_CORS_ORIGINS required in enterprise mode; wildcard forbidden")
        return {
            "allow_origins": cfg.cors_origins,
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Authorization", "Content-Type", "X-Request-ID"],
        }
    return {  # Personal mode
        "allow_origins": ["http://localhost:3000", "http://localhost:8080"],
        "allow_credentials": False,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
```

CSP header built from `cfg.csp_policy` or `DEFAULT_CSP` constant — configurable per deployment.

---

## 10. WebSocket Security — 10/10

```python
@app.websocket("/ws/{matter_id}")
async def ws_endpoint(websocket: WebSocket, matter_id: str, token: str | None = None):
    if cfg.multi_tenant:
        if not token:
            await websocket.close(code=4001, reason="Token required"); return
        try:
            payload = decode_access_token(token, cfg.api_secret_key)
        except JWTError:
            await websocket.close(code=4003, reason="Invalid token"); return
    # Concurrent connection limit per user
    if cfg.multi_tenant and not await _acquire_ws_slot(user_id):
        await websocket.close(code=1008, reason="Too many connections"); return
    await websocket.accept()
    # Idle timeout: 300s
    raw = await asyncio.wait_for(websocket.receive_text(), timeout=300)
```

Max 3 concurrent WebSocket connections per user. Idle connections closed after 5 minutes.

---

## 11. GDPR — `lexagent/security/gdpr.py`

**`GET /api/v1/me/export`** (Article 20 — data portability)
Returns all sessions, reminders, audit log entries, and API tokens for the user.

**`DELETE /api/v1/me?confirm=DELETE_MY_DATA`** (Article 17 — right to erasure)
- Anonymizes email → `deleted_<uid8>@anon.lexagent`
- Nulls `password_hash`, `display_name`
- Sets `revoked_at` on all `api_tokens`
- Sets `state_json='[deleted]'` on sessions (preserves anonymized cost analytics)
- Nulls `telegram_user_id` on reminders
- Writes `user.deleted` to audit log

---

## 12. New Config Fields (`lexagent/config.py`)

| Field | Env Var | Default | Mode |
|---|---|---|---|
| `encryption_key` | `LEX_ENCRYPTION_KEY` | `None` | Both (warn personal, refuse enterprise) |
| `require_tls` | `LEX_REQUIRE_TLS` | `False` | Enterprise |
| `cors_origins` | `LEX_CORS_ORIGINS` | `["http://localhost:3000","http://localhost:8080"]` | Both |
| `csp_policy` | `LEX_CSP_POLICY` | `None` (uses default) | Enterprise |
| `secrets_backend` | `LEX_SECRETS_BACKEND` | `"env"` | Enterprise |
| `vault_url` | `LEX_VAULT_URL` | `None` | Enterprise (vault) |
| `vault_token` | `LEX_VAULT_TOKEN` | `None` | Enterprise (vault) |
| `aws_region` | `LEX_AWS_REGION` | `None` | Enterprise (aws) |
| `rate_limit_global` | `LEX_RATE_LIMIT_GLOBAL` | `100` | Enterprise |
| `rate_limit_user` | `LEX_RATE_LIMIT_USER` | `20` | Enterprise |
| `rate_limit_draft` | `LEX_RATE_LIMIT_DRAFT` | `5` | Enterprise |
| `max_daily_spend_usd` | `LEX_MAX_DAILY_SPEND_USD` | `0.0` (off) | Enterprise |
| `audit_retain_days` | `LEX_AUDIT_RETAIN_DAYS` | `2555` (7 years) | Both |
| `smtp_host` | `LEX_SMTP_HOST` | `None` | Enterprise |
| `smtp_port` | `LEX_SMTP_PORT` | `587` | Enterprise |
| `smtp_username` | `LEX_SMTP_USERNAME` | `None` | Enterprise |
| `smtp_password` | `LEX_SMTP_PASSWORD` | `None` | Enterprise |
| `email_from` | `LEX_EMAIL_FROM` | `None` | Enterprise |

---

## 13. Files to Create / Modify

| File | Action | What Changes |
|---|---|---|
| `lexagent/security/__init__.py` | CREATE | Package exports |
| `lexagent/security/context.py` | CREATE | `SecurityContext`, `TenantScope`, `get_security_context` |
| `lexagent/security/crypto.py` | CREATE | AES-256-GCM + HKDF |
| `lexagent/security/tokens.py` | CREATE | JWT + argon2id + refresh + API keys |
| `lexagent/security/audit.py` | CREATE | `log_action`, `purge_old_audit_entries` |
| `lexagent/security/rate_limit.py` | CREATE | `slowapi` setup, per-tier limiters |
| `lexagent/security/permissions.py` | CREATE | Role enum, matrix, `@require_permission` |
| `lexagent/security/secrets.py` | CREATE | Backend abstraction + env/vault/aws |
| `lexagent/security/gdpr.py` | CREATE | Export + soft delete |
| `lexagent/memory/session_store.py` | MODIFY | Migration v3, `TenantScope`, encrypt/decrypt `state_json`, new tables |
| `lexagent/memory/soul.py` | MODIFY | `_read_file`/`_write_file` encryption wrappers |
| `lexagent/memory/matter_memory.py` | MODIFY | Encryption wrappers + CRIT-03 fix |
| `lexagent/gateway/control_plane.py` | MODIFY | `get_security_context` dep, auth endpoints, rate limiting, CORS config, TLS middleware, WebSocket auth, audit calls, GDPR endpoints |
| `lexagent/config.py` | MODIFY | Add 18 new fields |
| `lexagent/state.py` | MODIFY | Add `security_ctx: Optional[dict]` field |
| `lexagent/cli.py` | MODIFY | `lex login`, `lex admin` subcommand group |
| `pyproject.toml` | MODIFY | Add 5 new deps |
| `docker-compose.yml` | CREATE | Caddy + LexAgent services |
| `Caddyfile` | CREATE | Auto-HTTPS reverse proxy |
| `Dockerfile` | CREATE | Multi-stage, non-root user |
| `.env.example` | MODIFY | Document all new env vars |
| `SECURITY.md` | CREATE | Vulnerability disclosure, arch diagram, known gaps |
| `tests/test_security_crypto.py` | CREATE | 5 tests |
| `tests/test_security_tokens.py` | CREATE | 5 tests |
| `tests/test_security_context.py` | CREATE | 3 tests |
| `tests/test_security_permissions.py` | CREATE | 4 tests |
| `tests/test_security_audit.py` | CREATE | 3 tests |
| `tests/test_security_gdpr.py` | CREATE | 4 tests |
| `tests/test_security_integration.py` | CREATE | 9 end-to-end tests |

---

## 14. Dependencies to Add (`pyproject.toml`)

```toml
"cryptography>=43.0",              # AES-256-GCM via hazmat + HKDF
"python-jose[cryptography]>=3.3",  # JWT encode/decode
"argon2-cffi>=23.0",               # argon2id password hashing
"slowapi>=0.1.9",                  # FastAPI rate limiting
"httpx>=0.27",                     # Async HTTP for CLI login + tests

[project.optional-dependencies]
vault      = ["hvac>=2.0"]
aws        = ["boto3>=1.34"]
enterprise = ["hvac>=2.0", "boto3>=1.34"]
```

---

## 15. Migration: Personal → Enterprise

### `lex admin migrate --to-enterprise`

```
lex admin migrate --to-enterprise \
  --encryption-key <hex-key>   \
  --admin-email admin@firm.com \
  --admin-password <pass>      \
  --firm-id sharma-associates
```

Steps:
1. Run DB migrations (v1 → v3)
2. Assign `firm_id=<slug>`, `user_id='default'` to all existing sessions/reminders
3. Encrypt all `state_json` rows without `LEXENC:` prefix
4. Encrypt `SOUL.md` + all `MEMORY.md` / `state.json` files
5. Insert admin user into `users` table
6. Write `migration.to_enterprise` to audit log
7. Print: `Migration complete. Set LEX_MULTI_TENANT=true to activate enterprise mode.`

**Non-destructive:** SQLite `ALTER TABLE ADD COLUMN DEFAULT` never modifies existing rows. `LEXENC:` prefix detection means partial encryption is safe to retry.

---

## 16. Phased Build Order — 4 × 2-Week Sprints

### Sprint 1 (Weeks 1–2): Foundation
**Goal:** All new code additive. Personal mode fully unaffected.

| Step | Files | Checkpoint |
|---|---|---|
| Add dependencies | `pyproject.toml` | `uv sync && python -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM"` |
| Fix CRIT-01, CRIT-02, CRIT-03 | `cite.py`, `draft.py`, `matter_memory.py` | `pytest tests/ -x` — all 279 pass |
| Create `security/context.py`, `crypto.py` | NEW | `pytest tests/test_security_crypto.py tests/test_security_context.py` |
| Create `security/tokens.py`, `audit.py` | NEW | `pytest tests/test_security_tokens.py tests/test_security_audit.py` |
| DB migration v3 + `TenantScope` | `session_store.py` | `pytest tests/test_memory.py` — existing tests pass |
| Add 18 config fields | `config.py` | `python -c "from lexagent.config import LexConfig; LexConfig()"` |
| **Gate** | | `pytest tests/ -x` — all 279 + new unit tests pass |

### Sprint 2 (Weeks 3–4): Auth + Authorization
**Goal:** Enterprise auth layer live. Personal mode unaffected.

| Step | Files | Checkpoint |
|---|---|---|
| Replace `_verify_token` → `get_security_context` | `control_plane.py` | `LEX_MULTI_TENANT=false lex draft "test"` works instantly |
| Auth endpoints: register, login, refresh, logout | `control_plane.py` | `curl POST /auth/login` returns JWT |
| `permissions.py` + `@require_permission` on endpoints | NEW + `control_plane.py` | `pytest tests/test_security_permissions.py` |
| WebSocket auth + concurrent limit + idle timeout | `control_plane.py` | WS without token → `close(4001)` |
| `lex login`, `lex admin` CLI | `cli.py` | `lex login --help` |
| **Gate** | | `LEX_MULTI_TENANT=true pytest tests/test_security_integration.py` |

### Sprint 3 (Weeks 5–6): Encryption + Audit + Rate Limiting
**Goal:** Data at rest encrypted. Every action audited. API protected.

| Step | Files | Checkpoint |
|---|---|---|
| Encrypt `state_json` in `save_session`/`update_session`/`get_session_state` | `session_store.py` | Round-trip test: save→read→decrypt |
| Encrypt `SOUL.md` + `MEMORY.md` + `state.json` | `soul.py`, `matter_memory.py` | `grep -l "LEXENC:" ~/.lexagent/SOUL.md` |
| Audit instrumentation: all 14 call-sites | `control_plane.py`, `session_store.py`, `nodes/research.py` | `sqlite3 sessions.db "SELECT action FROM audit_log"` |
| `slowapi` rate limiting + budget cap check | `control_plane.py`, `nodes/_llm.py` | 6th rapid request → 429 |
| **Gate** | | `pytest tests/ -x` — all tests pass incl. encrypted round-trips |

### Sprint 4 (Weeks 7–8): GDPR + Secrets + TLS + Migration
**Goal:** Production-deployable. Full compliance trail.

| Step | Files | Checkpoint |
|---|---|---|
| GDPR: `gdpr.py` + `/me/export` + `/me DELETE` + `/audit` | NEW + `control_plane.py` | `pytest tests/test_security_gdpr.py` |
| Secrets backend + `.env` file detection | `secrets.py` + startup | `LEX_SECRETS_BACKEND=env` startup check passes |
| `docker-compose.yml` + `Caddyfile` + `Dockerfile` + TLS middleware | NEW | `docker compose up` → HTTPS on port 443 |
| `lex admin migrate --to-enterprise` + `rotate-key` | `cli.py` | `lex admin migrate --help` |
| `.env.example` updates + `SECURITY.md` | ROOT | Peer review |
| Postgres `sslmode` + Qdrant `https://` validation | `graph.py`, `retriever.py` | Startup rejects insecure URLs in enterprise mode |
| **Gate** | | `pytest tests/ -v` + `LEX_MULTI_TENANT=false lex draft "test"` completes in <3s, no auth prompts |

---

## 17. Final Security Score After Implementation

| Dimension | Current | Target | Key Fix |
|---|---|---|---|
| Authentication | 🔴 1/10 | ✅ 10/10 | JWT + refresh + argon2id; WebSocket token before `accept()` |
| Authorization | 🔴 0/10 | ✅ 10/10 | `@require_permission` + matter ownership check |
| Multi-tenant isolation | 🔴 0/10 | ✅ 10/10 | `TenantScope` CM + schema migration v3 |
| Encryption at rest | 🔴 0/10 | ✅ 10/10 | AES-256-GCM + HKDF per-firm keys on all sensitive storage |
| Encryption in transit | 🟡 5/10 | ✅ 10/10 | Caddy auto-HTTPS + TLS enforcement middleware + HSTS |
| Audit logging | 🔴 0/10 | ✅ 10/10 | `audit_log` table + 14 instrumented call-sites + 7-year retention |
| Rate limiting | 🔴 0/10 | ✅ 10/10 | `slowapi` 3-tier + budget cap + brute-force protection on login |
| Secrets management | 🟠 3/10 | ✅ 10/10 | Platform env vars + Vault/AWS backends + `.env` file detection |
| CORS | 🔴 1/10 | ✅ 10/10 | Config-driven allow-list; wildcard forbidden; security headers |
| WebSocket security | 🔴 0/10 | ✅ 10/10 | Token-gated + concurrent limit + idle timeout |

**Overall: 1.0/10 → 10/10**
