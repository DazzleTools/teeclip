"""Tests for the minimal TOML fallback parser."""

import sys

from teeclip._toml_fallback import loads


def test_empty_string():
    assert loads("") == {}


def test_comments_only():
    assert loads("# just a comment\n# another one") == {}


def test_blank_lines():
    assert loads("\n\n\n") == {}


def test_section_and_keys():
    result = loads("[history]\nenabled = true\nmax_entries = 50")
    assert result == {"history": {"enabled": True, "max_entries": 50}}


def test_multiple_sections():
    text = "[history]\nenabled = true\n\n[clipboard]\nbackend = xclip"
    result = loads(text)
    assert result["history"]["enabled"] is True
    assert result["clipboard"]["backend"] == "xclip"


def test_double_quoted_strings():
    result = loads('[output]\npath = "/home/user/.teeclip"')
    assert result["output"]["path"] == "/home/user/.teeclip"


def test_single_quoted_strings():
    result = loads("[output]\npath = '/home/user/.teeclip'")
    assert result["output"]["path"] == "/home/user/.teeclip"


def test_boolean_true():
    result = loads("[test]\na = true\nb = True")
    assert result["test"]["a"] is True
    assert result["test"]["b"] is True


def test_boolean_false():
    result = loads("[test]\na = false\nb = False")
    assert result["test"]["a"] is False
    assert result["test"]["b"] is False


def test_integers():
    result = loads("[test]\ncount = 42\nneg = -10")
    assert result["test"]["count"] == 42
    # Negative ints may parse or fall back to string
    # Our parser handles int() which supports negatives
    assert result["test"]["neg"] == -10


def test_unquoted_string():
    result = loads("[test]\nmode = auto")
    assert result["test"]["mode"] == "auto"


def test_inline_comment():
    result = loads("[test]\ncount = 42  # the answer")
    assert result["test"]["count"] == 42


def test_inline_comment_respects_quotes():
    result = loads('[test]\npath = "value # not a comment"')
    assert result["test"]["path"] == "value # not a comment"


def test_whitespace_around_equals():
    result = loads("[test]\n  key  =  value  ")
    assert result["test"]["key"] == "value"


def test_empty_quoted_string():
    result = loads('[test]\nbackend = ""')
    assert result["test"]["backend"] == ""


def test_matches_tomllib():
    """Verify fallback parser matches tomllib output for our config format."""
    if sys.version_info < (3, 11):
        import pytest
        pytest.skip("tomllib only available on Python 3.11+")

    import tomllib

    config_text = """
[history]
enabled = true
max_entries = 50
auto_save = true
preview_length = 80

[clipboard]
backend = ""

[output]
quiet = false

[security]
encryption = "none"
"""
    fallback_result = loads(config_text)
    tomllib_result = tomllib.loads(config_text)
    assert fallback_result == tomllib_result
