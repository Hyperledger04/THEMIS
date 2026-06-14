"""
JWT access/refresh tokens and API key lifecycle.

Token architecture:
- Access token:  JWT, HS256, 15-minute TTL, contains firm_id/user_id/role/jti.
- Refresh token: opaque random bytes, 7-day TTL, stored as SHA-256 hash in DB.
- API key:       "lex_<random>" prefix, stored as argon2id hash, no expiry.

WHY argon2id for password/API-key hashing:
- Winner of Password Hashing Competition (2015).
- Memory-hard: GPU/ASIC attacks are economically infeasible.
- bcrypt is still acceptable but argon2id is the 2024 recommendation.

WHY short (15-min) access tokens with rotating refresh tokens:
- Stolen access tokens expire quickly.
- Refresh token rotation (revoke old, issue new on every use) means a stolen
  refresh token is detected on the next legitimate use — attacker and victim
  cannot both hold valid tokens simultaneously.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7
ALGORITHM = "HS256"

_API_KEY_PREFIX = "lex_"


# ---------------------------------------------------------------------------
# Password hashing (argon2id)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password with argon2id. Returns the full encoded hash string."""
    try:
        from argon2 import PasswordHasher  # type: ignore[import]
        ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)
        return ph.hash(password)
    except ImportError:
        # WHY: argon2-cffi is an optional dep; fall back to bcrypt so the
        # rest of the security module stays functional without it.
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash. Returns False on any error."""
    try:
        if hashed.startswith("$argon2"):
            from argon2 import PasswordHasher, exceptions  # type: ignore[import]
            ph = PasswordHasher()
            ph.verify(hashed, password)
            return True
        import bcrypt
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Token hashing (SHA-256 for DB storage)
# ---------------------------------------------------------------------------

def hash_token(plaintext: str) -> str:
    """SHA-256 hex digest of a token for database storage."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------

def generate_access_token(
    user_id: str,
    firm_id: str,
    role: str,
    secret: str,
    expire_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES,
) -> str:
    """
    Issue a signed JWT access token.

    Claims: sub (user_id), firm_id, role, jti (unique ID for revocation),
    iat (issued-at), exp (expiry).
    """
    try:
        from jose import jwt  # type: ignore[import]
    except ImportError:
        raise ImportError("python-jose is required: uv add 'python-jose[cryptography]'") from None

    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user_id,
        "firm_id": firm_id,
        "role": role,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> dict:
    """
    Decode and verify a JWT access token.

    Raises jose.JWTError on invalid signature, expired token, or malformed JWT.
    Callers should catch JWTError and return HTTP 401.
    """
    try:
        from jose import jwt  # type: ignore[import]
    except ImportError:
        raise ImportError("python-jose is required: uv add 'python-jose[cryptography]'") from None

    return jwt.decode(token, secret, algorithms=[ALGORITHM])


# ---------------------------------------------------------------------------
# Refresh tokens (opaque, stored hashed)
# ---------------------------------------------------------------------------

def generate_refresh_token() -> tuple[str, str]:
    """
    Generate a cryptographically random refresh token.

    Returns (plaintext, sha256_hex) — store only the hash in the database,
    return the plaintext to the client exactly once.
    """
    plaintext = secrets.token_urlsafe(48)
    return plaintext, hash_token(plaintext)


# ---------------------------------------------------------------------------
# API keys ("lex_..." prefix, stored hashed)
# ---------------------------------------------------------------------------

def generate_api_key() -> tuple[str, str]:
    """
    Generate a "lex_<random>" API key.

    Returns (plaintext, argon2id_hash) — store only the hash, return
    the plaintext to the user exactly once (they cannot retrieve it again).

    WHY argon2id for API keys: API keys are long-lived secrets used as
    HTTP bearer tokens. Argon2id hashing means a leaked database does not
    immediately expose all API keys.
    """
    plaintext = _API_KEY_PREFIX + secrets.token_urlsafe(32)
    hashed = hash_password(plaintext)  # argon2id via hash_password()
    return plaintext, hashed


def verify_api_key(plaintext: str, hashed: str) -> bool:
    """Verify a "lex_..." API key against its stored hash."""
    return verify_password(plaintext, hashed)
