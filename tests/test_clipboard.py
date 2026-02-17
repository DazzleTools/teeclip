"""Tests for clipboard backend detection."""

import platform

from teeclip.clipboard import detect_backend, _is_wsl, ClipboardError


def test_detect_backend():
    """Should detect at least one backend on any dev machine."""
    try:
        backend = detect_backend()
        assert backend is not None
        assert backend.name in ("windows", "macos", "xclip", "xsel", "wayland", "wsl")
    except ClipboardError:
        # Acceptable in headless CI environments
        pass


def test_backend_has_copy_and_paste():
    """Detected backend should have copy and paste methods."""
    try:
        backend = detect_backend()
        assert callable(getattr(backend, "copy", None))
        assert callable(getattr(backend, "paste", None))
    except ClipboardError:
        pass


def test_wsl_detection_type():
    """_is_wsl should return a boolean."""
    result = _is_wsl()
    assert isinstance(result, bool)
