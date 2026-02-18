"""Inspect the teeclip history.db SQLite database directly.

Shows schema, recent rows (with raw column values), and metadata.
Useful for verifying encryption, size masking, HMAC hashing, etc.

Usage:
    python tests/one-offs/inspect_history_db.py
    python tests/one-offs/inspect_history_db.py --all        # show all rows
    python tests/one-offs/inspect_history_db.py --count 5    # show N rows
"""

import argparse
import os
import sqlite3
import sys


def get_db_path():
    home = os.environ.get("TEECLIP_HOME", os.path.join(os.path.expanduser("~"), ".teeclip"))
    return os.path.join(home, "history.db")


def main():
    parser = argparse.ArgumentParser(description="Inspect teeclip history.db")
    parser.add_argument("--all", action="store_true", help="show all rows")
    parser.add_argument("--count", type=int, default=5, help="rows to show (default: 5)")
    parser.add_argument("--db", type=str, default=None, help="path to history.db")
    args = parser.parse_args()

    db_path = args.db or get_db_path()
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        sys.exit(1)

    print(f"Database: {db_path}")
    print(f"Size: {os.path.getsize(db_path):,} bytes")
    print()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Schema
    print("=== SCHEMA ===")
    for row in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'").fetchall():
        if row[0]:
            print(row[0])
            print()

    # Row count
    total = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
    print(f"=== CLIPS ({total} total) ===")

    limit = "" if args.all else f"LIMIT {args.count}"
    rows = conn.execute(f"""
        SELECT id, timestamp, content_type,
               length(content) as content_bytes,
               size as stored_size,
               hash,
               preview, source, encrypted, encrypted_meta
        FROM clips ORDER BY id DESC {limit}
    """).fetchall()

    for r in rows:
        d = dict(r)
        enc_marker = " [E]" if d["encrypted"] else ""
        print(f"  #{d['id']}{enc_marker}")
        print(f"    timestamp:     {d['timestamp']}")
        print(f"    content_type:  {d['content_type']}")
        print(f"    content_bytes: {d['content_bytes']} (raw blob size in DB)")
        print(f"    stored_size:   {d['stored_size']}" +
              (" (masked)" if d["encrypted"] else ""))
        print(f"    hash:          {d['hash'][:40]}..." if len(d["hash"]) > 40 else f"    hash:          {d['hash']}")
        print(f"    preview:       {d['preview']!r}")
        print(f"    source:        {d['source']}")
        print(f"    encrypted:     {d['encrypted']}")
        enc_meta = d["encrypted_meta"]
        if enc_meta:
            print(f"    encrypted_meta: ({len(enc_meta)} bytes)")
        else:
            print(f"    encrypted_meta: NULL")
        print()

    if not args.all and total > args.count:
        print(f"  (showing {args.count} of {total} -- use --all to see everything)")
        print()

    # Metadata
    print("=== METADATA ===")
    for r in conn.execute("SELECT * FROM metadata").fetchall():
        print(f"  {r['key']} = {r['value']}")

    # Indexes
    print()
    print("=== INDEXES ===")
    for r in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchall():
        print(f"  {r['name']}")

    conn.close()


if __name__ == "__main__":
    main()
