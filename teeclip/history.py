"""
SQLite-based clipboard history store.

Stores clipboard entries in ~/.teeclip/history.db with FIFO rotation,
deduplication, and optional encryption support.
"""

import hashlib
import hmac as hmac_mod
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from ._paths import get_history_db_path, ensure_data_dir
from .config import Config

_CURRENT_SCHEMA_VERSION = 1


class HistoryError(Exception):
    """Raised when history operations fail."""
    pass


class HistoryEntry:
    """A single clipboard history entry (metadata only, no content)."""

    __slots__ = ("id", "timestamp", "content_type", "size", "hash",
                 "preview", "source", "encrypted", "sensitive")

    def __init__(self, row: sqlite3.Row):
        self.id = row["id"]
        self.timestamp = row["timestamp"]
        self.content_type = row["content_type"]
        self.size = row["size"]
        self.hash = row["hash"]
        self.preview = row["preview"]
        self.source = row["source"]
        self.encrypted = bool(row["encrypted"])
        self.sensitive = bool(row["sensitive"])


class HistoryStore:
    """SQLite-backed clipboard history store."""

    def __init__(self, config: Optional[Config] = None, db_path: Optional[Path] = None):
        self._config = config or Config()
        self._db_path = db_path or get_history_db_path()
        self._conn = None

    def _ensure_conn(self) -> sqlite3.Connection:
        """Open database connection and initialize schema if needed."""
        if self._conn is not None:
            return self._conn

        # Create data directory if this is a write path
        ensure_data_dir()

        self._conn = sqlite3.connect(str(self._db_path), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        """Create tables if they don't exist, run migrations."""
        conn = self._conn

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        version = self._get_schema_version()

        if version < 1:
            self._migrate_to_v1()

    def _get_schema_version(self) -> int:
        """Read current schema version from metadata table."""
        try:
            row = self._conn.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
            return int(row["value"]) if row else 0
        except (sqlite3.OperationalError, TypeError, ValueError):
            return 0

    def _migrate_to_v1(self) -> None:
        """Create initial schema (version 1)."""
        conn = self._conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS clips (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'text/plain',
                content     BLOB NOT NULL,
                size        INTEGER NOT NULL,
                hash        TEXT NOT NULL,
                preview     TEXT NOT NULL DEFAULT '',
                source      TEXT NOT NULL DEFAULT 'pipe',
                encrypted   INTEGER NOT NULL DEFAULT 0,
                sensitive   INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_clips_hash
                ON clips(hash);
            CREATE INDEX IF NOT EXISTS idx_clips_timestamp
                ON clips(timestamp DESC);
        """)

        # Set schema version
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("schema_version", str(_CURRENT_SCHEMA_VERSION))
        )
        conn.execute(
            "INSERT OR IGNORE INTO metadata (key, value) VALUES (?, ?)",
            ("created_at", datetime.now(timezone.utc).isoformat())
        )
        conn.commit()

    def save(self, content: bytes, content_type: str = "text/plain",
             source: str = "pipe") -> Optional[int]:
        """Save content to history.

        When encryption is configured with OS auth, content is encrypted
        transparently before storage.  Preview and hash are computed from
        the plaintext so that --list and dedup still work.

        Returns the clip ID, or None if skipped (duplicate).
        """
        conn = self._ensure_conn()

        # Start with bare SHA-256 hash (used when not encrypting)
        content_hash = hashlib.sha256(content).hexdigest()
        preview = _make_preview(content, self._config.history_preview_length)
        timestamp = datetime.now(timezone.utc).isoformat()
        stored_size = len(content)

        # Auto-encrypt if configured with OS auth (no prompt needed)
        save_content = content
        encrypted = 0
        if (self._config.security_encryption == "aes256"
                and self._config.security_auth_method != "password"):
            try:
                from .encryption import (
                    is_available, get_encryption_key,
                    encrypt as aes_encrypt,
                )
                if is_available():
                    key = get_encryption_key(self._config, self)
                    save_content = aes_encrypt(content, key)
                    encrypted = 1
                    preview = "(encrypted)"
                    # HMAC hash with encryption key — prevents offline
                    # plaintext verification by attackers with db access
                    content_hash = hmac_mod.new(
                        key, content, 'sha256'
                    ).hexdigest()
                    # XOR-mask the size so it looks random without
                    # the key but is recoverable with it
                    stored_size = _mask_size(
                        len(content), key, content_hash
                    )
            except Exception as e:
                _warn(f"auto-encrypt failed, saving plaintext: {e}")

        # Dedup: skip if hash matches most recent entry
        last = conn.execute(
            "SELECT hash FROM clips ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if last and last["hash"] == content_hash:
            return None

        cursor = conn.execute(
            """INSERT INTO clips
               (timestamp, content_type, content, size, hash, preview,
                source, encrypted)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, content_type, save_content, stored_size,
             content_hash, preview, source, encrypted)
        )
        clip_id = cursor.lastrowid

        # FIFO eviction
        self._evict_oldest(self._config.history_max_entries)

        conn.commit()
        return clip_id

    def list_recent(self, limit: int = 10) -> List[HistoryEntry]:
        """Return recent history entries (metadata only, no content)."""
        conn = self._ensure_conn()
        rows = conn.execute(
            """SELECT id, timestamp, content_type, size, hash,
                      preview, source, encrypted, sensitive
               FROM clips ORDER BY id DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [HistoryEntry(row) for row in rows]

    def get_clip(self, index: int) -> Optional[bytes]:
        """Retrieve clip content by 1-based index (1 = most recent).

        Returns the raw content bytes, or None if index is out of range.
        """
        if index < 1:
            return None

        conn = self._ensure_conn()
        row = conn.execute(
            "SELECT content FROM clips ORDER BY id DESC LIMIT 1 OFFSET ?",
            (index - 1,)
        ).fetchone()

        return bytes(row["content"]) if row else None

    def get_clip_entry(self, index: int) -> Optional[Tuple[HistoryEntry, bytes]]:
        """Retrieve full clip entry (metadata + content) by 1-based index.

        Returns (entry, content) tuple, or None if index is out of range.
        """
        if index < 1:
            return None

        conn = self._ensure_conn()
        row = conn.execute(
            """SELECT id, timestamp, content_type, content, size, hash,
                      preview, source, encrypted, sensitive
               FROM clips ORDER BY id DESC LIMIT 1 OFFSET ?""",
            (index - 1,)
        ).fetchone()

        if not row:
            return None

        content = bytes(row["content"])
        entry = HistoryEntry(row)
        return (entry, content)

    def clear(self) -> int:
        """Delete all clips. Returns the number of deleted entries."""
        conn = self._ensure_conn()
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM clips")
        count = cursor.fetchone()["cnt"]
        conn.execute("DELETE FROM clips")
        conn.commit()
        if count > 0:
            try:
                conn.execute("VACUUM")
            except sqlite3.OperationalError:
                pass  # best-effort; scrubs residual data from free pages
        return count

    def delete_by_indices(self, indices: list) -> int:
        """Delete clips by 1-based display indices (1 = most recent).

        Maps display indices to database IDs using ORDER BY id DESC,
        matching the ordering used by --list and --get.

        Returns the number of clips actually deleted.
        """
        if not indices:
            return 0

        conn = self._ensure_conn()

        # Get all clip IDs in display order (newest first)
        rows = conn.execute(
            "SELECT id FROM clips ORDER BY id DESC"
        ).fetchall()

        total = len(rows)
        # Map 1-based indices to database IDs
        ids_to_delete = []
        for idx in indices:
            if 1 <= idx <= total:
                ids_to_delete.append(rows[idx - 1]["id"])

        if not ids_to_delete:
            return 0

        placeholders = ",".join("?" * len(ids_to_delete))
        conn.execute(
            f"DELETE FROM clips WHERE id IN ({placeholders})",
            ids_to_delete,
        )
        conn.commit()

        if ids_to_delete:
            try:
                conn.execute("VACUUM")
            except sqlite3.OperationalError:
                pass  # best-effort

        return len(ids_to_delete)

    def count(self) -> int:
        """Return the total number of clips in history."""
        conn = self._ensure_conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM clips").fetchone()
        return row["cnt"]

    def _evict_oldest(self, max_entries: int) -> None:
        """Delete oldest entries exceeding max_entries."""
        if max_entries <= 0:
            return
        self._conn.execute(
            """DELETE FROM clips WHERE id NOT IN (
                   SELECT id FROM clips ORDER BY id DESC LIMIT ?
               )""",
            (max_entries,)
        )

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _make_preview(data: bytes, max_len: int = 80) -> str:
    """Generate a short preview string for display in --list."""
    if not data:
        return "(empty)"

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        hex_preview = data[:20].hex()
        return f"(binary, {len(data)} bytes) {hex_preview}"

    # Collapse whitespace to single line
    preview = " ".join(text.split())
    if len(preview) > max_len:
        preview = preview[:max_len - 3] + "..."
    return preview


def _mask_size(real_size: int, key: bytes, content_hash: str) -> int:
    """XOR-mask a size value using a per-clip key-derived mask.

    Without the key the stored integer looks arbitrary; with the key,
    XOR again to recover the real size.  Each clip gets a unique mask
    derived from its HMAC hash, so relative sizes are not preserved.
    """
    mask = int.from_bytes(
        hmac_mod.new(key, content_hash.encode(), 'sha256').digest()[:4],
        'big',
    )
    return real_size ^ mask


def _unmask_size(stored_size: int, key: bytes, content_hash: str) -> int:
    """Recover the real size from a masked value (XOR is its own inverse)."""
    return _mask_size(stored_size, key, content_hash)


def _warn(msg: str) -> None:
    """Print a warning to stderr."""
    print(f"teeclip: history: {msg}", file=sys.stderr)
