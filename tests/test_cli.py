"""Tests for teeclip CLI."""

import subprocess
import sys


def test_version_flag():
    """teeclip --version should print version string and exit 0."""
    result = subprocess.run(
        [sys.executable, "-m", "teeclip", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "teeclip" in result.stdout
    assert "PREALPHA" in result.stdout or "0." in result.stdout


def test_help_flag():
    """teeclip --help should print usage and exit 0."""
    result = subprocess.run(
        [sys.executable, "-m", "teeclip", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "clipboard" in result.stdout.lower()
    assert "FILE" in result.stdout


def test_pipe_passthrough(tmp_path):
    """Data piped through teeclip should appear on stdout unchanged."""
    test_data = "hello from teeclip\nline two\n"
    result = subprocess.run(
        [sys.executable, "-m", "teeclip", "--no-clipboard"],
        input=test_data,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout == test_data


def test_pipe_to_file(tmp_path):
    """teeclip should write to a file when given a filename."""
    outfile = tmp_path / "output.txt"
    test_data = "file output test\n"
    result = subprocess.run(
        [sys.executable, "-m", "teeclip", "--no-clipboard", str(outfile)],
        input=test_data,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout == test_data
    assert outfile.read_text() == test_data


def test_append_mode(tmp_path):
    """teeclip -a should append to existing file."""
    outfile = tmp_path / "append.txt"
    outfile.write_text("existing\n")

    result = subprocess.run(
        [sys.executable, "-m", "teeclip", "--no-clipboard", "-a", str(outfile)],
        input="appended\n",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert outfile.read_text() == "existing\nappended\n"


def test_empty_input():
    """Empty stdin should not crash."""
    result = subprocess.run(
        [sys.executable, "-m", "teeclip", "--no-clipboard"],
        input="",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout == ""
