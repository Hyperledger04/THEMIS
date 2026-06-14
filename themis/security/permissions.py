"""
Role-based permission matrix and FastAPI dependency decorator.

WHY: A flat permission string like "draft.create" is more legible than
a boolean field per-action and easier to extend — adding a new permission
means adding a string to the matrix, not a new column in the DB.

Personal mode: @require_permission is a no-op (all permissions granted).
Enterprise mode: role checked against PERMISSION_MATRIX; 403 if not present.
"""
from __future__ import annotations

from functools import wraps
from typing import Callable

PERMISSION_MATRIX: dict[str, set[str]] = {
    "admin": {
        "matter.*", "draft.*", "research.run", "document.*",
        "user.*", "token.*", "audit.read", "key.rotate",
        "firm.settings", "gdpr.*",
    },
    "partner": {
        "matter.create", "matter.read", "draft.*", "research.run",
        "document.*", "user.read", "token.create", "audit.read", "gdpr.export",
    },
    "associate": {
        "matter.create", "matter.read", "draft.*", "research.run",
        "document.*", "token.create",
    },
    "viewer": {
        "matter.read", "draft.read", "document.read",
    },
}


def _has_permission(role: str, permission: str) -> bool:
    """
    Check whether `role` grants `permission`.

    Supports wildcard matching: "draft.*" grants "draft.create", "draft.read", etc.
    """
    granted = PERMISSION_MATRIX.get(role, set())
    if permission in granted:
        return True
    # Check wildcard: "draft.*" covers "draft.create"
    namespace = permission.split(".")[0]
    return f"{namespace}.*" in granted


def require_permission(permission: str) -> Callable:
    """
    FastAPI dependency factory: raise 403 if the resolved SecurityContext
    does not have the given permission.

    Personal mode (is_multi_tenant=False): always passes — no overhead.

    Usage:
        @app.post("/api/v1/matters/{matter_id}/message")
        async def send_message(
            ctx: SecurityContext = Depends(get_security_context),
            _: None = Depends(require_permission("draft.create")),
        ): ...
    """
    def dependency(ctx=None):
        # ctx is injected by FastAPI via Depends(get_security_context)
        if ctx is None or not ctx.is_multi_tenant:
            return  # personal mode — all access granted

        if not _has_permission(ctx.role.value, permission):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail=f"Role '{ctx.role.value}' does not have permission '{permission}'",
            )

    return dependency


def check_permission(role: str, permission: str) -> bool:
    """
    Programmatic permission check (non-HTTP contexts — CLI, scheduler).

    Returns True if role grants permission, False otherwise.
    """
    return _has_permission(role, permission)
