"""Shared test fixtures for teeclip."""

import os
import subprocess
import sys

import pytest


@pytest.fixture
def teeclip_home(tmp_path, monkeypatch):
    """Provide an isolated ~/.teeclip/ directory for testing.

    Sets TEECLIP_HOME env var so all teeclip modules use tmp_path.
    Does NOT create the directory — lets module init logic do that.
    """
    home = tmp_path / ".teeclip"
    monkeypatch.setenv("TEECLIP_HOME", str(home))
    return home


@pytest.fixture
def history_store(teeclip_home):
    """Provide a fresh HistoryStore connected to a temp database."""
    from teeclip.history import HistoryStore
    store = HistoryStore()
    yield store
    store.close()


@pytest.fixture
def populated_history(history_store):
    """A history database pre-populated with 5 sample clips."""
    for i in range(1, 6):
        history_store.save(f"clip {i}".encode(), source="test")
    return history_store


@pytest.fixture
def config_file(teeclip_home):
    """Write arbitrary TOML content to the test config file.

    Returns a helper function. Call it with a TOML string.
    """
    def _write(content: str):
        teeclip_home.mkdir(parents=True, exist_ok=True)
        config_path = teeclip_home / "config.toml"
        config_path.write_text(content, encoding="utf-8")
        return config_path
    return _write


@pytest.fixture
def mock_clipboard(monkeypatch):
    """Replace clipboard operations with an in-memory buffer."""
    buffer = {"content": b""}

    def mock_copy(data, backend_name=None):
        buffer["content"] = data

    def mock_paste(backend_name=None):
        return buffer["content"]

    monkeypatch.setattr("teeclip.clipboard.copy_to_clipboard", mock_copy)
    monkeypatch.setattr("teeclip.clipboard.paste_from_clipboard", mock_paste)
    return buffer


@pytest.fixture
def run_teeclip(tmp_path):
    """Run teeclip as a subprocess with isolated TEECLIP_HOME.

    Returns a callable: run_teeclip(args, input_data=None, text=True)
    The callable has a .home attribute pointing to the teeclip data dir.
    """
    teeclip_home = tmp_path / ".teeclip"

    def _run(args, input_data=None, text=True):
        env = os.environ.copy()
        env["TEECLIP_HOME"] = str(teeclip_home)
        cmd = [sys.executable, "-m", "teeclip"] + args
        return subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=text,
            env=env,
            timeout=30,
        )

    _run.home = teeclip_home
    return _run
