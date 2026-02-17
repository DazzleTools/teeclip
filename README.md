# teeclip

[![PyPI version](https://badge.fury.io/py/teeclip.svg)](https://badge.fury.io/py/teeclip)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

Like Unix `tee`, but for your clipboard. Pipe any command's output to both stdout and the system clipboard simultaneously.

## Overview

`teeclip` reads from stdin and writes to stdout — just like `tee` — but instead of (or in addition to) writing to a file, it copies the output to your system clipboard. No more `| pbcopy`, `| xclip`, or `| clip.exe` — one tool, every platform.

## Features

- **Tee-style pass-through**: stdin flows to stdout unmodified while being copied to clipboard
- **Cross-platform**: Windows, macOS, Linux (X11 + Wayland), and WSL — auto-detected
- **Zero dependencies**: Uses only Python stdlib and native OS clipboard commands
- **File output too**: Supports writing to files just like standard `tee`
- **Paste mode**: Read clipboard contents back to stdout with `--paste`

## Installation

```bash
pip install teeclip
```

Or install from source:

```bash
git clone https://github.com/DazzleTools/teeclip.git
cd teeclip
pip install -e .
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
usage: teeclip [-h] [-a] [--paste] [--backend NAME] [--no-clipboard] [-q] [-V] [FILE ...]

positional arguments:
  FILE              also write to FILE(s), like standard tee

options:
  -a, --append      append to files instead of overwriting
  --paste, -p       print current clipboard contents to stdout
  --backend NAME    force clipboard backend (windows, macos, xclip, xsel, wayland, wsl)
  --no-clipboard    skip clipboard (act as plain tee)
  -q, --quiet       suppress warning messages
  -V, --version     show version and exit
```

## Contributions

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

Like the project?

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/djdarcy)

## License

teeclip, Copyright (C) 2025 Dustin Darcy 

This project is licensed under the GNU General Public License v3.0 — see [LICENSE](LICENSE) for details.
