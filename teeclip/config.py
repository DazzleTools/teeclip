"""
Configuration management for teeclip.

Loads settings from ~/.teeclip/config.toml (or TEECLIP_HOME/config.toml),
falls back to defaults when the file doesn't exist, and supports
CLI flag overrides via Config.with_overrides().
"""

import dataclasses
import sys
from pathlib import Path
from typing import Optional

from ._paths import get_config_path


# Default configuration values
_DEFAULTS = {
    "history": {
        "enabled": True,
        "max_entries": 50,
        "auto_save": True,
        "preview_length": 80,
        "list_count": 10,
    },
    "clipboard": {
        "backend": "",
    },
    "output": {
        "quiet": False,
    },
    "security": {
        "encryption": "none",
        "auth_method": "os",
    },
}


@dataclasses.dataclass(frozen=True)
class Config:
    """Immutable configuration object."""

    history_enabled: bool = True
    history_max_entries: int = 50
    history_auto_save: bool = True
    history_preview_length: int = 80
    history_list_count: int = 10
    clipboard_backend: str = ""
    output_quiet: bool = False
    security_encryption: str = "none"
    security_auth_method: str = "os"

    def with_overrides(self, **kwargs) -> "Config":
        """Return a new Config with specified fields overridden.

        Only applies overrides for non-None values, so CLI flags
        that weren't specified don't clobber config file values.
        """
        updates = {k: v for k, v in kwargs.items() if v is not None}
        return dataclasses.replace(self, **updates) if updates else self


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load config from TOML file, falling back to defaults.

    Args:
        config_path: Explicit path to config file. If None, uses
                     TEECLIP_HOME/config.toml or ~/.teeclip/config.toml.

    Returns:
        Config dataclass with merged values.
    """
    path = config_path or get_config_path()

    if not path.is_file():
        return Config()

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        _warn(f"Could not read config file {path}: {e}")
        return Config()

    try:
        parsed = _parse_toml(text)
    except Exception as e:
        _warn(f"Could not parse config file {path}: {e}")
        return Config()

    return _build_config(parsed)


def _parse_toml(text: str) -> dict:
    """Parse TOML text using tomllib (3.11+) or fallback parser."""
    if sys.version_info >= (3, 11):
        import tomllib
        return tomllib.loads(text)
    else:
        from ._toml_fallback import loads
        return loads(text)


def _build_config(parsed: dict) -> Config:
    """Build a Config from parsed TOML dict, using defaults for missing keys."""
    def _get(section: str, key: str, default):
        val = parsed.get(section, {}).get(key, default)
        # Type coercion for safety
        if isinstance(default, bool):
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes")
            return bool(val)
        if isinstance(default, int) and not isinstance(default, bool):
            try:
                return int(val)
            except (ValueError, TypeError):
                return default
        return val

    return Config(
        history_enabled=_get("history", "enabled", _DEFAULTS["history"]["enabled"]),
        history_max_entries=_get("history", "max_entries", _DEFAULTS["history"]["max_entries"]),
        history_auto_save=_get("history", "auto_save", _DEFAULTS["history"]["auto_save"]),
        history_preview_length=_get("history", "preview_length", _DEFAULTS["history"]["preview_length"]),
        history_list_count=_get("history", "list_count", _DEFAULTS["history"]["list_count"]),
        clipboard_backend=_get("clipboard", "backend", _DEFAULTS["clipboard"]["backend"]),
        output_quiet=_get("output", "quiet", _DEFAULTS["output"]["quiet"]),
        security_encryption=_get("security", "encryption", _DEFAULTS["security"]["encryption"]),
        security_auth_method=_get("security", "auth_method", _DEFAULTS["security"]["auth_method"]),
    )


def format_config(config: Config, config_path: Optional[Path] = None) -> str:
    """Format config for display (used by --config flag)."""
    path = config_path or get_config_path()
    lines = [
        f"Config file: {path}",
        f"  exists: {'yes' if path.is_file() else 'no'}",
        "",
        "[history]",
        f"  enabled = {str(config.history_enabled).lower()}",
        f"  max_entries = {config.history_max_entries}",
        f"  auto_save = {str(config.history_auto_save).lower()}",
        f"  preview_length = {config.history_preview_length}",
        f"  list_count = {config.history_list_count}",
        "",
        "[clipboard]",
        f"  backend = {config.clipboard_backend or '(auto)'}",
        "",
        "[output]",
        f"  quiet = {str(config.output_quiet).lower()}",
        "",
        "[security]",
        f"  encryption = {config.security_encryption}",
        f"  auth_method = {config.security_auth_method}",
    ]
    return "\n".join(lines)


def _warn(msg: str) -> None:
    """Print a warning to stderr."""
    print(f"teeclip: config: {msg}", file=sys.stderr)
