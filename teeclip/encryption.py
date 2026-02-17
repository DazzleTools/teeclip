"""
Optional AES-256-GCM encryption for clipboard history.

Requires the `cryptography` package: pip install teeclip[secure]

Key derivation uses PBKDF2-HMAC-SHA256 (stdlib) with 600,000 iterations.
Blob format: [12B nonce][ciphertext][16B GCM tag]
Salt is stored in the history database metadata table.
"""

import getpass
import hashlib
import os
import sys
from typing import Optional


# 28 bytes overhead per encrypted blob (12 nonce + 16 tag)
NONCE_SIZE = 12
TAG_SIZE = 16
SALT_SIZE = 16
PBKDF2_ITERATIONS = 600_000
KEY_SIZE = 32  # AES-256


class EncryptionError(Exception):
    """Raised when encryption/decryption operations fail."""
    pass


def is_available() -> bool:
    """Check if the cryptography package is installed."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
        return True
    except ImportError:
        return False


def require_available():
    """Raise EncryptionError if cryptography is not installed."""
    if not is_available():
        raise EncryptionError(
            "Encryption requires the 'cryptography' package.\n"
            "Install it with: pip install teeclip[secure]"
        )


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from password using PBKDF2."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations=PBKDF2_ITERATIONS,
        dklen=KEY_SIZE,
    )


def generate_salt() -> bytes:
    """Generate a random 16-byte salt."""
    return os.urandom(SALT_SIZE)


def encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt data with AES-256-GCM.

    Returns: [12B nonce][ciphertext][16B tag]
    """
    require_available()
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    # AESGCM.encrypt returns ciphertext + tag concatenated
    ct_with_tag = aesgcm.encrypt(nonce, data, None)
    return nonce + ct_with_tag


def decrypt(blob: bytes, key: bytes) -> bytes:
    """Decrypt AES-256-GCM blob.

    Expects: [12B nonce][ciphertext][16B tag]
    """
    require_available()
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if len(blob) < NONCE_SIZE + TAG_SIZE:
        raise EncryptionError("Encrypted blob is too short")

    nonce = blob[:NONCE_SIZE]
    ct_with_tag = blob[NONCE_SIZE:]

    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ct_with_tag, None)
    except Exception:
        raise EncryptionError(
            "Decryption failed — wrong password or corrupted data"
        )


def prompt_password(confirm: bool = False) -> str:
    """Prompt user for password via getpass.

    Args:
        confirm: If True, ask for password twice and verify match.

    Returns:
        The password string.
    """
    password = getpass.getpass("Encryption password: ")
    if not password:
        raise EncryptionError("Password cannot be empty")

    if confirm:
        password2 = getpass.getpass("Confirm password: ")
        if password != password2:
            raise EncryptionError("Passwords do not match")

    return password


def get_or_create_salt(store) -> bytes:
    """Get existing salt from store metadata, or create and save a new one.

    Args:
        store: HistoryStore instance (must have an open connection).

    Returns:
        16-byte salt.
    """
    conn = store._ensure_conn()
    row = conn.execute(
        "SELECT value FROM metadata WHERE key = 'encryption_salt'"
    ).fetchone()

    if row:
        return bytes.fromhex(row["value"])

    salt = generate_salt()
    conn.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
        ("encryption_salt", salt.hex())
    )
    conn.commit()
    return salt


def encrypt_history(store, password: str) -> int:
    """Encrypt all unencrypted clips in the history store.

    Returns the number of clips encrypted.
    """
    require_available()
    salt = get_or_create_salt(store)
    key = derive_key(password, salt)

    conn = store._ensure_conn()
    rows = conn.execute(
        "SELECT id, content FROM clips WHERE encrypted = 0"
    ).fetchall()

    count = 0
    for row in rows:
        encrypted_content = encrypt(bytes(row["content"]), key)
        conn.execute(
            "UPDATE clips SET content = ?, encrypted = 1 WHERE id = ?",
            (encrypted_content, row["id"])
        )
        count += 1

    if count > 0:
        # Mark encryption as enabled in metadata
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("encryption_enabled", "true")
        )
        conn.commit()

    return count


def decrypt_history(store, password: str) -> int:
    """Decrypt all encrypted clips in the history store.

    Returns the number of clips decrypted.
    """
    require_available()
    salt = get_or_create_salt(store)
    key = derive_key(password, salt)

    conn = store._ensure_conn()
    rows = conn.execute(
        "SELECT id, content FROM clips WHERE encrypted = 1"
    ).fetchall()

    count = 0
    for row in rows:
        decrypted_content = decrypt(bytes(row["content"]), key)
        conn.execute(
            "UPDATE clips SET content = ?, encrypted = 0 WHERE id = ?",
            (decrypted_content, row["id"])
        )
        count += 1

    if count > 0:
        # Check if any encrypted clips remain
        remaining = conn.execute(
            "SELECT COUNT(*) as cnt FROM clips WHERE encrypted = 1"
        ).fetchone()["cnt"]
        if remaining == 0:
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("encryption_enabled", "false")
            )
        conn.commit()

    return count


def decrypt_single(blob: bytes, store, password: Optional[str] = None) -> bytes:
    """Decrypt a single clip blob, prompting for password if needed.

    Args:
        blob: The encrypted content blob.
        store: HistoryStore instance for salt retrieval.
        password: Pre-supplied password, or None to prompt.

    Returns:
        Decrypted bytes.
    """
    require_available()

    if password is None:
        password = prompt_password(confirm=False)

    salt = get_or_create_salt(store)
    key = derive_key(password, salt)
    return decrypt(blob, key)
