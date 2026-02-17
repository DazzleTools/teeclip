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
auth_method = "os"      # "os" (default, zero-prompt) or "password"
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
| `auth_method` | string | `"os"` | Key management method. `"os"` or `"password"` |

**Auth methods**:

- **`"os"` (default)**: Uses your OS login session to protect the encryption key. No password prompts needed — if you're logged in, you can access your clips. Uses DPAPI on Windows, Keychain on macOS, Secret Service (GNOME Keyring / KDE Wallet) on Linux, with a file-based fallback for headless environments.
- **`"password"`**: Prompts for a password each time encryption or decryption is needed. Uses PBKDF2-HMAC-SHA256 (600,000 iterations) to derive the key.

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
| `--clear [SELECTOR]` | | Delete history entries. No argument clears all (prompts for confirmation). Accepts indices (`3`), ranges (`4:10`), or combos (`2,4:10`) |

### Configuration

| Flag | Description |
|------|-------------|
| `--config` | Show effective configuration and file path |

### Encryption

| Flag | Description |
|------|-------------|
| `--encrypt` | Encrypt all stored clips with AES-256-GCM |
| `--decrypt` | Decrypt all encrypted clips |

Encryption requires `pip install teeclip[secure]` (adds the `cryptography` package).

**How it works** (depends on `auth_method` in config):

With `auth_method = "os"` (default):

- `--encrypt` generates an AES-256 key, protects it with your OS credentials, and encrypts all clips — **no password prompt**
- `--decrypt` retrieves the OS-protected key and decrypts all clips — **no password prompt**
- `--get N` on an encrypted clip decrypts transparently
- New clips are auto-encrypted when `encryption = "aes256"` is in your config
- The key is tied to your OS user account and machine

With `auth_method = "password"`:

- `--encrypt` prompts for a password, derives an AES-256 key via PBKDF2, and encrypts all clips
- `--decrypt` prompts for the password and decrypts
- `--get N` prompts for the password to decrypt
- New clips are **not** auto-encrypted (can't prompt during pipe operations)

**Common to both modes**:

- `--list` preview text is always readable (stored separately from encrypted content)
- AES-256-GCM encryption with random 12-byte nonces
- The encryption salt is stored in the database metadata

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
| `.keyblob` | DPAPI-protected encryption key (Windows, auto-created when encryption enabled) |
| `.keyfile` | Raw encryption key file with 0600 permissions (Linux fallback, auto-created) |

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
