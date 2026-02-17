# Configuration & CLI Reference

teeclip can be configured via a TOML config file and/or CLI flags. CLI flags override config file settings for the current invocation.

## Config File

**Location**: `~/.teeclip/config.toml`

Override the data directory with the `TEECLIP_HOME` environment variable:

```bash
export TEECLIP_HOME=/custom/path    # uses /custom/path/config.toml
```

The config file is not created automatically — teeclip uses sensible defaults when no file exists. Create it manually or use the settings below as a starting point.

### Full Default Config

```toml
[history]
enabled = true          # Save piped content to clipboard history
max_entries = 50        # Maximum clips to keep (FIFO eviction)
auto_save = true        # Auto-save during pipe operations
preview_length = 80     # Characters shown in --list preview

[clipboard]
backend = ""            # Auto-detect (or: windows, macos, xclip, xsel, wayland, wsl)

[output]
quiet = false           # Suppress warning messages

[security]
encryption = "none"     # "none" or "aes256" (requires teeclip[secure])
```

### Section Reference

#### `[history]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Master switch for clipboard history |
| `max_entries` | int | `50` | Maximum number of clips to retain. Oldest are evicted first |
| `auto_save` | bool | `true` | Automatically save piped content to history |
| `preview_length` | int | `80` | Maximum characters for the preview shown in `--list` |

#### `[clipboard]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `backend` | string | `""` (auto) | Force a specific clipboard backend. Empty string = auto-detect |

Available backends: `windows`, `macos`, `xclip`, `xsel`, `wayland`, `wsl`

#### `[output]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `quiet` | bool | `false` | Suppress non-critical warning messages |

#### `[security]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `encryption` | string | `"none"` | Encryption mode. `"none"` or `"aes256"` |

To use encryption, install the secure extra:

```bash
pip install teeclip[secure]
```

---

## CLI Reference

### Tee Mode (default)

```bash
command | teeclip [OPTIONS] [FILE ...]
```

Reads stdin, writes to stdout, copies to clipboard, and saves to history.

| Flag | Short | Description |
|------|-------|-------------|
| `FILE` | | Also write to file(s), like standard `tee` |
| `--append` | `-a` | Append to files instead of overwriting |
| `--no-clipboard` | `-nc` | Skip clipboard copy (plain tee) |
| `--no-history` | | Skip history save for this invocation |
| `--backend NAME` | | Force clipboard backend |
| `--quiet` | `-q` | Suppress warnings |

### Clipboard Operations

| Flag | Short | Description |
|------|-------|-------------|
| `--paste` | `-p` | Print current clipboard contents to stdout |
| `--save` | `-s` | Capture current clipboard contents into history (for content copied outside teeclip) |

### History Operations

| Flag | Short | Description |
|------|-------|-------------|
| `--list` | `-l` | Show recent clipboard history |
| `--list-count N` | | Limit entries shown (default: 10) |
| `--get N` | `-g N` | Retrieve Nth most recent clip (1 = newest). Outputs to stdout and copies to clipboard |
| `--clear` | | Delete all clipboard history. Prompts for confirmation when interactive |

### Configuration

| Flag | Description |
|------|-------------|
| `--config` | Show effective configuration and file path |

### Encryption

| Flag | Description |
|------|-------------|
| `--encrypt` | Encrypt all stored clips with AES-256-GCM. Prompts for a password (with confirmation) |
| `--decrypt` | Decrypt all encrypted clips. Prompts for password |

Encryption requires `pip install teeclip[secure]` (adds the `cryptography` package).

**How it works**:

- `--encrypt` prompts for a password, derives an AES-256 key via PBKDF2 (600,000 iterations), and encrypts all unencrypted clips in-place
- `--decrypt` reverses the process, restoring plaintext
- `--get N` on an encrypted clip prompts for the password to decrypt before output
- `--list` preview text is always readable (stored separately from encrypted content)
- The encryption salt is stored in the database metadata — one salt per database

### Info

| Flag | Short | Description |
|------|-------|-------------|
| `--version` | `-V` | Show version and exit |
| `--help` | `-h` | Show help message |

---

## CLI-to-Config Mapping

Several CLI flags correspond to config file settings. CLI flags take precedence for the current invocation.

| CLI Flag | Config Key | Section |
|----------|-----------|---------|
| `--quiet` / `-q` | `quiet` | `[output]` |
| `--backend NAME` | `backend` | `[clipboard]` |
| `--no-history` | `auto_save` | `[history]` |

Flags like `--list`, `--get`, `--clear`, `--encrypt`, and `--decrypt` are commands, not persistent settings.

---

## Data Files

All data is stored under `~/.teeclip/` (or `$TEECLIP_HOME`):

| File | Description |
|------|-------------|
| `config.toml` | Configuration (user-created) |
| `history.db` | SQLite database for clipboard history (auto-created on first save) |

### History Database Schema

The SQLite database uses WAL journal mode for safe concurrent reads. Schema version is tracked in a `metadata` table for future migrations.

Each clip stores:

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment primary key |
| `timestamp` | TEXT | ISO 8601 UTC timestamp |
| `content_type` | TEXT | MIME type (default: `text/plain`) |
| `content` | BLOB | Raw content (or encrypted blob) |
| `size` | INTEGER | Content size in bytes |
| `hash` | TEXT | SHA-256 hex digest (for deduplication) |
| `preview` | TEXT | Truncated text preview for `--list` |
| `source` | TEXT | Origin: `pipe`, `clipboard`, `test` |
| `encrypted` | INTEGER | 1 if content is encrypted |
| `sensitive` | INTEGER | Reserved for future auto-expiry |
