"""
Optional AES-256-GCM encryption for clipboard history.

Requires the `cryptography` package: pip install teeclip[secure]

Key management supports two auth methods (configured via [security] in config):

  auth_method = "os" (default):
      Uses OS-native key storage — DPAPI on Windows, Keychain on macOS,
      Secret Service on Linux, file-based fallback elsewhere.  A random
      AES key is generated once and protected by the OS.  No password
      prompts needed.

  auth_method = "password":
      User-supplied password with PBKDF2-HMAC-SHA256 key derivation
      (600,000 iterations).  Password is prompted via getpass, never stored.

Blob format: [12B nonce][ciphertext][16B GCM tag]
"""

import abc
import getpass
import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Availability checks
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Low-level crypto (password mode)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# AES-256-GCM encrypt / decrypt (unchanged — takes raw key bytes)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Password prompt
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Salt management (used by password mode)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Key Provider Abstraction
# ---------------------------------------------------------------------------

class KeyProvider(abc.ABC):
    """Abstract base for key storage backends.

    Each provider stores/retrieves a raw 32-byte AES key using
    a platform-specific secure storage mechanism.
    """

    name: str = "base"

    @abc.abstractmethod
    def store_key(self, key: bytes) -> None:
        """Protect and persist an AES key."""

    @abc.abstractmethod
    def retrieve_key(self) -> bytes:
        """Retrieve the stored AES key."""

    @abc.abstractmethod
    def has_key(self) -> bool:
        """Check whether a key is already stored."""

    @abc.abstractmethod
    def delete_key(self) -> None:
        """Remove the stored key."""


class DPAPIKeyProvider(KeyProvider):
    """Windows DPAPI key storage via CryptProtectData / CryptUnprotectData.

    The key is encrypted with the user's Windows login credentials and
    stored as a blob file.  Only the same user account on the same
    machine can decrypt it — no password prompt needed.
    """

    name = "dpapi"

    def __init__(self, key_path: Path):
        self._key_path = key_path

    def store_key(self, key: bytes) -> None:
        blob = _dpapi_protect(key)
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        self._key_path.write_bytes(blob)

    def retrieve_key(self) -> bytes:
        if not self._key_path.is_file():
            raise EncryptionError("No DPAPI key blob found")
        blob = self._key_path.read_bytes()
        return _dpapi_unprotect(blob)

    def has_key(self) -> bool:
        return self._key_path.is_file()

    def delete_key(self) -> None:
        if self._key_path.is_file():
            self._key_path.unlink()


class KeychainKeyProvider(KeyProvider):
    """macOS Keychain key storage via the ``security`` CLI.

    Stores the AES key as a generic password in the user's login keychain.
    """

    name = "keychain"
    _SERVICE = "teeclip"
    _ACCOUNT = "encryption-key"

    _TIMEOUT = 5  # seconds; prevents hangs if Keychain prompts block

    def store_key(self, key: bytes) -> None:
        hex_key = key.hex()
        try:
            proc = subprocess.run(
                ["security", "add-generic-password",
                 "-s", self._SERVICE, "-a", self._ACCOUNT,
                 "-w", hex_key, "-U"],
                capture_output=True, text=True, timeout=self._TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise EncryptionError(
                "Timed out storing key in macOS Keychain "
                "(Keychain may be locked)"
            )
        if proc.returncode != 0:
            raise EncryptionError(
                f"Failed to store key in Keychain: {proc.stderr.strip()}"
            )

    def retrieve_key(self) -> bytes:
        try:
            proc = subprocess.run(
                ["security", "find-generic-password",
                 "-s", self._SERVICE, "-a", self._ACCOUNT, "-w"],
                capture_output=True, text=True, timeout=self._TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise EncryptionError(
                "Timed out reading key from macOS Keychain "
                "(Keychain may be locked)"
            )
        if proc.returncode != 0:
            raise EncryptionError("Encryption key not found in macOS Keychain")
        return bytes.fromhex(proc.stdout.strip())

    def has_key(self) -> bool:
        try:
            proc = subprocess.run(
                ["security", "find-generic-password",
                 "-s", self._SERVICE, "-a", self._ACCOUNT],
                capture_output=True, timeout=self._TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return False
        return proc.returncode == 0

    def delete_key(self) -> None:
        try:
            subprocess.run(
                ["security", "delete-generic-password",
                 "-s", self._SERVICE, "-a", self._ACCOUNT],
                capture_output=True, timeout=self._TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            pass  # best-effort deletion


class SecretToolKeyProvider(KeyProvider):
    """Linux Secret Service key storage via ``secret-tool`` CLI.

    Works with GNOME Keyring, KDE Wallet, or any Secret Service D-Bus
    provider that is unlocked at login.
    """

    name = "secret-tool"
    _TIMEOUT = 5  # seconds; prevents hangs if keyring is locked

    def store_key(self, key: bytes) -> None:
        try:
            proc = subprocess.run(
                ["secret-tool", "store",
                 "--label", "teeclip encryption key",
                 "application", "teeclip",
                 "type", "encryption-key"],
                input=key.hex().encode(),
                capture_output=True, timeout=self._TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise EncryptionError(
                "Timed out storing key via secret-tool "
                "(keyring may be locked — unlock your session and retry)"
            )
        if proc.returncode != 0:
            raise EncryptionError(
                f"Failed to store key via secret-tool: "
                f"{proc.stderr.decode().strip()}"
            )

    def retrieve_key(self) -> bytes:
        try:
            proc = subprocess.run(
                ["secret-tool", "lookup",
                 "application", "teeclip",
                 "type", "encryption-key"],
                capture_output=True, timeout=self._TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise EncryptionError(
                "Timed out reading key via secret-tool "
                "(keyring may be locked — unlock your session and retry)"
            )
        if proc.returncode != 0:
            raise EncryptionError(
                "Encryption key not found in Secret Service"
            )
        return bytes.fromhex(proc.stdout.decode().strip())

    def has_key(self) -> bool:
        try:
            proc = subprocess.run(
                ["secret-tool", "lookup",
                 "application", "teeclip",
                 "type", "encryption-key"],
                capture_output=True, timeout=self._TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return False
        return proc.returncode == 0

    def delete_key(self) -> None:
        try:
            subprocess.run(
                ["secret-tool", "clear",
                 "application", "teeclip",
                 "type", "encryption-key"],
                capture_output=True, timeout=self._TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            pass  # best-effort deletion


class FileKeyProvider(KeyProvider):
    """File-based key storage with restrictive permissions.

    Fallback for environments without an OS keyring (headless Linux,
    containers, CI/CD).  The raw key bytes are stored in a file with
    0600 permissions on Unix.
    """

    name = "file"

    def __init__(self, key_path: Path):
        self._key_path = key_path

    def store_key(self, key: bytes) -> None:
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        self._key_path.write_bytes(key)
        if sys.platform != "win32":
            os.chmod(self._key_path, 0o600)

    def retrieve_key(self) -> bytes:
        if not self._key_path.is_file():
            raise EncryptionError(f"Key file not found: {self._key_path}")
        key = self._key_path.read_bytes()
        if len(key) != KEY_SIZE:
            raise EncryptionError("Key file is corrupted (wrong size)")
        return key

    def has_key(self) -> bool:
        return self._key_path.is_file()

    def delete_key(self) -> None:
        if self._key_path.is_file():
            self._key_path.unlink()


class PasswordKeyProvider(KeyProvider):
    """Password-based key derivation via PBKDF2.

    Wraps the password-prompt + PBKDF2 flow as a KeyProvider for uniform
    interface.  Keys are derived on the fly and never stored.
    """

    name = "password"

    def __init__(self, store):
        self._store = store

    def store_key(self, key: bytes) -> None:
        pass  # Password-derived keys are not persisted

    def retrieve_key(self) -> bytes:
        password = prompt_password(confirm=False)
        salt = get_or_create_salt(self._store)
        return derive_key(password, salt)

    def retrieve_key_with_password(self, password: str) -> bytes:
        """Derive key from an already-known password (no prompt)."""
        salt = get_or_create_salt(self._store)
        return derive_key(password, salt)

    def has_key(self) -> bool:
        return True  # User can always supply a password

    def delete_key(self) -> None:
        pass  # Nothing to delete


# ---------------------------------------------------------------------------
# DPAPI helpers (Windows only — imported lazily)
# ---------------------------------------------------------------------------

def _dpapi_protect(data: bytes) -> bytes:
    """Encrypt data using Windows DPAPI (CryptProtectData)."""
    import ctypes
    import ctypes.wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    input_blob = DATA_BLOB(
        len(data), ctypes.create_string_buffer(data, len(data))
    )
    output_blob = DATA_BLOB()

    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        None,   # szDataDescr
        None,   # pOptionalEntropy
        None,   # pvReserved
        None,   # pPromptStruct
        0,      # dwFlags
        ctypes.byref(output_blob),
    ):
        raise EncryptionError("DPAPI CryptProtectData failed")

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    """Decrypt data using Windows DPAPI (CryptUnprotectData)."""
    import ctypes
    import ctypes.wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    input_blob = DATA_BLOB(
        len(data), ctypes.create_string_buffer(data, len(data))
    )
    output_blob = DATA_BLOB()

    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,   # ppszDataDescr
        None,   # pOptionalEntropy
        None,   # pvReserved
        None,   # pPromptStruct
        0,      # dwFlags
        ctypes.byref(output_blob),
    ):
        raise EncryptionError("DPAPI CryptUnprotectData failed")

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


# ---------------------------------------------------------------------------
# Provider factory & key retrieval
# ---------------------------------------------------------------------------

def get_key_provider(config, store=None) -> KeyProvider:
    """Select the appropriate key provider based on config and platform.

    For auth_method="os":  DPAPI (Windows) → Keychain (macOS) →
                           secret-tool (Linux) → file fallback.
    For auth_method="password": PasswordKeyProvider.
    """
    if config.security_auth_method == "password":
        if store is None:
            raise EncryptionError("HistoryStore required for password auth")
        return PasswordKeyProvider(store)

    # OS auth mode — select based on platform
    from ._paths import get_data_dir
    data_dir = get_data_dir()

    if sys.platform == "win32":
        return DPAPIKeyProvider(data_dir / ".keyblob")

    if sys.platform == "darwin":
        return KeychainKeyProvider()

    # Linux — try secret-tool first, then file fallback
    if shutil.which("secret-tool"):
        return SecretToolKeyProvider()

    _warn("No OS keyring found — using file-based key storage")
    return FileKeyProvider(data_dir / ".keyfile")


def get_encryption_key(config, store, password: Optional[str] = None,
                       confirm_password: bool = False) -> bytes:
    """Get the AES encryption key for the active auth method.

    For OS auth: retrieves the stored key, or auto-generates and stores
    a new one on first use.  No password prompt.

    For password auth: uses the supplied password, or prompts if None.

    Args:
        config: Config instance with security_auth_method.
        store: HistoryStore for salt/metadata access.
        password: Pre-supplied password (password mode only).
        confirm_password: If True and prompting, require confirmation.
    """
    if config.security_auth_method != "password":
        # OS auth — auto-generate key on first use
        provider = get_key_provider(config)
        if not provider.has_key():
            require_available()
            key = os.urandom(KEY_SIZE)
            provider.store_key(key)
        return provider.retrieve_key()

    # Password auth
    if password is None:
        password = prompt_password(confirm=confirm_password)
    salt = get_or_create_salt(store)
    return derive_key(password, salt)


# ---------------------------------------------------------------------------
# Batch operations (support both OS and password auth)
# ---------------------------------------------------------------------------

def encrypt_history(store, password: Optional[str] = None,
                    config=None) -> int:
    """Encrypt all unencrypted clips in the history store.

    Auth resolution order:
      1. config with auth_method="os" → OS key provider (no prompt)
      2. config with auth_method="password" → password param or prompt
      3. No config → password param or prompt (backward compatible)

    Returns the number of clips encrypted.
    """
    require_available()

    if config is not None:
        key = get_encryption_key(config, store, password=password,
                                 confirm_password=True)
    elif password is not None:
        salt = get_or_create_salt(store)
        key = derive_key(password, salt)
    else:
        password = prompt_password(confirm=True)
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
            "UPDATE clips SET content = ?, encrypted = 1, "
            "preview = '(encrypted)' WHERE id = ?",
            (encrypted_content, row["id"])
        )
        count += 1

    if count > 0:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("encryption_enabled", "true")
        )
        conn.commit()

    return count


def decrypt_history(store, password: Optional[str] = None,
                    config=None) -> int:
    """Decrypt all encrypted clips in the history store.

    Returns the number of clips decrypted.
    """
    require_available()

    if config is not None:
        key = get_encryption_key(config, store, password=password)
    elif password is not None:
        salt = get_or_create_salt(store)
        key = derive_key(password, salt)
    else:
        password = prompt_password(confirm=False)
        salt = get_or_create_salt(store)
        key = derive_key(password, salt)

    conn = store._ensure_conn()
    rows = conn.execute(
        "SELECT id, content FROM clips WHERE encrypted = 1"
    ).fetchall()

    from .history import _make_preview

    count = 0
    for row in rows:
        decrypted_content = decrypt(bytes(row["content"]), key)
        preview = _make_preview(decrypted_content)
        conn.execute(
            "UPDATE clips SET content = ?, encrypted = 0, preview = ? "
            "WHERE id = ?",
            (decrypted_content, preview, row["id"])
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


def decrypt_single(blob: bytes, store, password: Optional[str] = None,
                   config=None) -> bytes:
    """Decrypt a single clip blob.

    Uses config-based auth when provided, otherwise falls back to password.
    """
    require_available()

    if config is not None:
        key = get_encryption_key(config, store, password=password)
    elif password is not None:
        salt = get_or_create_salt(store)
        key = derive_key(password, salt)
    else:
        password = prompt_password(confirm=False)
        salt = get_or_create_salt(store)
        key = derive_key(password, salt)

    return decrypt(blob, key)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _warn(msg: str) -> None:
    """Print a warning to stderr."""
    print(f"teeclip: encryption: {msg}", file=sys.stderr)
