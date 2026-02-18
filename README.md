# teeclip

[![PyPI](https://img.shields.io/pypi/v/teeclip?color=green)](https://pypi.org/project/teeclip/)
[![Release Date](https://img.shields.io/github/release-date/DazzleTools/teeclip?color=green)](https://github.com/DazzleTools/teeclip/releases)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/license-GPL%20v3-green.svg)](https://www.gnu.org/licenses/gpl-3.0.html)
[![GitHub Discussions](https://img.shields.io/github/discussions/DazzleTools/teeclip)](https://github.com/DazzleTools/teeclip/discussions)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](docs/platform-support.md)

Like Unix `tee`, but for your clipboard — with history and encryption. One command, every platform.

## Why teeclip?

Platform clipboard tools (`clip.exe`, `pbcopy`, `xclip`) are **sinks** — they consume stdin and produce no output. That means `cmd | clip | tee` doesn't work the way you'd expect: `clip` eats the data and nothing reaches `tee`.

```bash
# What you'd expect to work (but doesn't):
echo hello | clip | tee output.txt       # output.txt is EMPTY — clip ate stdin

# The workaround (but you lose stdout):
echo hello | tee output.txt | clip       # works, but you can't see the output

# With teeclip — stdout + clipboard + file, one command:
echo hello | teeclip output.txt
```

teeclip is a **filter**, not a sink. Data flows through it to stdout while being copied to the clipboard. It also keeps an encrypted local history so you can recall past clips, and it works identically on Windows, macOS, Linux, and WSL — your scripts stay portable.

| Task | Without teeclip | With teeclip |
|------|----------------|--------------|
| Copy + see output | `cmd \| tee /dev/tty \| clip` | `cmd \| teeclip` |
| Copy + file + stdout | `cmd \| tee file \| tee /dev/tty \| clip` | `cmd \| teeclip file` |
| Recall a previous copy | Not possible | `teeclip --get 2` |
| Encrypted history at rest | Not possible | Automatic with config |
| Same script, any OS | Requires platform detection | Just works |

## Features

- **Tee-style pass-through**: stdin flows to stdout unmodified while being copied to clipboard
- **Clipboard history**: Automatically saves piped content to a local SQLite database
- **History recall**: Browse (`--list`), retrieve (`--get N`), and manage (`--clear`) past clips
- **Encrypted storage**: AES-256-GCM encryption with OS-integrated key management (DPAPI, Keychain, Secret Service)
- **Cross-platform**: Windows, macOS, Linux (X11 + Wayland), and WSL — auto-detected, one command everywhere
- **Configurable**: `~/.teeclip/config.toml` for persistent settings (history size, encryption, backend)
- **Zero core dependencies**: Uses only Python stdlib and native OS clipboard commands
- **File output**: Supports writing to files just like standard `tee`
- **Paste mode**: Read clipboard contents back to stdout with `--paste`

## Installation

```bash
pip install teeclip
```

For encrypted clipboard history:

```bash
pip install teeclip[secure]
```

Or install from source:

```bash
git clone https://github.com/DazzleTools/teeclip.git
cd teeclip
pip install -e ".[secure]"
```

## Usage

```bash
# Copy command output to clipboard (and still see it)
echo "hello world" | teeclip

# Pipe a diff to clipboard for pasting into a PR comment
git diff | teeclip

# Copy to clipboard AND write to a file
cat data.csv | teeclip output.csv

# Append to a log file while copying to clipboard
make build 2>&1 | teeclip -a build.log

# Print current clipboard contents
teeclip --paste

# Pipe clipboard into another command
teeclip --paste | grep "error"

# Skip clipboard (act as plain tee)
echo test | teeclip --no-clipboard output.txt

# Browse clipboard history
teeclip --list

# Retrieve the 2nd most recent clip
teeclip --get 2

# Save clipboard to history (for content copied outside teeclip)
teeclip --save

# Show current config
teeclip --config

# Encrypt all stored clips (requires teeclip[secure])
teeclip --encrypt
```

## Platform Support

| Platform | Clipboard Tool | Notes |
|----------|---------------|-------|
| **Windows** | `clip.exe` / PowerShell | Built-in, no setup needed |
| **macOS** | `pbcopy` / `pbpaste` | Built-in, no setup needed |
| **Linux (X11)** | `xclip` or `xsel` | Install: `sudo apt install xclip` |
| **Linux (Wayland)** | `wl-copy` / `wl-paste` | Install: `sudo apt install wl-clipboard` |
| **WSL** | Windows clipboard via `/mnt/c/` | Auto-detected, no setup needed |

## Options

```
usage: teeclip [-h] [-a] [--paste] [--backend NAME] [--no-clipboard] [-q]
               [--list [N]] [--get N] [--clear [SELECTOR]]
               [--save] [--config] [--no-history] [--encrypt] [--decrypt]
               [-V] [FILE ...]

positional arguments:
  FILE              also write to FILE(s), like standard tee

options:
  -a, --append      append to files instead of overwriting
  --paste, -p       print current clipboard contents to stdout
  --backend NAME    force clipboard backend
  --no-clipboard, -nc
                    skip clipboard (act as plain tee)
  -q, --quiet       suppress warning messages
  --list [N], -l [N]
                    show recent clipboard history (default: 10)
  --get N, -g N     retrieve Nth clip from history (1 = most recent)
  --clear [SELECTOR]
                    delete history entries (all, or by index/range/combo)
  --save, -s        save current clipboard contents to history
  --config          show current configuration
  --no-history      skip history save for this invocation
  --encrypt         enable AES-256-GCM encryption (requires teeclip[secure])
  --decrypt         decrypt all stored clips
  -V, --version     show version and exit
```

For detailed documentation on all options and the config file, see [docs/configuration.md](docs/configuration.md). For database internals and encryption details, see [docs/database.md](docs/database.md).

## Contributions

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

Like the project?

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/djdarcy)

## License

teeclip, Copyright (C) 2025 Dustin Darcy 

This project is licensed under the GNU General Public License v3.0 — see [LICENSE](LICENSE) for details.
