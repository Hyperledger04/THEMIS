"""Tests for AES-256-GCM encryption — themis/security/crypto.py."""
import os
import pytest
from themis.security.crypto import (
    _derive_key,
    decrypt_bytes,
    decrypt_str,
    encrypt_bytes,
    encrypt_str,
    get_master_key,
    is_encryption_enabled,
)

MASTER_KEY = os.urandom(32).hex()
FIRM_A = "firm_alpha"
FIRM_B = "firm_beta"


class TestDeriveKey:
    def test_returns_32_bytes(self):
        assert len(_derive_key(MASTER_KEY, FIRM_A)) == 32

    def test_deterministic(self):
        assert _derive_key(MASTER_KEY, FIRM_A) == _derive_key(MASTER_KEY, FIRM_A)

    def test_different_firm_yields_different_key(self):
        assert _derive_key(MASTER_KEY, FIRM_A) != _derive_key(MASTER_KEY, FIRM_B)

    def test_different_master_yields_different_key(self):
        other = os.urandom(32).hex()
        assert _derive_key(MASTER_KEY, FIRM_A) != _derive_key(other, FIRM_A)


class TestEncryptDecryptBytes:
    def test_roundtrip(self):
        pt = b"Themis NI Act Section 138 complaint"
        ct = encrypt_bytes(pt, MASTER_KEY, FIRM_A)
        assert decrypt_bytes(ct, MASTER_KEY, FIRM_A) == pt

    def test_ciphertext_has_sentinel(self):
        assert encrypt_bytes(b"x", MASTER_KEY, FIRM_A).startswith(b"LEXENC:")

    def test_encrypt_idempotent(self):
        ct = encrypt_bytes(b"data", MASTER_KEY, FIRM_A)
        assert encrypt_bytes(ct, MASTER_KEY, FIRM_A) == ct

    def test_decrypt_passthrough_for_plaintext(self):
        raw = b"no sentinel here"
        assert decrypt_bytes(raw, MASTER_KEY, FIRM_A) == raw

    def test_nonce_randomness(self):
        ct1 = encrypt_bytes(b"same", MASTER_KEY, FIRM_A)
        ct2 = encrypt_bytes(b"same", MASTER_KEY, FIRM_A)
        assert ct1 != ct2  # different random nonces each call

    def test_cross_firm_decrypt_raises(self):
        ct = encrypt_bytes(b"secret", MASTER_KEY, FIRM_A)
        with pytest.raises(Exception):
            decrypt_bytes(ct, MASTER_KEY, FIRM_B)

    def test_empty_bytes_roundtrip(self):
        assert decrypt_bytes(encrypt_bytes(b"", MASTER_KEY, FIRM_A), MASTER_KEY, FIRM_A) == b""


class TestEncryptDecryptStr:
    def test_roundtrip(self):
        s = "वादी बनाम प्रतिवादी 2024"
        assert decrypt_str(encrypt_str(s, MASTER_KEY, FIRM_A), MASTER_KEY, FIRM_A) == s

    def test_returns_valid_hex(self):
        result = encrypt_str("hello", MASTER_KEY, FIRM_A)
        bytes.fromhex(result)  # raises ValueError if not valid hex

    def test_ascii_roundtrip(self):
        s = "Cheque dishonoured on 14 March 2026."
        assert decrypt_str(encrypt_str(s, MASTER_KEY, FIRM_A), MASTER_KEY, FIRM_A) == s


class TestGetMasterKey:
    def test_returns_none_when_not_configured(self):
        class _Cfg:
            encryption_key = None
        assert get_master_key(_Cfg()) is None

    def test_returns_key_when_configured(self):
        class _Cfg:
            encryption_key = MASTER_KEY
        assert get_master_key(_Cfg()) == MASTER_KEY


class TestIsEncryptionEnabled:
    def test_false_when_no_key(self):
        class _Cfg:
            encryption_key = None
            multi_tenant = True
        assert not is_encryption_enabled(_Cfg())

    def test_false_when_not_multi_tenant(self):
        class _Cfg:
            encryption_key = MASTER_KEY
            multi_tenant = False
        assert not is_encryption_enabled(_Cfg())

    def test_true_when_key_and_multi_tenant(self):
        class _Cfg:
            encryption_key = MASTER_KEY
            multi_tenant = True
        assert is_encryption_enabled(_Cfg())
