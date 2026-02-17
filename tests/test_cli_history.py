"""CLI integration tests for clipboard history features.

These tests run teeclip as a subprocess with an isolated TEECLIP_HOME,
exercising the --list, --get, --clear, --save, --config, and --no-history flags.

Flag interaction test matrix:
  Flag combination              | stdout | clipboard | history | notes
  ------------------------------|--------|-----------|---------|------
  (default pipe)                | yes    | attempt   | yes     | clipboard may fail in CI
  --no-clipboard                | yes    | no        | yes     | regression: v0.2.0a1 skipped history
  --no-history                  | yes    | attempt   | no      |
  --no-clipboard --no-history   | yes    | no        | no      | pure tee mode
  --quiet                       | yes    | attempt   | yes     | suppresses warnings only
  --save                        | n/a    | read      | yes     | saves clipboard to history
  --paste                       | yes    | read      | no      | prints clipboard to stdout
  --get N                       | yes    | write     | no      | retrieves from history
  --clear [SEL]                 | status | n/a       | delete  | selective or clear-all
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


# ── --clear selective ────────────────────────────────────────────────


def test_clear_single_index(run_teeclip):
    """--clear N deletes only the Nth entry."""
    run_teeclip([], input_data="clip one")
    run_teeclip([], input_data="clip two")
    run_teeclip([], input_data="clip three")

    # Delete entry #2 (the middle one: "clip two")
    result = run_teeclip(["--clear", "2"])
    assert result.returncode == 0
    assert "deleted 1 entries" in result.stdout

    result = run_teeclip(["--list"])
    assert "clip one" in result.stdout
    assert "clip three" in result.stdout
    assert "clip two" not in result.stdout


def test_clear_range(run_teeclip):
    """--clear START:END deletes a range of entries."""
    for i in range(1, 6):
        run_teeclip([], input_data=f"range clip {i}")

    # Delete entries 2-4 (range clip 4, 3, 2 in display order)
    result = run_teeclip(["--clear", "2:4"])
    assert result.returncode == 0
    assert "deleted 3 entries" in result.stdout

    result = run_teeclip(["--list"])
    assert "range clip 5" in result.stdout   # #1 (newest, kept)
    assert "range clip 1" in result.stdout   # #5 (oldest, kept)
    assert "range clip 4" not in result.stdout
    assert "range clip 3" not in result.stdout
    assert "range clip 2" not in result.stdout


def test_clear_combo(run_teeclip):
    """--clear with comma-separated indices and ranges."""
    for i in range(1, 8):
        run_teeclip([], input_data=f"combo clip {i}")

    # Delete #1 (newest: combo clip 7) and #5:7 (combo clip 3, 2, 1)
    result = run_teeclip(["--clear", "1,5:7"])
    assert result.returncode == 0
    assert "deleted 4 entries" in result.stdout

    result = run_teeclip(["--list"])
    assert "combo clip 6" in result.stdout   # kept
    assert "combo clip 5" in result.stdout   # kept
    assert "combo clip 4" in result.stdout   # kept
    assert "combo clip 7" not in result.stdout
    assert "combo clip 3" not in result.stdout
    assert "combo clip 2" not in result.stdout
    assert "combo clip 1" not in result.stdout


def test_clear_invalid_selector(run_teeclip):
    """--clear with invalid selector exits with error."""
    result = run_teeclip(["--clear", "abc"])
    assert result.returncode == 1
    assert "invalid index" in result.stderr


def test_clear_out_of_range_index_silent(run_teeclip):
    """--clear with out-of-range index deletes nothing gracefully."""
    run_teeclip([], input_data="only clip")

    result = run_teeclip(["--clear", "99"])
    assert result.returncode == 0
    assert "deleted 0 entries" in result.stdout

    # The one clip should still be there
    result = run_teeclip(["--list"])
    assert "only clip" in result.stdout


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


# ── --no-clipboard (regression for v0.2.0a1 bug) ────────────────────


def test_no_clipboard_still_saves_history(run_teeclip):
    """--no-clipboard must still save piped content to history.

    Regression test: v0.2.0a1 had a bug where --no-clipboard silently
    skipped history saves because the save was nested inside the
    clipboard-copy conditional.
    """
    result = run_teeclip(["--no-clipboard"], input_data="nc-history-test")
    assert result.returncode == 0
    assert "nc-history-test" in result.stdout  # stdout passthrough works

    # Verify history was saved
    result = run_teeclip(["--list"])
    assert "nc-history-test" in result.stdout


def test_no_clipboard_with_file(run_teeclip, tmp_path):
    """--no-clipboard writes to files and history without clipboard."""
    outfile = tmp_path / "nc_output.txt"
    result = run_teeclip(
        ["--no-clipboard", str(outfile)], input_data="nc-file-test"
    )
    assert result.returncode == 0
    assert "nc-file-test" in result.stdout
    assert outfile.read_text() == "nc-file-test"

    result = run_teeclip(["--list"])
    assert "nc-file-test" in result.stdout


# ── --no-clipboard --no-history (pure tee) ───────────────────────────


def test_no_clipboard_no_history_pure_tee(run_teeclip):
    """--no-clipboard --no-history is pure tee mode: stdout only."""
    result = run_teeclip(
        ["--no-clipboard", "--no-history"], input_data="pure tee data"
    )
    assert result.returncode == 0
    assert "pure tee data" in result.stdout

    # Verify nothing saved to history
    result = run_teeclip(["--list"])
    assert "(no history)" in result.stdout


# ── --quiet ──────────────────────────────────────────────────────────


def test_quiet_suppresses_clipboard_warning(run_teeclip):
    """--quiet suppresses clipboard backend warnings."""
    # Force a bad backend to trigger a warning
    result = run_teeclip(
        ["--backend", "nonexistent_backend"], input_data="quiet test"
    )
    # Without --quiet, stderr has a warning
    stderr_noisy = result.stderr

    result = run_teeclip(
        ["--quiet", "--backend", "nonexistent_backend"],
        input_data="quiet test",
    )
    # With --quiet, stderr should be shorter or empty
    assert len(result.stderr) <= len(stderr_noisy)


def test_quiet_still_saves_history(run_teeclip):
    """--quiet suppresses warnings but still saves to history."""
    run_teeclip(["-q", "--no-clipboard"], input_data="quiet-history-test")

    result = run_teeclip(["--list"])
    assert "quiet-history-test" in result.stdout


def test_quiet_still_passes_stdout(run_teeclip):
    """--quiet does not suppress stdout passthrough."""
    result = run_teeclip(
        ["-q", "--no-clipboard"], input_data="quiet-stdout-test"
    )
    assert result.returncode == 0
    assert "quiet-stdout-test" in result.stdout


# ── --save (in-process with mock clipboard) ─────────────────────────


def test_save_from_clipboard(teeclip_home, mock_clipboard, capsys):
    """--save saves current clipboard contents into history."""
    from teeclip.cli import main

    mock_clipboard["content"] = b"clipboard-save-test"
    main(["--save"])

    captured = capsys.readouterr()
    assert "saved to history" in captured.out

    # Verify it's in history
    from teeclip.history import HistoryStore
    with HistoryStore() as store:
        entries = store.list_recent()
        assert any("clipboard-save-test" in (e.preview or "") for e in entries)


def test_save_duplicate_reports_dedup(teeclip_home, mock_clipboard, capsys):
    """--save on duplicate content reports dedup instead of saving."""
    from teeclip.cli import main

    mock_clipboard["content"] = b"dupe-save-test"
    main(["--save"])
    capsys.readouterr()  # discard first output

    main(["--save"])  # duplicate
    captured = capsys.readouterr()
    assert "duplicate" in captured.out or "already" in captured.out


# ── --paste (in-process with mock clipboard) ─────────────────────────


def test_paste_outputs_clipboard(teeclip_home, mock_clipboard, capsys):
    """--paste prints clipboard contents to stdout."""
    from teeclip.cli import main

    mock_clipboard["content"] = b"paste-output-test"
    main(["--paste"])

    captured = capsys.readouterr()
    assert "paste-output-test" in captured.out


def test_paste_does_not_save_history(teeclip_home, mock_clipboard, capsys):
    """--paste does not save to history (read-only operation)."""
    from teeclip.cli import main
    from teeclip.history import HistoryStore

    mock_clipboard["content"] = b"paste-no-history"
    main(["--paste"])
    capsys.readouterr()

    with HistoryStore() as store:
        assert store.count() == 0


# ── --get interactions ───────────────────────────────────────────────


def test_get_outputs_to_stdout(run_teeclip):
    """--get N writes clip content to stdout."""
    run_teeclip(["--no-clipboard"], input_data="get-stdout-test")

    result = run_teeclip(["--get", "1"])
    assert result.returncode == 0
    assert "get-stdout-test" in result.stdout
