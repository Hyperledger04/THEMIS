"""
SecurityContext — the frozen identity token threaded through every request.

WHY: A single immutable dataclass replaces the ad-hoc `auth["user_id"]` dict
scattered across control_plane.py. Passing SecurityContext to every function
that needs identity means:
  - No implicit global state
  - Easy to mock in tests (just construct a SecurityContext)
  - The is_multi_tenant flag is always co-located with user identity

TenantScope is a context manager that automatically appends `WHERE firm_id=?`
to SQL queries in enterprise mode — zero risk of cross-tenant data leaks.
In personal mode (is_multi_tenant=False) the CM is a no-op.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Generator, Optional


class Role(str, Enum):
    ADMIN = "admin"
    PARTNER = "partner"
    ASSOCIATE = "associate"
    VIEWER = "viewer"


@dataclass(frozen=True)
class SecurityContext:
    firm_id: str
    user_id: str
    role: Role
    is_multi_tenant: bool
    ip: Optional[str] = field(default=None)
    user_agent: Optional[str] = field(default=None)
    token_jti: Optional[str] = field(default=None)

    @classmethod
    def personal_default(cls) -> "SecurityContext":
        """
        Returns the personal-mode identity: single firm, admin role, no auth.

        WHY: personal_default() is injected at the control-plane level so
        every downstream function always receives a SecurityContext — no
        None checks needed anywhere in the codebase.
        """
        from themis.config import LexConfig
        cfg = LexConfig()
        return cls(
            firm_id=cfg.default_firm_id,
            user_id="default",
            role=Role.ADMIN,
            is_multi_tenant=False,
        )

    @classmethod
    def from_jwt_payload(cls, payload: dict, is_multi_tenant: bool) -> "SecurityContext":
        """Construct from a decoded JWT payload dict."""
        return cls(
            firm_id=payload["firm_id"],
            user_id=payload["sub"],
            role=Role(payload.get("role", "associate")),
            is_multi_tenant=is_multi_tenant,
            token_jti=payload.get("jti"),
        )


class TenantScope:
    """
    Context manager that wraps SQLite connections with automatic tenant filtering.

    Usage:
        scope = TenantScope(ctx, conn)
        scope.execute("SELECT * FROM sessions WHERE matter_id=?", (matter_id,))
        # In enterprise mode → appends AND firm_id=? AND user_id=? automatically
    """

    def __init__(self, ctx: SecurityContext, conn: sqlite3.Connection) -> None:
        self._ctx = ctx
        self._conn = conn

    def execute(
        self,
        sql: str,
        params: tuple = (),
        *,
        tenant_filter: bool = True,
    ) -> sqlite3.Cursor:
        """
        Execute SQL, optionally appending a firm_id + user_id WHERE clause.

        tenant_filter=False skips appending (for INSERT or cross-tenant admin
        queries — use with care).
        """
        if tenant_filter and self._ctx.is_multi_tenant:
            joiner = " AND " if "WHERE" in sql.upper() else " WHERE "
            sql = f"{sql}{joiner}firm_id=? AND user_id=?"
            params = params + (self._ctx.firm_id, self._ctx.user_id)
        return self._conn.execute(sql, params)

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Simple transaction helper — commit on success, rollback on exception."""
        try:
            yield
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise


def get_security_context(
    token: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> SecurityContext:
    """
    FastAPI dependency: resolve a SecurityContext from the Authorization header.

    Personal mode  (multi_tenant=False): returns SecurityContext.personal_default()
    Enterprise mode (multi_tenant=True): decodes JWT, raises 401/403 on failure.

    # LANGGRAPH / FastAPI: used as Depends(get_security_context) in every
    # protected endpoint. Keeps auth logic in one place, not spread across routes.
    """
    from themis.config import LexConfig
    cfg = LexConfig()

    if not cfg.multi_tenant:
        return SecurityContext.personal_default()

    if not token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Authorization token required")

    try:
        from themis.security.tokens import decode_access_token
        payload = decode_access_token(token, cfg.api_secret_key or "")
        ctx = SecurityContext.from_jwt_payload(payload, is_multi_tenant=True)
        return dataclasses.replace(ctx, ip=ip, user_agent=user_agent)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e
