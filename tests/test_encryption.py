"""Tests for teeclip encryption module.

These tests require the `cryptography` package. They are automatically
skipped if it is not installed.
"""

import pytest

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

pytestmark = pytest.mark.skipif(
    not HAS_CRYPTOGRAPHY,
    reason="cryptography package not installed"
)

from teeclip.encryption import (
    derive_key,
    generate_salt,
    encrypt,
    decrypt,
    is_available,
    require_available,
    encrypt_history,
    decrypt_history,
    get_or_create_salt,
    EncryptionError,
    NONCE_SIZE,
    TAG_SIZE,
    SALT_SIZE,
    KEY_SIZE,
)


# ── Availability ──────────────────────────────────────────────────────


def test_is_available():
    """is_available() returns True when cryptography is installed."""
    assert is_available() is True


def test_require_available_no_error():
    """require_available() does not raise when cryptography is installed."""
    require_available()  # should not raise


# ── Key derivation ───────────────────────────────────────────────────


def test_derive_key_length():
    """Derived key is 32 bytes (AES-256)."""
    salt = generate_salt()
    key = derive_key("test password", salt)
    assert len(key) == KEY_SIZE


def test_derive_key_deterministic():
    """Same password + salt produces the same key."""
    salt = generate_salt()
    key1 = derive_key("password", salt)
    key2 = derive_key("password", salt)
    assert key1 == key2


def test_derive_key_different_passwords():
    """Different passwords produce different keys."""
    salt = generate_salt()
    key1 = derive_key("password1", salt)
    key2 = derive_key("password2", salt)
    assert key1 != key2


def test_derive_key_different_salts():
    """Different salts produce different keys."""
    key1 = derive_key("password", generate_salt())
    key2 = derive_key("password", generate_salt())
    assert key1 != key2


# ── Salt generation ──────────────────────────────────────────────────


def test_generate_salt_length():
    """Generated salt is 16 bytes."""
    salt = generate_salt()
    assert len(salt) == SALT_SIZE


def test_generate_salt_unique():
    """Each salt generation produces unique output."""
    salts = {generate_salt() for _ in range(10)}
    assert len(salts) == 10


# ── Encrypt / Decrypt roundtrip ──────────────────────────────────────


def test_encrypt_decrypt_roundtrip():
    """Data survives encrypt → decrypt cycle."""
    salt = generate_salt()
    key = derive_key("secret", salt)
    plaintext = b"Hello, encrypted world!"

    blob = encrypt(plaintext, key)
    result = decrypt(blob, key)
    assert result == plaintext


def test_encrypt_decrypt_empty():
    """Empty data can be encrypted and decrypted."""
    key = derive_key("secret", generate_salt())
    blob = encrypt(b"", key)
    result = decrypt(blob, key)
    assert result == b""


def test_encrypt_decrypt_binary():
    """Binary data survives encrypt/decrypt."""
    key = derive_key("secret", generate_salt())
    data = bytes(range(256))
    blob = encrypt(data, key)
    assert decrypt(blob, key) == data


def test_encrypt_decrypt_large():
    """Large data (100KB) survives encrypt/decrypt."""
    key = derive_key("secret", generate_salt())
    data = b"x" * 100_000
    blob = encrypt(data, key)
    assert decrypt(blob, key) == data


def test_encrypted_blob_overhead():
    """Encrypted blob has expected overhead (nonce + tag)."""
    key = derive_key("secret", generate_salt())
    plaintext = b"test data"
    blob = encrypt(plaintext, key)
    # Overhead = 12 (nonce) + 16 (tag)
    assert len(blob) == len(plaintext) + NONCE_SIZE + TAG_SIZE


def test_decrypt_wrong_key():
    """Decryption with wrong key raises EncryptionError."""
    salt = generate_salt()
    key1 = derive_key("correct", salt)
    key2 = derive_key("wrong", salt)

    blob = encrypt(b"secret data", key1)
    with pytest.raises(EncryptionError, match="wrong password"):
        decrypt(blob, key2)


def test_decrypt_corrupted_blob():
    """Decryption of corrupted data raises EncryptionError."""
    key = derive_key("secret", generate_salt())
    blob = encrypt(b"original", key)
    # Corrupt a byte in the ciphertext
    corrupted = blob[:15] + bytes([blob[15] ^ 0xFF]) + blob[16:]
    with pytest.raises(EncryptionError):
        decrypt(corrupted, key)


def test_decrypt_too_short():
    """Blob shorter than nonce + tag raises EncryptionError."""
    key = derive_key("secret", generate_salt())
    with pytest.raises(EncryptionError, match="too short"):
        decrypt(b"short", key)


def test_each_encryption_unique():
    """Encrypting the same data twice produces different blobs (random nonce)."""
    key = derive_key("secret", generate_salt())
    blob1 = encrypt(b"same data", key)
    blob2 = encrypt(b"same data", key)
    assert blob1 != blob2  # different nonces


# ── Salt storage in HistoryStore ─────────────────────────────────────


def test_get_or_create_salt_creates(history_store):
    """get_or_create_salt creates and stores a new salt."""
    salt = get_or_create_salt(history_store)
    assert len(salt) == SALT_SIZE
    assert isinstance(salt, bytes)


def test_get_or_create_salt_stable(history_store):
    """get_or_create_salt returns the same salt on subsequent calls."""
    salt1 = get_or_create_salt(history_store)
    salt2 = get_or_create_salt(history_store)
    assert salt1 == salt2


# ── Batch encrypt/decrypt history ────────────────────────────────────


def test_encrypt_history(populated_history):
    """encrypt_history encrypts all unencrypted clips."""
    count = encrypt_history(populated_history, "test-password")
    assert count == 5

    # Verify clips are marked encrypted
    entries = populated_history.list_recent()
    assert all(e.encrypted for e in entries)


def test_encrypt_history_idempotent(populated_history):
    """Encrypting already-encrypted clips returns 0."""
    encrypt_history(populated_history, "test-password")
    count = encrypt_history(populated_history, "test-password")
    assert count == 0


def test_decrypt_history(populated_history):
    """decrypt_history restores all encrypted clips."""
    encrypt_history(populated_history, "test-password")
    count = decrypt_history(populated_history, "test-password")
    assert count == 5

    # Verify clips are unencrypted and content is correct
    entries = populated_history.list_recent()
    assert all(not e.encrypted for e in entries)

    # Verify content
    content = populated_history.get_clip(1)
    assert content == b"clip 5"


def test_decrypt_wrong_password(populated_history):
    """Decrypting with wrong password raises EncryptionError."""
    encrypt_history(populated_history, "correct-password")
    with pytest.raises(EncryptionError, match="wrong password"):
        decrypt_history(populated_history, "wrong-password")


def test_encrypt_preserves_preview(populated_history):
    """Encryption preserves the preview text (stored unencrypted)."""
    encrypt_history(populated_history, "test-password")
    entries = populated_history.list_recent()
    # Previews should still be readable
    assert entries[0].preview == "clip 5"
    assert entries[-1].preview == "clip 1"
