"""
Symmetric encryption for private message content (server-side encryption,
spec §9.1/§5.3 — not E2E; the algorithm itself is our choice, ABF-118).

AES-256-GCM: authenticated encryption, so tampering with a stored row is
detected on decrypt rather than silently producing garbage.

Storage format (base64 of the concatenation, so it fits in a Text column):
    nonce (12 bytes) || ciphertext+tag

`key_version` exists on DirectMessage so a future key rotation only needs a
new branch here — encrypt_message() always writes CURRENT_KEY_VERSION.
"""

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

CURRENT_KEY_VERSION = 1

_NONCE_LENGTH = 12


def _key_for_version(key_version: int) -> bytes:
    """
    Derive the 32-byte AES-256 key for a given key_version.

    MESSAGE_ENCRYPTION_KEY is an arbitrary secret string (see config.py) —
    hashing it guarantees exactly 32 bytes regardless of the string's own
    length or format.
    """
    if key_version != CURRENT_KEY_VERSION:
        raise ValueError(f"Unknown message encryption key_version: {key_version}")
    return hashlib.sha256(settings.MESSAGE_ENCRYPTION_KEY.encode()).digest()


def encrypt_message(plaintext: str) -> tuple[str, int]:
    """Encrypt message content. Returns (base64 ciphertext, key_version)."""
    key = _key_for_version(CURRENT_KEY_VERSION)
    nonce = os.urandom(_NONCE_LENGTH)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii"), CURRENT_KEY_VERSION


def decrypt_message(stored_content: str, key_version: int) -> str:
    """Decrypt message content previously produced by encrypt_message()."""
    key = _key_for_version(key_version)
    raw = base64.b64decode(stored_content)
    nonce, ciphertext = raw[:_NONCE_LENGTH], raw[_NONCE_LENGTH:]
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
