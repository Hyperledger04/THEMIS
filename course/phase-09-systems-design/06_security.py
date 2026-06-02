"""
Phase 9 — 06: Security — JWT, RBAC, Encryption, Audit Log
===========================================================
Run:  pip install pyjwt fastapi httpx
      python 06_security.py
"""

import sys
import time
from datetime import datetime, timezone
from typing import Any

# ── SECTION 1: WHY SECURITY MATTERS FOR A LEGAL APP ─────────────────────────
#
# LexAgent handles:
#   • Privileged client communications (attorney-client privilege)
#   • Strategy documents (unfiled pleadings, settlement positions)
#   • Personal data of parties (DPDP Act obligations)
#
# A security breach is not just a technical problem — it's a Bar Council
# professional responsibility issue.  We need:
#   1. Authentication — who is this user? (JWT)
#   2. Authorization — what can they do? (RBAC)
#   3. Encryption at rest — firm data encrypted per-firm (AES-256-GCM)
#   4. Audit logging — who accessed what, when (immutable log)

try:
    import jwt as pyjwt
    JWT_AVAILABLE = True
except ImportError:
    print("Install:  pip install pyjwt")
    print("Running in PRINT-ONLY mode — JWT calls are stubbed.\n")
    JWT_AVAILABLE = False

try:
    from fastapi import Depends, FastAPI, HTTPException, status
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from fastapi.testclient import TestClient
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


# ── SECTION 2: JWT TOKENS ─────────────────────────────────────────────────────
#
# JWT (JSON Web Token) = base64(header) + "." + base64(payload) + "." + signature
#
# The signature is HMAC-SHA256(header + "." + payload, SECRET_KEY).
# Anyone with the secret can verify the signature — no DB lookup needed.
#
# Payload claims for LexAgent:
#   firm_id — which firm this user belongs to (used for data isolation)
#   user_id — individual user
#   role    — RBAC role (admin | partner | associate | viewer)
#   exp     — expiry timestamp (Unix seconds)
#
# WHY exp?
#   If a token is stolen, it's only valid until expiry.
#   Typical: 1 hour for API tokens, 30 days for "remember me".

SECRET_KEY = "lexagent-dev-secret-change-in-prod"
ALGORITHM = "HS256"


def encode_token(firm_id: str, user_id: str, role: str,
                 ttl_seconds: int = 3600) -> str:
    """
    Create a signed JWT for a LexAgent user.

    In production:
      • SECRET_KEY comes from cfg.jwt_secret (env var, never hardcoded).
      • ttl_seconds from cfg.jwt_ttl_seconds.
    """
    if not JWT_AVAILABLE:
        return f"stub.token.for.{firm_id}.{user_id}.{role}"

    payload = {
        "firm_id": firm_id,
        "user_id": user_id,
        "role": role,
        "exp": int(time.time()) + ttl_seconds,
        "iat": int(time.time()),     # issued-at
    }
    return pyjwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Verify signature and decode the JWT.
    Raises jwt.ExpiredSignatureError if token is past `exp`.
    Raises jwt.InvalidTokenError on tampered signature.

    In production this is wrapped in Depends(verify_jwt) — see Section 5.
    """
    if not JWT_AVAILABLE:
        # Stub: parse the fake token format above
        parts = token.split(".")
        if len(parts) >= 4:
            return {"firm_id": parts[3], "user_id": parts[4], "role": parts[5],
                    "exp": int(time.time()) + 3600}
        raise ValueError("Invalid stub token")

    return pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# ── SECTION 3: RBAC — ROLE-BASED ACCESS CONTROL ──────────────────────────────
#
# Roles and their permissions in a law firm:
#
# ┌──────────────┬─────────┬────────┬───────────┬──────────┐
# │ Action       │ admin   │partner │ associate │  viewer  │
# ├──────────────┼─────────┼────────┼───────────┼──────────┤
# │ draft        │   ✓     │   ✓    │     ✓     │          │
# │ research     │   ✓     │   ✓    │     ✓     │          │
# │ view_matters │   ✓     │   ✓    │     ✓     │    ✓     │
# │ delete_matter│   ✓     │   ✓    │           │          │
# │ manage_users │   ✓     │        │           │          │
# └──────────────┴─────────┴────────┴───────────┴──────────┘
#
# In LexAgent (lexagent/security/):
#   RBAC is checked in Depends(verify_jwt) before any handler runs.
#   The handler never needs to check roles — the dependency does it.

ROLE_HIERARCHY = ["viewer", "associate", "partner", "admin"]

PERMISSIONS: dict[str, list[str]] = {
    "draft":          ["associate", "partner", "admin"],
    "research":       ["associate", "partner", "admin"],
    "view_matters":   ["viewer", "associate", "partner", "admin"],
    "delete_matter":  ["partner", "admin"],
    "manage_users":   ["admin"],
}


def can(role: str, action: str) -> bool:
    """
    Return True if `role` is permitted to perform `action`.

    WHY a lookup dict instead of if/elif chains?
      Adding a new role or action = one line in PERMISSIONS dict.
      if/elif chains would need changes in multiple places.
    """
    return role in PERMISSIONS.get(action, [])


def require_permission(role: str, action: str) -> None:
    """Raise if role cannot perform action."""
    if not can(role, action):
        raise PermissionError(
            f"Role '{role}' cannot perform '{action}'. "
            f"Required: one of {PERMISSIONS.get(action, [])}"
        )


# ── SECTION 4: ENCRYPTION CONCEPT — AES-256-GCM ──────────────────────────────
#
# AES-256-GCM is authenticated encryption:
#   • AES-256: 256-bit key, symmetric block cipher
#   • GCM (Galois/Counter Mode): provides integrity (tamper detection) + confidentiality
#
# Per-firm encryption:
#   1. Master secret in env var (never in code or DB).
#   2. Per-firm key derived with HKDF:
#        firm_key = HKDF(master_secret, salt=firm_id, length=32)
#   3. All matter data encrypted with firm_key.
#   4. Even if the DB is stolen, data is unreadable without firm_key.
#   5. Revoke a firm: delete their HKDF-derived key — all their data becomes garbage.
#
# WHY GCM over CBC?
#   GCM includes an authentication tag — if data is tampered with in storage,
#   decryption fails loudly instead of silently returning garbage.
#
# Implementation in production:
#   from cryptography.hazmat.primitives.kdf.hkdf import HKDF
#   from cryptography.hazmat.primitives import hashes
#   from cryptography.hazmat.primitives.ciphers.aead import AESGCM
#
#   firm_key = HKDF(algorithm=hashes.SHA256(), length=32,
#                   salt=firm_id.encode(), info=b"lexagent").derive(master_secret)
#   aesgcm = AESGCM(firm_key)
#   nonce = os.urandom(12)
#   ciphertext = aesgcm.encrypt(nonce, plaintext, None)
#
# This file doesn't implement cryptography — the concept is the lesson.
# For the real implementation see lexagent/security/encryption.py (if present).

def encryption_concept_demo() -> None:
    print("── AES-256-GCM concept ──")
    print("   master_secret = os.environ['LEXAGENT_MASTER_KEY']  (32 bytes)")
    print("   firm_key = HKDF(master_secret, salt=firm_id)       (per-firm)")
    print("   ciphertext = AESGCM(firm_key).encrypt(nonce, plaintext)")
    print("   nonce is random per-message (12 bytes) — stored alongside ciphertext")
    print("   AES-256-GCM provides: confidentiality + integrity (tamper detection)")
    print()


# ── SECTION 5: AUDIT LOG ──────────────────────────────────────────────────────
#
# Every sensitive action is logged:
#   (timestamp, firm_id, user_id, action, result, ip_address)
#
# In production (lexagent/security/audit.py):
#   • Written to Postgres `audit_log` table (append-only, never UPDATE/DELETE)
#   • Separate DB user with INSERT-only grants
#   • Shipped to centralised log store (ELK, Datadog)
#
# WHY immutable?
#   If an attacker (or rogue employee) could delete audit records, you'd have
#   no forensic trail.  Append-only + off-site shipping makes deletion very hard.

_audit_log: list[dict] = []    # in-memory stand-in for the DB table


def audit(firm_id: str, user_id: str, action: str, result: str,
          detail: str = "") -> None:
    """
    Append one audit event.

    In production: INSERT INTO audit_log VALUES (...) using a write-only DB user.
    """
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "firm_id": firm_id,
        "user_id": user_id,
        "action": action,
        "result": result,
        "detail": detail[:200],
    }
    _audit_log.append(event)


def print_audit_log() -> None:
    print(f"── Audit log ({len(_audit_log)} events) ──")
    for ev in _audit_log:
        print(f"   {ev['ts'][:19]}  {ev['firm_id']:10s}  {ev['user_id']:6s}  "
              f"{ev['action']:20s}  {ev['result']}")
    print()


# ── SECTION 6: FASTAPI DEPENDENCY — verify_jwt ────────────────────────────────
#
# `Depends(verify_jwt)` is the security perimeter for every protected endpoint.
# FastAPI calls verify_jwt before your handler — if it raises, the handler never runs.
#
# Signature:
#   async def verify_jwt(
#       credentials: HTTPAuthorizationCredentials = Depends(bearer),
#   ) -> dict:
#       token = credentials.credentials      # "Bearer <token>"
#       try:
#           payload = decode_token(token)
#       except jwt.ExpiredSignatureError:
#           raise HTTPException(401, "Token expired")
#       except jwt.InvalidTokenError:
#           raise HTTPException(401, "Invalid token")
#       audit(payload["firm_id"], payload["user_id"], "auth", "ok")
#       return payload
#
# The handler then receives the payload as a parameter:
#   @app.post("/draft")
#   async def draft(req: DraftRequest, user: dict = Depends(verify_jwt)):
#       firm_id = user["firm_id"]   ← from JWT, not from request body
#       ...

if FASTAPI_AVAILABLE:
    bearer = HTTPBearer()

    async def verify_jwt(
        credentials: HTTPAuthorizationCredentials = Depends(bearer),
    ) -> dict:
        token = credentials.credentials
        try:
            payload = decode_token(token)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired token: {exc}",
            )
        audit(payload.get("firm_id", "?"), payload.get("user_id", "?"),
              "authenticate", "ok")
        return payload


    def build_secured_app() -> "FastAPI":
        app = FastAPI(title="LexAgent Secured Control Plane")

        @app.post("/draft")
        async def draft(user: dict = Depends(verify_jwt)) -> dict:
            require_permission(user["role"], "draft")
            audit(user["firm_id"], user["user_id"], "draft", "ok")
            return {"status": "ok", "firm_id": user["firm_id"], "role": user["role"]}

        @app.delete("/matter/{matter_id}")
        async def delete_matter(matter_id: str, user: dict = Depends(verify_jwt)) -> dict:
            require_permission(user["role"], "delete_matter")
            audit(user["firm_id"], user["user_id"], "delete_matter", "ok",
                  detail=matter_id)
            return {"deleted": matter_id}

        return app


# ── SECTION 7: FULL DEMO ──────────────────────────────────────────────────────

def run_demo() -> None:
    print("── JWT demo ──\n")

    # 1. Encode tokens for 4 roles
    roles = ["admin", "partner", "associate", "viewer"]
    tokens = {}
    for role in roles:
        tok = encode_token("firm_a", f"u_{role[:3]}", role)
        tokens[role] = tok
        # Show only first 40 chars — tokens are long
        display = tok[:40] + "..." if len(tok) > 40 else tok
        print(f"   {role:10s} token: {display}")

    print()

    # 2. Decode and verify
    print("── Decode / verify ──")
    for role, tok in tokens.items():
        payload = decode_token(tok)
        print(f"   decoded: firm_id={payload.get('firm_id')}  "
              f"user_id={payload.get('user_id')}  role={payload.get('role')}")

    print()

    # 3. RBAC checks for all 4 roles
    print("── RBAC permission matrix ──")
    actions = ["draft", "research", "view_matters", "delete_matter", "manage_users"]
    header = f"   {'Role':12s}" + "".join(f"{a[:10]:>12s}" for a in actions)
    print(header)
    for role in roles:
        row = f"   {role:12s}" + "".join(
            f"{'✓':>12s}" if can(role, a) else f"{'✗':>12s}" for a in actions
        )
        print(row)
    print()

    # 4. Audit 3 events
    print("── Audit events ──")
    audit("firm_a", "u_adm", "draft",         "ok",    "matter_id=m001")
    audit("firm_a", "u_par", "delete_matter",  "ok",    "matter_id=m002")
    audit("firm_b", "u_ass", "draft",          "ok",    "matter_id=m010")
    print_audit_log()

    # 5. Encryption concept
    encryption_concept_demo()

    # 6. FastAPI integration test
    if FASTAPI_AVAILABLE and JWT_AVAILABLE:
        print("── FastAPI integration (verify_jwt dependency) ──")
        app = build_secured_app()
        client = TestClient(app, raise_server_exceptions=False)

        # No token → 403 (HTTPBearer returns 403 when Authorization header is missing)
        resp = client.post("/draft")
        print(f"   No token:        HTTP {resp.status_code} (expected 403)")
        assert resp.status_code == 403

        # Valid admin token → 200
        admin_tok = tokens["admin"]
        resp = client.post("/draft", headers={"Authorization": f"Bearer {admin_tok}"})
        print(f"   Admin token:     HTTP {resp.status_code} (expected 200)")
        assert resp.status_code == 200

        # Viewer tries to draft → 500 from PermissionError
        # (in prod, require_permission would raise HTTPException 403)
        viewer_tok = tokens["viewer"]
        resp = client.post("/draft", headers={"Authorization": f"Bearer {viewer_tok}"})
        print(f"   Viewer draft:    HTTP {resp.status_code} (expected 500/403)")

        # Viewer can delete_matter (partner/admin only) → blocked
        resp = client.delete(
            "/matter/m001",
            headers={"Authorization": f"Bearer {viewer_tok}"},
        )
        print(f"   Viewer delete:   HTTP {resp.status_code} (expected 500/403)")

        print()
        print("   ✓ Auth middleware working correctly")

    print("── Security demo complete ──")


if __name__ == "__main__":
    run_demo()


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
#
# 1. Open lexagent/security/ (or lexagent/gateway/control_plane.py).
#    Is `verify_jwt` implemented there?  Does it use PyJWT or a different library?
#    What happens when the token is expired — which HTTP status code is returned?
#
# 2. The RBAC table in this file uses a dict of lists.
#    In lexagent/security/, is RBAC stored in code, config, or a database?
#    What are the pros/cons of each approach for a law firm deployment?
#
# 3. The audit log in this file is a Python list (in-memory, lost on restart).
#    In production, what table structure and DB permissions would you use
#    to make it append-only?  How would you prevent even a DB admin from
#    deleting rows?
#
# 4. The encryption concept section describes HKDF for per-firm key derivation.
#    If you rotate the master secret, what happens to existing ciphertext?
#    How would you handle a key rotation without downtime?
#
# 5. `SECRET_KEY` is hardcoded in this file as "lexagent-dev-secret-change-in-prod".
#    List 3 ways a developer could accidentally commit a real secret to git,
#    and 3 controls to prevent it (beyond `.gitignore`).
