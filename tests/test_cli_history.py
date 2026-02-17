"""CLI integration tests for clipboard history features.

These tests run teeclip as a subprocess with an isolated TEECLIP_HOME,
exercising the --list, --get, --clear, --save, --config, and --no-history flags.
"""

import sqlite3

import pytest


# ── --config ──────────────────────────────────────────────────────────


def test_config_shows_settings(run_teeclip):
    """--config outputs effective configuration."""
    result = run_teeclip(["--config"])
    assert result.returncode == 0
    assert "[history]" in result.stdout
    assert "max_entries = 50" in result.stdout
    assert "[security]" in result.stdout
    assert "Config file:" in result.stdout


# ── --list ────────────────────────────────────────────────────────────


def test_list_empty_history(run_teeclip):
    """--list on empty history shows placeholder."""
    result = run_teeclip(["--list"])
    assert result.returncode == 0
    assert "(no history)" in result.stdout


def test_list_shows_piped_content(run_teeclip):
    """Content piped in is saved to history and shown by --list."""
    # Pipe some content (will fail clipboard copy, but history should work)
    run_teeclip([], input_data="hello from pipe")

    result = run_teeclip(["--list"])
    assert result.returncode == 0
    assert "hello from pipe" in result.stdout


def test_list_shows_multiple_entries(run_teeclip):
    """Multiple piped entries appear in --list output."""
    run_teeclip([], input_data="first clip")
    run_teeclip([], input_data="second clip")
    run_teeclip([], input_data="third clip")

    result = run_teeclip(["--list"])
    assert result.returncode == 0
    assert "first clip" in result.stdout
    assert "second clip" in result.stdout
    assert "third clip" in result.stdout


def test_list_count_limits_output(run_teeclip):
    """--list-count limits the number of entries shown."""
    for i in range(5):
        run_teeclip([], input_data=f"clip number {i}")

    result = run_teeclip(["--list", "--list-count", "2"])
    assert result.returncode == 0
    # Should show the 2 most recent
    assert "clip number 4" in result.stdout
    assert "clip number 3" in result.stdout
    # Should NOT show older ones
    assert "clip number 0" not in result.stdout


# ── --get ─────────────────────────────────────────────────────────────


def test_get_retrieves_content(run_teeclip):
    """--get N outputs the Nth most recent clip."""
    run_teeclip([], input_data="older content")
    run_teeclip([], input_data="newer content")

    result = run_teeclip(["--get", "1"])
    assert result.returncode == 0
    assert "newer content" in result.stdout

    result = run_teeclip(["--get", "2"])
    assert result.returncode == 0
    assert "older content" in result.stdout


def test_get_invalid_index(run_teeclip):
    """--get with out-of-range index exits with error."""
    result = run_teeclip(["--get", "1"])
    assert result.returncode == 1
    assert "no clip at index 1" in result.stderr


def test_get_zero_index(run_teeclip):
    """--get 0 exits with error."""
    run_teeclip([], input_data="some data")
    result = run_teeclip(["--get", "0"])
    assert result.returncode == 1
    assert "no clip at index 0" in result.stderr


# ── --clear ───────────────────────────────────────────────────────────


def test_clear_removes_history(run_teeclip):
    """--clear deletes all history entries."""
    run_teeclip([], input_data="to be cleared")

    # --clear with piped "y" as confirmation
    result = run_teeclip(["--clear"], input_data="y\n")
    assert result.returncode == 0
    assert "cleared" in result.stdout

    # Verify empty
    result = run_teeclip(["--list"])
    assert "(no history)" in result.stdout


def test_clear_noninteractive_clears_without_prompt(run_teeclip):
    """--clear in non-interactive mode (piped stdin) clears without prompting."""
    run_teeclip([], input_data="to be cleared too")

    # When stdin is not a TTY, --clear proceeds without asking
    result = run_teeclip(["--clear"], input_data="")
    assert result.returncode == 0
    assert "cleared" in result.stdout

    result = run_teeclip(["--list"])
    assert "(no history)" in result.stdout


# ── --no-history ──────────────────────────────────────────────────────


def test_no_history_skips_save(run_teeclip):
    """--no-history prevents saving to history database."""
    run_teeclip(["--no-history"], input_data="should not be saved")

    result = run_teeclip(["--list"])
    assert "(no history)" in result.stdout


def test_no_history_still_outputs(run_teeclip):
    """--no-history still passes through to stdout."""
    result = run_teeclip(["--no-history"], input_data="pass through")
    assert "pass through" in result.stdout


# ── Deduplication via CLI ─────────────────────────────────────────────


def test_dedup_consecutive(run_teeclip):
    """Consecutive identical pipes are deduplicated in history."""
    run_teeclip([], input_data="same content")
    run_teeclip([], input_data="same content")

    result = run_teeclip(["--list"])
    # Should only appear once — count lines with the content
    lines = [l for l in result.stdout.splitlines() if "same content" in l]
    assert len(lines) == 1


# ── History database location ────────────────────────────────────────


def test_history_db_created_in_teeclip_home(run_teeclip):
    """History database is created in TEECLIP_HOME directory."""
    run_teeclip([], input_data="trigger db creation")
    db_path = run_teeclip.home / "history.db"
    assert db_path.exists()
