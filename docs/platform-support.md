# Platform Support

teeclip auto-detects your platform and uses the appropriate native clipboard tool. No configuration needed in most cases.

## Supported Platforms

### Windows

- **Clipboard tool**: `clip.exe` (write), PowerShell `Get-Clipboard` (read)
- **Requirements**: None — both tools ship with Windows
- **Notes**: `clip.exe` doesn't support reading the clipboard, so paste mode uses PowerShell. UTF-16LE encoding from PowerShell pipelines may need attention in some edge cases.

### macOS

- **Clipboard tool**: `pbcopy` (write), `pbpaste` (read)
- **Requirements**: None — ships with macOS
- **Notes**: Fully supported out of the box.

### Linux (X11)

- **Clipboard tool**: `xclip` or `xsel`
- **Requirements**: Install one of:
  ```bash
  sudo apt install xclip    # Debian/Ubuntu
  sudo dnf install xclip    # Fedora
  sudo pacman -S xclip      # Arch
  ```
- **Notes**: `xclip` is preferred when both are available. teeclip uses the `CLIPBOARD` selection (not `PRIMARY`).

### Linux (Wayland)

- **Clipboard tool**: `wl-copy` / `wl-paste`
- **Requirements**: Install:
  ```bash
  sudo apt install wl-clipboard    # Debian/Ubuntu
  sudo dnf install wl-clipboard    # Fedora
  sudo pacman -S wl-clipboard      # Arch
  ```
- **Notes**: Auto-detected via `WAYLAND_DISPLAY` environment variable.

### WSL (Windows Subsystem for Linux)

- **Clipboard tool**: Windows `clip.exe` and `powershell.exe` via `/mnt/c/`
- **Requirements**: None — uses the host Windows clipboard tools
- **Notes**: Auto-detected via `/proc/version`. Uses the Windows clipboard, not an X11/Wayland one, so clipboard content is shared with your Windows desktop.

## Backend Selection

teeclip auto-detects backends in this order:

1. **WSL** — if running inside WSL
2. **Windows** — if on native Windows
3. **macOS** — if on Darwin
4. **Wayland** — if `WAYLAND_DISPLAY` is set and `wl-copy` is available
5. **xclip** — if available
6. **xsel** — if available

To force a specific backend:
```bash
echo "hello" | teeclip --backend xclip
```

## Help Wanted

Testing across all platforms is a challenge for a solo maintainer. If you use teeclip on any of these environments and run into issues (or can confirm it works), please open an issue or start a discussion:

- **Linux distros**: Fedora, Arch, openSUSE, NixOS, etc.
- **Wayland compositors**: Sway, Hyprland, KDE Plasma (Wayland session)
- **Older macOS versions**: Pre-Ventura
- **WSL1 vs WSL2**: Both should work but WSL1 has different interop behavior
- **Remote/headless**: SSH sessions, Docker containers, CI environments

[Open an issue](https://github.com/DazzleTools/teeclip/issues) or [start a discussion](https://github.com/DazzleTools/teeclip/discussions)
