"""Tests for teeclip clipboard history store."""

import sqlite3
import time

import pytest

from teeclip.history import HistoryStore, HistoryEntry, HistoryError, _make_preview


# ── HistoryStore basics ───────────────────────────────────────────────


def test_store_creates_db_on_first_access(teeclip_home):
    """Database file is created lazily on first operation."""
    store = HistoryStore()
    assert not (teeclip_home / "history.db").exists()
    store.count()  # triggers connection
    assert (teeclip_home / "history.db").exists()
    store.close()


def test_store_context_manager(teeclip_home):
    """HistoryStore works as a context manager."""
    with HistoryStore() as store:
        store.save(b"context manager test")
        assert store.count() == 1


def test_empty_store_count(history_store):
    """Fresh store has zero clips."""
    assert history_store.count() == 0


def test_empty_store_list(history_store):
    """Fresh store returns empty list."""
    assert history_store.list_recent() == []


# ── Save & retrieve ──────────────────────────────────────────────────


def test_save_returns_id(history_store):
    """save() returns the clip ID on success."""
    clip_id = history_store.save(b"hello world")
    assert isinstance(clip_id, int)
    assert clip_id >= 1


def test_save_and_retrieve(history_store):
    """Saved content can be retrieved by index."""
    history_store.save(b"first clip")
    content = history_store.get_clip(1)
    assert content == b"first clip"


def test_retrieve_ordering(history_store):
    """Index 1 is the most recent clip."""
    history_store.save(b"older")
    history_store.save(b"newer")
    assert history_store.get_clip(1) == b"newer"
    assert history_store.get_clip(2) == b"older"


def test_get_clip_out_of_range(history_store):
    """get_clip() returns None for invalid indices."""
    history_store.save(b"only one")
    assert history_store.get_clip(0) is None
    assert history_store.get_clip(-1) is None
    assert history_store.get_clip(2) is None
    assert history_store.get_clip(999) is None


def test_get_clip_entry(history_store):
    """get_clip_entry() returns (HistoryEntry, bytes) tuple."""
    history_store.save(b"entry test", source="test")
    result = history_store.get_clip_entry(1)
    assert result is not None
    entry, content = result
    assert isinstance(entry, HistoryEntry)
    assert content == b"entry test"
    assert entry.source == "test"
    assert entry.content_type == "text/plain"
    assert entry.size == len(b"entry test")


def test_get_clip_entry_out_of_range(history_store):
    """get_clip_entry() returns None for invalid indices."""
    assert history_store.get_clip_entry(0) is None
    assert history_store.get_clip_entry(1) is None


def test_save_binary_content(history_store):
    """Binary (non-UTF-8) content is stored and retrieved correctly."""
    data = bytes(range(256))
    history_store.save(data, content_type="application/octet-stream")
    assert history_store.get_clip(1) == data


def test_save_empty_content(history_store):
    """Empty bytes can be saved."""
    clip_id = history_store.save(b"")
    assert clip_id is not None
    assert history_store.get_clip(1) == b""


def test_save_large_content(history_store):
    """Large content is stored without truncation."""
    data = b"x" * 100_000
    history_store.save(data)
    assert history_store.get_clip(1) == data


# ── Deduplication ─────────────────────────────────────────────────────


def test_dedup_skips_consecutive_identical(history_store):
    """Consecutive identical saves are deduplicated."""
    id1 = history_store.save(b"duplicate")
    id2 = history_store.save(b"duplicate")
    assert id1 is not None
    assert id2 is None
    assert history_store.count() == 1


def test_dedup_allows_nonconsecutive_identical(history_store):
    """Same content is allowed if separated by different content."""
    history_store.save(b"alpha")
    history_store.save(b"beta")
    id3 = history_store.save(b"alpha")
    assert id3 is not None
    assert history_store.count() == 3


def test_dedup_different_content_saved(history_store):
    """Different content is always saved."""
    history_store.save(b"one")
    history_store.save(b"two")
    assert history_store.count() == 2


# ── FIFO eviction ────────────────────────────────────────────────────


def test_fifo_eviction(teeclip_home):
    """Oldest clips are evicted when max_entries is exceeded."""
    from teeclip.config import Config
    config = Config(history_max_entries=3)
    store = HistoryStore(config=config)

    for i in range(5):
        store.save(f"clip {i}".encode())

    assert store.count() == 3
    # Most recent 3 should remain
    assert store.get_clip(1) == b"clip 4"
    assert store.get_clip(2) == b"clip 3"
    assert store.get_clip(3) == b"clip 2"
    store.close()


def test_fifo_preserves_within_limit(teeclip_home):
    """No eviction when count is within max_entries."""
    from teeclip.config import Config
    config = Config(history_max_entries=10)
    store = HistoryStore(config=config)

    for i in range(5):
        store.save(f"clip {i}".encode())

    assert store.count() == 5
    store.close()


# ── list_recent ───────────────────────────────────────────────────────


def test_list_recent_returns_entries(populated_history):
    """list_recent returns HistoryEntry objects."""
    entries = populated_history.list_recent()
    assert len(entries) == 5
    assert all(isinstance(e, HistoryEntry) for e in entries)


def test_list_recent_ordered_newest_first(populated_history):
    """list_recent returns newest first."""
    entries = populated_history.list_recent()
    assert entries[0].preview == "clip 5"
    assert entries[-1].preview == "clip 1"


def test_list_recent_respects_limit(populated_history):
    """list_recent limit parameter works."""
    entries = populated_history.list_recent(limit=2)
    assert len(entries) == 2
    assert entries[0].preview == "clip 5"


def test_list_recent_limit_larger_than_count(populated_history):
    """list_recent with limit > count returns all entries."""
    entries = populated_history.list_recent(limit=100)
    assert len(entries) == 5


# ── HistoryEntry fields ──────────────────────────────────────────────


def test_entry_has_expected_fields(history_store):
    """HistoryEntry exposes all expected metadata fields."""
    history_store.save(b"field test", source="unit-test")
    entry = history_store.list_recent(limit=1)[0]

    assert isinstance(entry.id, int)
    assert isinstance(entry.timestamp, str)
    assert entry.content_type == "text/plain"
    assert entry.size == len(b"field test")
    assert len(entry.hash) == 64  # SHA-256 hex
    assert entry.preview == "field test"
    assert entry.source == "unit-test"
    assert entry.encrypted is False
    assert entry.sensitive is False


def test_entry_timestamp_is_iso(history_store):
    """Timestamp is ISO 8601 format."""
    history_store.save(b"timestamp test")
    entry = history_store.list_recent(limit=1)[0]
    # Should contain date separator and time
    assert "T" in entry.timestamp
    assert "-" in entry.timestamp


# ── Clear ─────────────────────────────────────────────────────────────


def test_clear_returns_count(populated_history):
    """clear() returns the number of deleted clips."""
    count = populated_history.clear()
    assert count == 5


def test_clear_empties_store(populated_history):
    """clear() removes all clips."""
    populated_history.clear()
    assert populated_history.count() == 0
    assert populated_history.list_recent() == []


def test_clear_empty_store(history_store):
    """clear() on empty store returns 0."""
    assert history_store.clear() == 0


# ── Preview generation ────────────────────────────────────────────────


def test_preview_simple_text():
    """Simple text preview is returned as-is."""
    assert _make_preview(b"hello world") == "hello world"


def test_preview_collapses_whitespace():
    """Multiline text is collapsed to single line."""
    assert _make_preview(b"line one\nline two\n\tindented") == "line one line two indented"


def test_preview_truncated():
    """Long text is truncated with ellipsis."""
    long_text = ("a" * 100).encode()
    preview = _make_preview(long_text, max_len=20)
    assert len(preview) == 20
    assert preview.endswith("...")


def test_preview_binary():
    """Binary data shows hex preview."""
    data = bytes([0xFF, 0xFE, 0x00, 0x01])
    preview = _make_preview(data)
    assert "(binary," in preview
    assert "4 bytes" in preview
    assert "fffe0001" in preview


def test_preview_empty():
    """Empty data shows '(empty)'."""
    assert _make_preview(b"") == "(empty)"


def test_preview_exact_max_len():
    """Text exactly at max_len is not truncated."""
    text = ("a" * 80).encode()
    preview = _make_preview(text, max_len=80)
    assert preview == "a" * 80
    assert "..." not in preview


# ── Schema versioning ────────────────────────────────────────────────


def test_schema_version_stored(history_store):
    """Schema version is recorded in metadata table."""
    history_store.count()  # ensure schema is initialized
    conn = history_store._ensure_conn()
    row = conn.execute(
        "SELECT value FROM metadata WHERE key = 'schema_version'"
    ).fetchone()
    assert row is not None
    assert row["value"] == "1"


def test_created_at_stored(history_store):
    """created_at timestamp is recorded in metadata table."""
    history_store.count()
    conn = history_store._ensure_conn()
    row = conn.execute(
        "SELECT value FROM metadata WHERE key = 'created_at'"
    ).fetchone()
    assert row is not None
    assert "T" in row["value"]  # ISO 8601


def test_reopen_preserves_data(teeclip_home):
    """Data persists across store open/close cycles."""
    store1 = HistoryStore()
    store1.save(b"persistent data")
    store1.close()

    store2 = HistoryStore()
    assert store2.count() == 1
    assert store2.get_clip(1) == b"persistent data"
    store2.close()


# ── Edge cases ────────────────────────────────────────────────────────


def test_unicode_content(history_store):
    """Unicode text is stored and retrieved correctly."""
    text = "Hello 世界 🌍 café"
    data = text.encode("utf-8")
    history_store.save(data)
    assert history_store.get_clip(1) == data


def test_source_field_preserved(history_store):
    """Source field is stored correctly."""
    history_store.save(b"from pipe", source="pipe")
    history_store.save(b"from clipboard", source="clipboard")
    entries = history_store.list_recent(limit=2)
    assert entries[0].source == "clipboard"
    assert entries[1].source == "pipe"


def test_content_type_preserved(history_store):
    """Content type is stored correctly."""
    history_store.save(b"binary data", content_type="application/octet-stream")
    entry = history_store.list_recent(limit=1)[0]
    assert entry.content_type == "application/octet-stream"


# ── delete_by_indices ────────────────────────────────────────────────


def test_delete_by_indices_single(history_store):
    """delete_by_indices removes a single entry by display index."""
    for i in range(1, 4):
        history_store.save(f"clip {i}".encode(), source="test")

    # Delete #2 in display order (clip 2, the middle one)
    count = history_store.delete_by_indices([2])
    assert count == 1
    assert history_store.count() == 2

    # clip 3 is #1 (newest), clip 1 is #2 (oldest) — clip 2 gone
    assert history_store.get_clip(1) == b"clip 3"
    assert history_store.get_clip(2) == b"clip 1"


def test_delete_by_indices_multiple(history_store):
    """delete_by_indices removes multiple entries."""
    for i in range(1, 6):
        history_store.save(f"clip {i}".encode(), source="test")

    # Delete #1 (clip 5) and #4 (clip 2)
    count = history_store.delete_by_indices([1, 4])
    assert count == 2
    assert history_store.count() == 3

    # Remaining: clip 4 (#1), clip 3 (#2), clip 1 (#3)
    assert history_store.get_clip(1) == b"clip 4"
    assert history_store.get_clip(2) == b"clip 3"
    assert history_store.get_clip(3) == b"clip 1"


def test_delete_by_indices_out_of_range(history_store):
    """Out-of-range indices are silently ignored."""
    history_store.save(b"only clip", source="test")

    count = history_store.delete_by_indices([5, 10])
    assert count == 0
    assert history_store.count() == 1


def test_delete_by_indices_empty_list(history_store):
    """Empty index list deletes nothing."""
    history_store.save(b"still here", source="test")

    count = history_store.delete_by_indices([])
    assert count == 0
    assert history_store.count() == 1


# ── parse_clear_selector ────────────────────────────────────────────


def test_parse_single_index():
    """Single number parses to one-element list."""
    from teeclip.cli import parse_clear_selector
    assert parse_clear_selector("3") == [3]


def test_parse_range():
    """START:END parses to inclusive range."""
    from teeclip.cli import parse_clear_selector
    assert parse_clear_selector("4:7") == [4, 5, 6, 7]


def test_parse_combo():
    """Comma-separated indices and ranges parse correctly."""
    from teeclip.cli import parse_clear_selector
    assert parse_clear_selector("1,5:7,10") == [1, 5, 6, 7, 10]


def test_parse_deduplicates():
    """Overlapping ranges produce unique sorted indices."""
    from teeclip.cli import parse_clear_selector
    assert parse_clear_selector("3:5,4:6") == [3, 4, 5, 6]


def test_parse_invalid_text():
    """Non-numeric input raises ValueError."""
    from teeclip.cli import parse_clear_selector
    with pytest.raises(ValueError, match="invalid index"):
        parse_clear_selector("abc")


def test_parse_invalid_range():
    """Reversed range raises ValueError."""
    from teeclip.cli import parse_clear_selector
    with pytest.raises(ValueError, match="start > end"):
        parse_clear_selector("10:5")


def test_parse_zero_index():
    """Zero index raises ValueError."""
    from teeclip.cli import parse_clear_selector
    with pytest.raises(ValueError, match="positive"):
        parse_clear_selector("0")
