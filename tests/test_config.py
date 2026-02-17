"""Tests for teeclip configuration loading."""

import sys

from teeclip.config import Config, load_config, format_config


def test_default_config_when_no_file(teeclip_home):
    """When no config.toml exists, all defaults are applied."""
    config = load_config()
    assert config.history_enabled is True
    assert config.history_max_entries == 50
    assert config.history_auto_save is True
    assert config.history_preview_length == 80
    assert config.clipboard_backend == ""
    assert config.output_quiet is False
    assert config.security_encryption == "none"
    assert config.security_auth_method == "os"


def test_load_valid_config(config_file):
    """Valid TOML file is parsed correctly."""
    config_file(
        '[history]\n'
        'enabled = true\n'
        'max_entries = 100\n'
        '\n'
        '[output]\n'
        'quiet = true\n'
    )
    config = load_config()
    assert config.history_max_entries == 100
    assert config.output_quiet is True


def test_partial_config_uses_defaults(config_file):
    """Config with only some keys uses defaults for the rest."""
    config_file('[history]\nmax_entries = 25\n')
    config = load_config()
    assert config.history_max_entries == 25
    assert config.history_enabled is True  # default
    assert config.output_quiet is False    # default section missing entirely


def test_empty_config_file(config_file):
    """Empty config.toml uses all defaults."""
    config_file("")
    config = load_config()
    assert config.history_max_entries == 50


def test_security_section(config_file):
    """[security] section parsed correctly."""
    config_file('[security]\nencryption = "aes256"\n')
    config = load_config()
    assert config.security_encryption == "aes256"
    assert config.security_auth_method == "os"  # default


def test_security_auth_method(config_file):
    """[security] auth_method parsed correctly."""
    config_file('[security]\nencryption = "aes256"\nauth_method = "password"\n')
    config = load_config()
    assert config.security_encryption == "aes256"
    assert config.security_auth_method == "password"


def test_clipboard_backend(config_file):
    """Clipboard backend setting loaded."""
    config_file('[clipboard]\nbackend = "xclip"\n')
    config = load_config()
    assert config.clipboard_backend == "xclip"


def test_cli_overrides():
    """Config.with_overrides() replaces specified fields."""
    config = Config(history_max_entries=50, output_quiet=False)
    overridden = config.with_overrides(output_quiet=True, history_max_entries=10)
    assert overridden.output_quiet is True
    assert overridden.history_max_entries == 10
    # Original unchanged (frozen dataclass)
    assert config.output_quiet is False


def test_cli_overrides_skip_none():
    """with_overrides() ignores None values (unset CLI flags)."""
    config = Config(output_quiet=True)
    overridden = config.with_overrides(output_quiet=None)
    assert overridden.output_quiet is True  # not overridden


def test_malformed_config_falls_back(config_file):
    """Malformed TOML falls back to defaults with warning."""
    config_file("[invalid\nthis is not toml at all {{{}}")
    config = load_config()
    # Should get defaults, not crash
    assert config.history_max_entries == 50


def test_config_display(teeclip_home):
    """format_config produces readable output."""
    config = Config()
    output = format_config(config)
    assert "[history]" in output
    assert "max_entries = 50" in output
    assert "[security]" in output
    assert "encryption = none" in output


def test_config_display_shows_path(teeclip_home):
    """format_config shows the config file path."""
    config = Config()
    output = format_config(config)
    assert "Config file:" in output


def test_explicit_config_path(tmp_path):
    """load_config() accepts an explicit path."""
    custom = tmp_path / "custom.toml"
    custom.write_text('[history]\nmax_entries = 99\n', encoding="utf-8")
    config = load_config(config_path=custom)
    assert config.history_max_entries == 99


def test_boolean_string_coercion(config_file):
    """String 'true'/'false' coerced to bool."""
    config_file('[history]\nenabled = true\nauto_save = false\n')
    config = load_config()
    assert config.history_enabled is True
    assert config.history_auto_save is False


def test_integer_coercion(config_file):
    """String integers coerced to int."""
    config_file('[history]\nmax_entries = 200\n')
    config = load_config()
    assert config.history_max_entries == 200
    assert isinstance(config.history_max_entries, int)
