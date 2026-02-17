"""
Minimal TOML parser for Python 3.8-3.10 (before tomllib was added in 3.11).

Only handles the subset of TOML that teeclip's config.toml uses:
- [section] headers
- key = "string" (double-quoted)
- key = 'string' (single-quoted)
- key = true / false (booleans)
- key = 123 (integers)
- # comments
- blank lines

Does NOT handle: arrays, inline tables, multi-line strings, dotted keys,
dates, floats, escape sequences, etc.
"""


def loads(text: str) -> dict:
    """Parse a simple TOML string into a nested dict."""
    result = {}
    current_section = None

    for line in text.splitlines():
        stripped = line.strip()

        # Skip blank lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        # Section header
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].strip()
            result.setdefault(current_section, {})
            continue

        # Key = value
        if "=" in stripped:
            key, _, raw_value = stripped.partition("=")
            key = key.strip()
            raw_value = raw_value.strip()

            # Strip inline comments (but not inside quotes)
            raw_value = _strip_inline_comment(raw_value)
            value = _parse_value(raw_value)

            if current_section:
                result[current_section][key] = value
            else:
                result.setdefault("", {})
                result[""][key] = value

    return result


def load(fp) -> dict:
    """Parse a simple TOML file object into a nested dict."""
    return loads(fp.read())


def _strip_inline_comment(raw: str) -> str:
    """Remove inline comments, respecting quoted strings."""
    if not raw:
        return raw

    in_quote = None
    for i, ch in enumerate(raw):
        if ch in ('"', "'") and in_quote is None:
            in_quote = ch
        elif ch == in_quote:
            in_quote = None
        elif ch == "#" and in_quote is None:
            return raw[:i].rstrip()

    return raw


def _parse_value(raw: str) -> object:
    """Parse a TOML value string into a Python object."""
    if not raw:
        return ""

    # Double-quoted string
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1]

    # Single-quoted string
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1]

    # Booleans
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False

    # Integers
    try:
        return int(raw)
    except ValueError:
        pass

    # Unquoted string fallback
    return raw
