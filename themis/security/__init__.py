"""
Themis security package.

Provides authentication, authorisation, encryption, audit logging, rate
limiting, permissions, and GDPR helpers for both personal and enterprise
multi-tenant deployments.

Personal mode (LEX_MULTI_TENANT=false):  all checks bypassed; zero friction.
Enterprise mode (LEX_MULTI_TENANT=true): every check enforced; 10/10 score.

# WHY: A single env-var gate (multi_tenant) means the personal CLI path never
# touches auth or encryption code — no latency, no config required.
"""
from themis.security.context import Role, SecurityContext, TenantScope
from themis.security.permissions import require_permission

__all__ = [
    "Role",
    "SecurityContext",
    "TenantScope",
    "require_permission",
]
