"""Tests for JWT, refresh token, and API key helpers — lexagent/security/tokens.py."""
import time
import pytest
from lexagent.security.tokens import (
    decode_access_token,
    generate_access_token,
    generate_api_key,
    generate_refresh_token,
    hash_token,
    verify_api_key,
)

SECRET = "super-secret-key-for-tests-32chars!!"
FIRM_ID = "firm_test"
USER_ID = "user_123"
ROLE = "associate"


class TestGenerateDecodeAccessToken:
    def test_roundtrip_claims(self):
        token = generate_access_token(USER_ID, FIRM_ID, ROLE, SECRET)
        payload = decode_access_token(token, SECRET)
        assert payload["sub"] == USER_ID
        assert payload["firm_id"] == FIRM_ID
        assert payload["role"] == ROLE

    def test_contains_jti(self):
        token = generate_access_token(USER_ID, FIRM_ID, ROLE, SECRET)
        payload = decode_access_token(token, SECRET)
        assert "jti" in payload

    def test_two_tokens_have_different_jti(self):
        t1 = generate_access_token(USER_ID, FIRM_ID, ROLE, SECRET)
        t2 = generate_access_token(USER_ID, FIRM_ID, ROLE, SECRET)
        p1 = decode_access_token(t1, SECRET)
        p2 = decode_access_token(t2, SECRET)
        assert p1["jti"] != p2["jti"]

    def test_wrong_secret_raises(self):
        token = generate_access_token(USER_ID, FIRM_ID, ROLE, SECRET)
        from jose import JWTError
        with pytest.raises(JWTError):
            decode_access_token(token, "wrong-secret")

    def test_expired_token_raises(self):
        token = generate_access_token(USER_ID, FIRM_ID, ROLE, SECRET, expire_minutes=0)
        # expire_minutes=0 → exp == iat → immediately expired
        time.sleep(1)
        from jose import JWTError
        with pytest.raises(JWTError):
            decode_access_token(token, SECRET)

    def test_malformed_token_raises(self):
        from jose import JWTError
        with pytest.raises(JWTError):
            decode_access_token("not.a.token", SECRET)

    def test_different_roles(self):
        for role in ("admin", "partner", "associate", "viewer"):
            token = generate_access_token(USER_ID, FIRM_ID, role, SECRET)
            payload = decode_access_token(token, SECRET)
            assert payload["role"] == role


class TestRefreshToken:
    def test_returns_plaintext_and_hash(self):
        plaintext, hashed = generate_refresh_token()
        assert isinstance(plaintext, str)
        assert isinstance(hashed, str)
        assert len(plaintext) > 20

    def test_hash_matches_plaintext(self):
        plaintext, hashed = generate_refresh_token()
        assert hash_token(plaintext) == hashed

    def test_two_tokens_are_different(self):
        pt1, _ = generate_refresh_token()
        pt2, _ = generate_refresh_token()
        assert pt1 != pt2


class TestApiKey:
    def test_has_lex_prefix(self):
        plaintext, _ = generate_api_key()
        assert plaintext.startswith("lex_")

    def test_verify_correct_key(self):
        plaintext, hashed = generate_api_key()
        assert verify_api_key(plaintext, hashed)

    def test_reject_wrong_key(self):
        _, hashed = generate_api_key()
        assert not verify_api_key("lex_wrongkey", hashed)

    def test_two_keys_are_different(self):
        k1, _ = generate_api_key()
        k2, _ = generate_api_key()
        assert k1 != k2
