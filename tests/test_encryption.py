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
    decrypt_single,
    get_or_create_salt,
    get_key_provider,
    get_encryption_key,
    DPAPIKeyProvider,
    FileKeyProvider,
    PasswordKeyProvider,
    KeyProvider,
    EncryptionError,
    NONCE_SIZE,
    TAG_SIZE,
    SALT_SIZE,
    KEY_SIZE,
)
from teeclip.config import Config


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

    # Verify previews restored from decrypted content
    assert entries[0].preview == "clip 5"
    assert entries[-1].preview == "clip 1"

    # Verify content
    content = populated_history.get_clip(1)
    assert content == b"clip 5"


def test_decrypt_wrong_password(populated_history):
    """Decrypting with wrong password raises EncryptionError."""
    encrypt_history(populated_history, "correct-password")
    with pytest.raises(EncryptionError, match="wrong password"):
        decrypt_history(populated_history, "wrong-password")


def test_encrypt_blanks_preview(populated_history):
    """Encryption blanks the preview to avoid leaking plaintext."""
    encrypt_history(populated_history, "test-password")
    entries = populated_history.list_recent()
    for entry in entries:
        assert entry.preview == "(encrypted)"


# ── Key Provider: FileKeyProvider ────────────────────────────────────


def test_file_provider_roundtrip(tmp_path):
    """FileKeyProvider stores and retrieves a key."""
    provider = FileKeyProvider(tmp_path / ".keyfile")
    assert not provider.has_key()

    key = generate_salt() + generate_salt()  # 32 bytes
    provider.store_key(key)
    assert provider.has_key()
    assert provider.retrieve_key() == key


def test_file_provider_delete(tmp_path):
    """FileKeyProvider.delete_key removes the file."""
    provider = FileKeyProvider(tmp_path / ".keyfile")
    provider.store_key(b"\x00" * KEY_SIZE)
    assert provider.has_key()
    provider.delete_key()
    assert not provider.has_key()


def test_file_provider_corrupted_size(tmp_path):
    """FileKeyProvider raises on wrong-sized key file."""
    key_path = tmp_path / ".keyfile"
    key_path.write_bytes(b"too short")
    provider = FileKeyProvider(key_path)
    assert provider.has_key()
    with pytest.raises(EncryptionError, match="corrupted"):
        provider.retrieve_key()


def test_file_provider_missing_key(tmp_path):
    """FileKeyProvider raises when key file doesn't exist."""
    provider = FileKeyProvider(tmp_path / "nonexistent")
    with pytest.raises(EncryptionError, match="not found"):
        provider.retrieve_key()


# ── Key Provider: DPAPIKeyProvider (Windows only) ────────────────────


@pytest.mark.skipif(
    not (hasattr(__import__("sys"), "platform") and __import__("sys").platform == "win32"),
    reason="DPAPI only available on Windows"
)
class TestDPAPIKeyProvider:
    """Tests for Windows DPAPI key storage."""

    def test_roundtrip(self, tmp_path):
        """DPAPI protects and unprotects a key."""
        import os
        provider = DPAPIKeyProvider(tmp_path / ".keyblob")
        key = os.urandom(KEY_SIZE)
        provider.store_key(key)
        assert provider.retrieve_key() == key

    def test_has_key(self, tmp_path):
        """has_key reflects whether the blob file exists."""
        import os
        provider = DPAPIKeyProvider(tmp_path / ".keyblob")
        assert not provider.has_key()
        provider.store_key(os.urandom(KEY_SIZE))
        assert provider.has_key()

    def test_delete(self, tmp_path):
        """delete_key removes the DPAPI blob."""
        import os
        provider = DPAPIKeyProvider(tmp_path / ".keyblob")
        provider.store_key(os.urandom(KEY_SIZE))
        provider.delete_key()
        assert not provider.has_key()

    def test_missing_blob(self, tmp_path):
        """retrieve_key raises when blob file is missing."""
        provider = DPAPIKeyProvider(tmp_path / "nonexistent")
        with pytest.raises(EncryptionError, match="No DPAPI"):
            provider.retrieve_key()


# ── Key Provider: PasswordKeyProvider ────────────────────────────────


def test_password_provider_always_has_key(history_store):
    """PasswordKeyProvider.has_key is always True."""
    provider = PasswordKeyProvider(history_store)
    assert provider.has_key() is True


def test_password_provider_derive_with_password(history_store):
    """retrieve_key_with_password derives key without prompting."""
    provider = PasswordKeyProvider(history_store)
    key = provider.retrieve_key_with_password("test-password")
    assert len(key) == KEY_SIZE
    # Same password produces same key
    key2 = provider.retrieve_key_with_password("test-password")
    assert key == key2


# ── get_key_provider factory ─────────────────────────────────────────


def test_get_key_provider_password_mode(history_store):
    """auth_method='password' returns PasswordKeyProvider."""
    config = Config(security_auth_method="password")
    provider = get_key_provider(config, store=history_store)
    assert isinstance(provider, PasswordKeyProvider)


def test_get_key_provider_os_mode_returns_provider(teeclip_home):
    """auth_method='os' returns a non-password provider."""
    config = Config(security_auth_method="os")
    provider = get_key_provider(config)
    assert isinstance(provider, KeyProvider)
    assert not isinstance(provider, PasswordKeyProvider)


def test_get_key_provider_password_requires_store():
    """auth_method='password' without store raises EncryptionError."""
    config = Config(security_auth_method="password")
    with pytest.raises(EncryptionError, match="HistoryStore required"):
        get_key_provider(config, store=None)


# ── get_encryption_key ───────────────────────────────────────────────


def test_get_encryption_key_os_mode(teeclip_home):
    """OS mode auto-generates and stores a key."""
    from teeclip.history import HistoryStore

    config = Config(security_encryption="aes256", security_auth_method="os")
    store = HistoryStore(config=config)

    key = get_encryption_key(config, store)
    assert len(key) == KEY_SIZE

    # Same key on subsequent calls
    key2 = get_encryption_key(config, store)
    assert key == key2

    store.close()

    # Cleanup: delete the OS key
    provider = get_key_provider(config)
    provider.delete_key()


def test_get_encryption_key_password_mode(history_store):
    """Password mode derives key from provided password."""
    config = Config(security_auth_method="password")
    key = get_encryption_key(config, history_store, password="my-secret")
    assert len(key) == KEY_SIZE


def test_get_encryption_key_password_mode_deterministic(history_store):
    """Same password produces same key in password mode."""
    config = Config(security_auth_method="password")
    key1 = get_encryption_key(config, history_store, password="same")
    key2 = get_encryption_key(config, history_store, password="same")
    assert key1 == key2


# ── Auto-encrypt in save path ───────────────────────────────────────


def test_auto_encrypt_on_save(teeclip_home):
    """With encryption=aes256 + auth_method=os, save() encrypts."""
    from teeclip.history import HistoryStore

    config = Config(
        security_encryption="aes256",
        security_auth_method="os",
    )
    store = HistoryStore(config=config)
    store.save(b"auto-encrypted content", source="test")

    # Content should be encrypted in the database
    entry = store.list_recent(1)[0]
    assert entry.encrypted is True
    # Preview should be blanked to avoid leaking plaintext
    assert entry.preview == "(encrypted)"

    # Raw content should NOT be the plaintext
    raw = store.get_clip(1)
    assert raw != b"auto-encrypted content"
    # Should be larger (nonce + tag overhead)
    assert len(raw) > len(b"auto-encrypted content")

    # Decrypt and verify
    key = get_encryption_key(config, store)
    decrypted = decrypt(raw, key)
    assert decrypted == b"auto-encrypted content"

    store.close()
    get_key_provider(config).delete_key()


def test_no_auto_encrypt_without_config(teeclip_home):
    """Default config (encryption=none) saves plaintext."""
    from teeclip.history import HistoryStore

    config = Config()  # encryption=none
    store = HistoryStore(config=config)
    store.save(b"plaintext clip", source="test")

    entry = store.list_recent(1)[0]
    assert entry.encrypted is False
    assert store.get_clip(1) == b"plaintext clip"

    store.close()


def test_no_auto_encrypt_with_password_mode(teeclip_home):
    """auth_method=password skips auto-encrypt (can't prompt in pipe)."""
    from teeclip.history import HistoryStore

    config = Config(
        security_encryption="aes256",
        security_auth_method="password",
    )
    store = HistoryStore(config=config)
    store.save(b"password mode clip", source="test")

    entry = store.list_recent(1)[0]
    assert entry.encrypted is False
    assert store.get_clip(1) == b"password mode clip"

    store.close()


def test_auto_encrypt_dedup_uses_plaintext_hash(teeclip_home):
    """Dedup compares plaintext hashes even when auto-encrypting."""
    from teeclip.history import HistoryStore

    config = Config(
        security_encryption="aes256",
        security_auth_method="os",
    )
    store = HistoryStore(config=config)
    clip_id1 = store.save(b"duplicate content", source="test")
    clip_id2 = store.save(b"duplicate content", source="test")

    assert clip_id1 is not None
    assert clip_id2 is None  # dedup should catch it

    store.close()
    get_key_provider(config).delete_key()


# ── Config-driven encrypt/decrypt batch ─────────────────────────────


def test_encrypt_history_with_os_config(teeclip_home):
    """encrypt_history works with config-driven OS auth."""
    from teeclip.history import HistoryStore

    config = Config(
        security_encryption="aes256",
        security_auth_method="os",
    )
    store = HistoryStore(config=config)
    # Save plaintext clips (override config temporarily)
    plain_config = Config()
    plain_store = HistoryStore(config=plain_config,
                               db_path=store._db_path)
    for i in range(3):
        plain_store.save(f"clip {i}".encode(), source="test")

    # Now encrypt with OS config
    count = encrypt_history(store, config=config)
    assert count == 3

    entries = store.list_recent()
    assert all(e.encrypted for e in entries)

    # Decrypt to verify
    count = decrypt_history(store, config=config)
    assert count == 3
    assert store.get_clip(1) == b"clip 2"

    store.close()
    plain_store.close()
    get_key_provider(config).delete_key()


def test_decrypt_single_with_os_config(teeclip_home):
    """decrypt_single works with config-driven OS auth."""
    from teeclip.history import HistoryStore

    config = Config(
        security_encryption="aes256",
        security_auth_method="os",
    )
    store = HistoryStore(config=config)
    store.save(b"secret data", source="test")

    # Get the encrypted blob
    entry, raw = store.get_clip_entry(1)
    assert entry.encrypted is True

    decrypted = decrypt_single(raw, store, config=config)
    assert decrypted == b"secret data"

    store.close()
    get_key_provider(config).delete_key()
