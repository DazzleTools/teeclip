"""
Centralized path resolution for teeclip data directory.

The data directory (~/.teeclip/) stores history database and config file.
Supports TEECLIP_HOME env var override for testing and custom installs.
"""

import os
from pathlib import Path


def get_data_dir() -> Path:
    """Return the teeclip data directory path.

    Checks TEECLIP_HOME env var first (for testing and custom installs),
    then falls back to ~/.teeclip/.
    """
    env_dir = os.environ.get("TEECLIP_HOME")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".teeclip"


def get_history_db_path() -> Path:
    """Return the path to the history SQLite database."""
    return get_data_dir() / "history.db"


def get_config_path() -> Path:
    """Return the path to the config TOML file."""
    return get_data_dir() / "config.toml"


def ensure_data_dir() -> Path:
    """Create the data directory if it doesn't exist. Returns the path."""
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
