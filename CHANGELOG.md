# Changelog

All notable changes to teeclip will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2026-02-17

### Added

- **OS session-based encryption**: Default `auth_method = "os"` uses DPAPI (Windows), Keychain (macOS), or Secret Service (Linux) to protect the encryption key — no password prompts needed
- **Auto-encrypt on save**: When `encryption = "aes256"` and `auth_method = "os"`, new clips are encrypted transparently during pipe operations
- **Key provider abstraction**: `KeyProvider` base class with five implementations — `DPAPIKeyProvider`, `KeychainKeyProvider`, `SecretToolKeyProvider`, `FileKeyProvider`, `PasswordKeyProvider`
- **`security.auth_method` config setting**: Choose between `"os"` (default, zero-prompt) and `"password"` (existing behavior)
- **Selective `--clear`**: `--clear 3` (single entry), `--clear 4:10` (range), `--clear 2,4:10` (combo). No argument still clears all with confirmation prompt.
- **Developer scripts**: `gh_issue_full.py` (full issue context viewer with timeline, cross-refs, sub-issues), `gh_sub_issues.py` (link/unlink GitHub sub-issues via GraphQL), `safe_move.sh` (hash-verified file move with Windows timestamp preservation)

### Fixed

- `--list-count` replaced by `--list [N]` — simplified CLI, no longer needs a separate flag
- `--no-clipboard` now correctly saves to history (was skipping history save because it was nested inside the clipboard-copy conditional)

### Security

- **HMAC-keyed hashing**: Encrypted clips use HMAC-SHA-256 (keyed with the encryption key) instead of bare SHA-256 — prevents offline plaintext fingerprinting by attackers with database access
- **Size masking**: Encrypted clips mask the size with a per-clip key-derived value — looks random without the key, recoverable with it
- **Content-type masking**: Encrypted entries store `(encrypted)` as `content_type` — prevents leaking MIME type metadata to attackers with database access
- **Encrypted metadata blob**: New `encrypted_meta` column stores content-type and other metadata as an AES-256-GCM encrypted JSON blob, making it recoverable on decrypt without leaking information at rest
- **Removed `sensitive` column**: Previously reserved but unused — its existence would signal attackers which rows to target. Per-row flags now belong inside `encrypted_meta` where they're invisible without the key
- **SQLite VACUUM**: Runs after encrypt, decrypt, and clear operations to scrub residual plaintext from free database pages

### Changed

- `--list [N]` now accepts an optional count argument, replacing `--list-count N`. Default count configurable via `history.list_count` in config
- `--list` now shows compact `[E]` marker between timestamp and preview for encrypted entries (was trailing `[encrypted]`)
- `--encrypt` / `--decrypt` no longer prompt for password when `auth_method = "os"` — uses OS-managed key instead
- `--get N` decrypts transparently with OS auth (no password prompt)
- `--list` decrypts preview text on the fly for OS auth users (preview stored as `(encrypted)` on disk)
- Existing password-based encryption preserved as opt-in via `auth_method = "password"`

## [0.2.0-alpha] - 2026-02-16

### Added

- **Clipboard history**: Piped content is automatically saved to a SQLite database (`~/.teeclip/history.db`)
- **`--list`, `-l`**: Show recent clipboard history with timestamps and previews
- **`--list-count N`**: Limit the number of entries shown by `--list`
- **`--get N`, `-g N`**: Retrieve the Nth most recent clip (1 = newest) to stdout and clipboard
- **`--clear`**: Clear all clipboard history (prompts for confirmation in interactive mode)
- **`--save`, `-s`**: Save current clipboard contents into history
- **`--config`**: Display effective configuration and config file path
- **`--no-history`**: Skip history save for the current invocation
- **`--encrypt`**: Enable AES-256-GCM encryption on all stored clips (requires `pip install teeclip[secure]`)
- **`--decrypt`**: Decrypt all encrypted clips and disable encryption
- **Configuration file**: `~/.teeclip/config.toml` for persistent settings (history size, encryption, backend, quiet mode)
- **TOML fallback parser**: Built-in minimal TOML parser for Python 3.8-3.10 (Python 3.11+ uses stdlib `tomllib`)
- **`TEECLIP_HOME` env var**: Override `~/.teeclip/` data directory (useful for testing and custom setups)
- **`[secure]` optional dependency**: `pip install teeclip[secure]` adds `cryptography>=41.0` for AES-256-GCM encryption
- **Deduplication**: Consecutive identical clips are not duplicated in history
- **FIFO eviction**: History auto-trims to `max_entries` (default 50) oldest-first

### Changed

- Default tee mode now saves piped content to history (disable with `--no-history` or `history.auto_save = false` in config)
- CLI dispatch is now priority-based: config → encrypt/decrypt → clear → list → get → save → paste → tee

## [0.1.1] - 2026-02-16

### Added

- PyPI trusted publisher workflow (`release.yml`) for automated releases via OIDC
- VS Code debug configurations for teeclip and pytest
- Platform support documentation (`docs/platform-support.md`)
- `tests/output/` directory for debug output

### Changed

- README badges updated to DazzleTools convention
- `-nc` shorthand documented in options block

## [0.1.0] - 2026-02-16

### Added

- Initial release
- Tee-style stdin pass-through with clipboard copy
- Cross-platform clipboard support: Windows, macOS, Linux (X11/Wayland), WSL
- `--paste` / `-p` to read clipboard contents to stdout
- `--backend` to force a specific clipboard backend
- `--no-clipboard` / `-nc` to skip clipboard (plain tee mode)
- `-a` / `--append` for file append mode
- `-q` / `--quiet` to suppress warnings
- File output support (like standard `tee`)

[0.2.2]: https://github.com/DazzleTools/teeclip/compare/v0.1.1...v0.2.2
[0.2.1-alpha]: https://github.com/DazzleTools/teeclip/compare/v0.2.0a1...v0.2.1a1
[0.2.0-alpha]: https://github.com/DazzleTools/teeclip/compare/v0.1.1...v0.2.0a1
[0.1.1]: https://github.com/DazzleTools/teeclip/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/DazzleTools/teeclip/releases/tag/v0.1.0
