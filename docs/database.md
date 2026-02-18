# Database Format

teeclip stores clipboard history in a SQLite database at `~/.teeclip/history.db` (or `$TEECLIP_HOME/history.db`).

This document describes the on-disk format for users who want to inspect, back up, or build tools around the history database.

## Overview

- **Engine**: SQLite 3 with WAL journal mode
- **Schema version**: tracked in the `metadata` table; checked on every open
- **Concurrency**: WAL mode allows safe concurrent reads during pipe operations
- **Encryption**: optional AES-256-GCM; when enabled, content and metadata are encrypted per-row

## Tables

### `metadata`

Key-value store for database-level state.

| Key | Value | Description |
|-----|-------|-------------|
| `schema_version` | `"2"` | Current schema version (integer as string) |
| `created_at` | ISO 8601 | When the database was first created |
| `encryption_salt` | hex string | PBKDF2 salt for password-mode encryption (only present if password mode was used) |
| `encryption_enabled` | `"true"` / `"false"` | Whether encryption is active |

Additional keys may be added by future versions. Unknown keys should be ignored.

### `clips`

Each row is one clipboard history entry.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment primary key |
| `timestamp` | TEXT | ISO 8601 UTC timestamp of when the clip was saved |
| `content_type` | TEXT | MIME type (default `text/plain`). Set to `(encrypted)` for encrypted rows |
| `content` | BLOB | Raw content bytes, or AES-256-GCM ciphertext for encrypted rows |
| `size` | INTEGER | Content size in bytes. XOR-masked when encrypted (see below) |
| `hash` | TEXT | SHA-256 hex digest for deduplication. HMAC-SHA-256 when encrypted |
| `preview` | TEXT | Truncated plaintext preview for display. `(encrypted)` for encrypted rows |
| `source` | TEXT | Where the clip came from: `pipe`, `clipboard`, or `save` |
| `encrypted` | INTEGER | `0` = plaintext, `1` = encrypted |
| `encrypted_meta` | BLOB | AES-256-GCM encrypted JSON metadata (see below). `NULL` for plaintext rows |

### Indexes

| Name | Definition | Purpose |
|------|-----------|---------|
| `idx_clips_hash` | `clips(hash)` | Fast deduplication lookup |
| `idx_clips_timestamp` | `clips(timestamp DESC)` | Fast history listing |

## Encryption Details

When encryption is enabled, each clip row is transformed before storage. The goal is to prevent an attacker with database access from learning anything about the content — including its type, size, or whether two clips contain the same data.

### What changes per row

| Column | Plaintext row | Encrypted row |
|--------|--------------|---------------|
| `content` | Raw bytes | `[12B nonce][ciphertext][16B GCM tag]` |
| `content_type` | MIME string (e.g. `text/plain`) | `(encrypted)` |
| `size` | Actual byte count | XOR-masked value (see below) |
| `hash` | `SHA-256(content)` | `HMAC-SHA-256(key, content)` |
| `preview` | First ~80 chars | `(encrypted)` |
| `encrypted` | `0` | `1` |
| `encrypted_meta` | `NULL` | AES-256-GCM encrypted JSON blob |

### `encrypted_meta` blob

Holds metadata that would leak information if stored in the clear. Currently contains:

```json
{"content_type": "text/plain"}
```

The blob is encrypted with the same key as `content`, using its own random nonce. It is extensible — future versions may add fields (e.g. `encoding`, `dimensions` for images) without requiring schema changes.

For pre-v0.2.2 encrypted rows that lack `encrypted_meta`, teeclip falls back to `text/plain` on decrypt.

### Size masking

The `size` column is XOR-masked so that an attacker cannot determine content length or compare relative sizes across rows:

```
stored_size = real_size XOR mask
mask = first 4 bytes of HMAC-SHA-256(key, content_hash)
```

XOR is its own inverse, so unmasking uses the same operation with the same key and hash.

### Hash (HMAC)

Encrypted rows use HMAC-SHA-256 keyed with the encryption key instead of bare SHA-256. This prevents offline plaintext fingerprinting — an attacker cannot hash a guessed plaintext and compare it to stored hashes without possessing the key. Deduplication still works because consecutive saves compute the same HMAC.

## FIFO Eviction

After each insert, rows exceeding `max_entries` (default 50) are deleted oldest-first:

```sql
DELETE FROM clips WHERE id NOT IN (
    SELECT id FROM clips ORDER BY id DESC LIMIT ?
)
```

## Deduplication

Before inserting, the hash of the new content is compared to the most recent entry only. If they match, the insert is skipped. This prevents consecutive duplicates without scanning the full history.

## Inspecting the Database

```bash
# Open with sqlite3 CLI
sqlite3 ~/.teeclip/history.db

# Show schema
.schema

# List recent clips (metadata only)
SELECT id, timestamp, content_type, size, encrypted, preview
FROM clips ORDER BY id DESC LIMIT 10;

# Check metadata
SELECT * FROM metadata;
```

A helper script is included for development use:

```bash
python tests/one-offs/inspect_history_db.py          # show 5 most recent
python tests/one-offs/inspect_history_db.py --all     # show all rows
python tests/one-offs/inspect_history_db.py --count 3  # show N rows
```

## Backing Up

The database is a single file. To back up:

```bash
cp ~/.teeclip/history.db ~/.teeclip/history.db.bak
```

If teeclip is actively writing (WAL mode), use SQLite's backup API or `.backup` command for a consistent copy:

```bash
sqlite3 ~/.teeclip/history.db ".backup '/path/to/backup.db'"
```

## Schema History

| Version | Introduced | Changes |
|---------|-----------|---------|
| 2 | v0.2.2 | Added `encrypted_meta` BLOB column. Removed `sensitive` column. Auto-migrates from v1. |
| 1 | v0.2.0-alpha | Initial schema: `clips` table with encryption support, `metadata` table |
