"""
Cross-platform clipboard abstraction.

Auto-detects the platform and uses native OS clipboard commands:
- Windows: clip.exe (write), PowerShell Get-Clipboard (read)
- macOS: pbcopy (write), pbpaste (read)
- Linux/X11: xclip or xsel
- Linux/Wayland: wl-copy, wl-paste
- WSL: Windows clipboard tools via /mnt/c/

No Python dependencies required — uses subprocess calls to native tools.
"""

import os
import platform
import shutil
import subprocess
import sys


class ClipboardError(Exception):
    """Raised when clipboard operations fail."""
    pass


class ClipboardBackend:
    """Base class for clipboard backends."""

    name = "base"

    def copy(self, data: bytes) -> None:
        raise NotImplementedError

    def paste(self) -> bytes:
        raise NotImplementedError

    @staticmethod
    def available() -> bool:
        return False


class WindowsBackend(ClipboardBackend):
    """Windows clipboard via clip.exe and PowerShell."""

    name = "windows"

    def copy(self, data: bytes) -> None:
        try:
            proc = subprocess.run(
                ["clip.exe"],
                input=data,
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise ClipboardError(f"clip.exe failed: {proc.stderr.decode(errors='replace')}")
        except FileNotFoundError:
            raise ClipboardError("clip.exe not found")

    def paste(self) -> bytes:
        try:
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise ClipboardError(f"PowerShell Get-Clipboard failed: {proc.stderr.decode(errors='replace')}")
            return proc.stdout
        except FileNotFoundError:
            raise ClipboardError("powershell.exe not found")

    @staticmethod
    def available() -> bool:
        return platform.system() == "Windows" or _is_wsl()


class MacBackend(ClipboardBackend):
    """macOS clipboard via pbcopy/pbpaste."""

    name = "macos"

    def copy(self, data: bytes) -> None:
        try:
            proc = subprocess.run(
                ["pbcopy"],
                input=data,
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise ClipboardError(f"pbcopy failed: {proc.stderr.decode(errors='replace')}")
        except FileNotFoundError:
            raise ClipboardError("pbcopy not found")

    def paste(self) -> bytes:
        try:
            proc = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise ClipboardError(f"pbpaste failed: {proc.stderr.decode(errors='replace')}")
            return proc.stdout
        except FileNotFoundError:
            raise ClipboardError("pbpaste not found")

    @staticmethod
    def available() -> bool:
        return platform.system() == "Darwin"


class XclipBackend(ClipboardBackend):
    """Linux X11 clipboard via xclip."""

    name = "xclip"

    def copy(self, data: bytes) -> None:
        try:
            proc = subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=data,
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise ClipboardError(f"xclip failed: {proc.stderr.decode(errors='replace')}")
        except FileNotFoundError:
            raise ClipboardError("xclip not found — install with: sudo apt install xclip")

    def paste(self) -> bytes:
        try:
            proc = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise ClipboardError(f"xclip failed: {proc.stderr.decode(errors='replace')}")
            return proc.stdout
        except FileNotFoundError:
            raise ClipboardError("xclip not found — install with: sudo apt install xclip")

    @staticmethod
    def available() -> bool:
        return shutil.which("xclip") is not None


class XselBackend(ClipboardBackend):
    """Linux X11 clipboard via xsel."""

    name = "xsel"

    def copy(self, data: bytes) -> None:
        try:
            proc = subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=data,
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise ClipboardError(f"xsel failed: {proc.stderr.decode(errors='replace')}")
        except FileNotFoundError:
            raise ClipboardError("xsel not found — install with: sudo apt install xsel")

    def paste(self) -> bytes:
        try:
            proc = subprocess.run(
                ["xsel", "--clipboard", "--output"],
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise ClipboardError(f"xsel failed: {proc.stderr.decode(errors='replace')}")
            return proc.stdout
        except FileNotFoundError:
            raise ClipboardError("xsel not found — install with: sudo apt install xsel")

    @staticmethod
    def available() -> bool:
        return shutil.which("xsel") is not None


class WaylandBackend(ClipboardBackend):
    """Linux Wayland clipboard via wl-copy/wl-paste."""

    name = "wayland"

    def copy(self, data: bytes) -> None:
        try:
            proc = subprocess.run(
                ["wl-copy"],
                input=data,
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise ClipboardError(f"wl-copy failed: {proc.stderr.decode(errors='replace')}")
        except FileNotFoundError:
            raise ClipboardError("wl-copy not found — install with: sudo apt install wl-clipboard")

    def paste(self) -> bytes:
        try:
            proc = subprocess.run(
                ["wl-paste"],
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise ClipboardError(f"wl-paste failed: {proc.stderr.decode(errors='replace')}")
            return proc.stdout
        except FileNotFoundError:
            raise ClipboardError("wl-paste not found — install with: sudo apt install wl-clipboard")

    @staticmethod
    def available() -> bool:
        return os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy") is not None


class WSLBackend(ClipboardBackend):
    """WSL clipboard using Windows tools from Linux side."""

    name = "wsl"

    def _find_clip(self):
        """Find clip.exe in WSL environment."""
        for path in ["/mnt/c/Windows/System32/clip.exe", "clip.exe"]:
            if shutil.which(path) or os.path.isfile(path):
                return path
        return None

    def _find_powershell(self):
        """Find powershell.exe in WSL environment."""
        for path in ["/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe", "powershell.exe"]:
            if shutil.which(path) or os.path.isfile(path):
                return path
        return None

    def copy(self, data: bytes) -> None:
        clip = self._find_clip()
        if not clip:
            raise ClipboardError("clip.exe not found in WSL environment")
        try:
            proc = subprocess.run(
                [clip],
                input=data,
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise ClipboardError(f"clip.exe failed: {proc.stderr.decode(errors='replace')}")
        except FileNotFoundError:
            raise ClipboardError("clip.exe not found in WSL environment")

    def paste(self) -> bytes:
        ps = self._find_powershell()
        if not ps:
            raise ClipboardError("powershell.exe not found in WSL environment")
        try:
            proc = subprocess.run(
                [ps, "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                raise ClipboardError(f"PowerShell failed: {proc.stderr.decode(errors='replace')}")
            return proc.stdout
        except FileNotFoundError:
            raise ClipboardError("powershell.exe not found in WSL environment")

    @staticmethod
    def available() -> bool:
        return _is_wsl()


def _is_wsl() -> bool:
    """Detect if running inside Windows Subsystem for Linux."""
    if platform.system() != "Linux":
        return False
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except (FileNotFoundError, PermissionError):
        return False


# Backend detection order — most specific first
_BACKENDS = [
    WSLBackend,
    WindowsBackend,
    MacBackend,
    WaylandBackend,
    XclipBackend,
    XselBackend,
]


def detect_backend() -> ClipboardBackend:
    """Auto-detect and return the appropriate clipboard backend."""
    for backend_cls in _BACKENDS:
        if backend_cls.available():
            return backend_cls()
    raise ClipboardError(
        "No clipboard backend available. "
        "On Linux, install xclip (sudo apt install xclip) or wl-clipboard."
    )


def get_backend(name: str = None) -> ClipboardBackend:
    """Get a clipboard backend by name, or auto-detect."""
    if name is None:
        return detect_backend()

    for backend_cls in _BACKENDS:
        if backend_cls.name == name:
            if not backend_cls.available():
                raise ClipboardError(f"Backend '{name}' is not available on this system")
            return backend_cls()

    available_names = [b.name for b in _BACKENDS]
    raise ClipboardError(f"Unknown backend '{name}'. Available: {', '.join(available_names)}")


def copy_to_clipboard(data: bytes, backend_name: str = None) -> None:
    """Copy data to the system clipboard."""
    backend = get_backend(backend_name)
    backend.copy(data)


def paste_from_clipboard(backend_name: str = None) -> bytes:
    """Read data from the system clipboard."""
    backend = get_backend(backend_name)
    return backend.paste()
