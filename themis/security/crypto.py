"""
AES-256-GCM encryption with HKDF per-firm key derivation.

WHY AES-256-GCM over Fernet (AES-128-CBC + HMAC):
- GCM is Authenticated Encryption with Associated Data (AEAD) — authentication
  is built into the cipher, no separate HMAC needed.
- 256-bit keys vs 128-bit keys.
- HKDF per-firm key derivation: a leaked key for firm_a cannot decrypt firm_b
  data — each firm's key is derived separately from the master key.
- Hardware-accelerated via AES-NI on every modern CPU (no perceptible overhead).

Wire format: b"LEXENC:" + nonce(12 bytes) + ciphertext+GCM-tag(variable)
The "LEXENC:" prefix is a cheap sentinel — plaintext bytes can be detected
and passed through unchanged, enabling safe incremental migration.

Personal mode (encryption_key=None): passthrough — nothing encrypted.
Enterprise mode (encryption_key set): all sensitive storage encrypted.
"""
from __future__ import annotations

import os
from typing import Optional

_SENTINEL = b"LEXENC:"
_NONCE_SIZE = 12  # 96-bit nonce recommended by NIST SP 800-38D for GCM


def _derive_key(master_key_hex: str, firm_id: str) -> bytes:
    """
    Derive a 32-byte AES key from the master key and firm_id using HKDF-SHA256.

    WHY: Per-firm key derivation means a key leak for one firm does not
    compromise any other firm's data — each firm_id produces a different key.
    """
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    master_bytes = bytes.fromhex(master_key_hex)
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=None,
        info=firm_id.encode(),
    )
    return hkdf.derive(master_bytes)


def encrypt_bytes(
    plaintext: bytes,
    master_key_hex: str,
    firm_id: str = "default",
) -> bytes:
    """
    Encrypt plaintext with AES-256-GCM.

    Returns LEXENC: + nonce(12) + ciphertext+tag.
    Already-encrypted bytes (starting with LEXENC:) are returned as-is.
    """
    if plaintext.startswith(_SENTINEL):
        return plaintext  # idempotent

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _derive_key(master_key_hex, firm_id)
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return _SENTINEL + nonce + ciphertext


def decrypt_bytes(
    ciphertext: bytes,
    master_key_hex: str,
    firm_id: str = "default",
) -> bytes:
    """
    Decrypt AES-256-GCM ciphertext.

    Bytes without the LEXENC: prefix are returned unchanged (plaintext
    passthrough for backward compatibility during migration).
    """
    if not ciphertext.startswith(_SENTINEL):
        return ciphertext  # plaintext passthrough

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _derive_key(master_key_hex, firm_id)
    payload = ciphertext[len(_SENTINEL):]
    nonce = payload[:_NONCE_SIZE]
    ct = payload[_NONCE_SIZE:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)


def encrypt_str(
    plaintext: str,
    master_key_hex: str,
    firm_id: str = "default",
) -> str:
    """Encrypt a UTF-8 string and return a hex-encoded ciphertext string."""
    return encrypt_bytes(plaintext.encode(), master_key_hex, firm_id).hex()


def decrypt_str(
    ciphertext_hex: str,
    master_key_hex: str,
    firm_id: str = "default",
) -> str:
    """Decrypt a hex-encoded ciphertext string back to UTF-8."""
    raw = bytes.fromhex(ciphertext_hex)
    return decrypt_bytes(raw, master_key_hex, firm_id).decode()


def get_master_key(cfg=None) -> Optional[str]:
    """
    Return the master encryption key from config, or None if not set.

    WHY: Called at every encrypt/decrypt site so the key is always read
    from the current config — supports key rotation without restart.
    """
    if cfg is None:
        from themis.config import LexConfig
        cfg = LexConfig()
    return getattr(cfg, "encryption_key", None)


def is_encryption_enabled(cfg=None) -> bool:
    """Returns True when a master key is configured and multi_tenant is True."""
    if cfg is None:
        from themis.config import LexConfig
        cfg = LexConfig()
    return bool(getattr(cfg, "encryption_key", None)) and bool(getattr(cfg, "multi_tenant", False))
