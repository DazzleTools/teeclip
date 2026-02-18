"""
Command-line interface for teeclip.

Usage:
    my-command | teeclip              # stdout + clipboard + history
    my-command | teeclip -a log.txt   # stdout + clipboard + append to file
    my-command | teeclip output.txt   # stdout + clipboard + write to file
    teeclip --paste                   # print current clipboard to stdout
    teeclip --list                    # show recent clipboard history
    teeclip --list 20                 # show last 20 entries
    teeclip --get 1                   # retrieve most recent clip
    teeclip --version                 # show version
"""

import argparse
import sys

from ._version import __version__, get_display_version


def _list_arg(value):
    """Parse --list argument: integer or 'all' (returns -1)."""
    if value.lower() == "all":
        return -1
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a number or 'all', got '{value}'"
        )
    if n < 1:
        raise argparse.ArgumentTypeError(f"count must be >= 1, got {n}")
    return n


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    p = argparse.ArgumentParser(
        prog="teeclip",
        description=(
            "Like tee, but for the clipboard. "
            "Reads stdin, writes to stdout and the system clipboard."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  echo hello | teeclip              # copy 'hello' to clipboard\n"
            "  git diff | teeclip                # view diff AND copy to clipboard\n"
            "  cat file | teeclip -a log.txt     # clipboard + append to log\n"
            "  teeclip --paste                   # print clipboard contents\n"
            "  teeclip --paste | grep error      # pipe clipboard into grep\n"
            "  teeclip --list                    # show clipboard history\n"
            "  teeclip --list 20                 # show last 20 entries\n"
            "  teeclip --get 1                   # retrieve most recent clip\n"
            "  teeclip --clear 3                 # delete entry #3\n"
            "  teeclip --clear 4:10              # delete entries 4-10\n"
            "  teeclip --clear 2,4:10            # delete entry 2 and 4-10\n"
        ),
    )

    p.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="also write to FILE(s), like standard tee",
    )

    p.add_argument(
        "-a", "--append",
        action="store_true",
        help="append to files instead of overwriting",
    )

    p.add_argument(
        "--paste", "-p",
        action="store_true",
        help="print current clipboard contents to stdout",
    )

    p.add_argument(
        "--backend",
        metavar="NAME",
        help="force clipboard backend (windows, macos, xclip, xsel, wayland, wsl)",
    )

    p.add_argument(
        "--no-clipboard", "-nc",
        action="store_true",
        help="skip clipboard (act as plain tee)",
    )

    p.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="suppress warning messages",
    )

    # History arguments
    p.add_argument(
        "--list", "-l",
        nargs="?",
        type=_list_arg,
        const=0,
        default=None,
        dest="list_history",
        metavar="N",
        help="show recent clipboard history; N or 'all' (default: config list_count)",
    )

    p.add_argument(
        "--get", "-g",
        type=int,
        metavar="N",
        dest="get_clip",
        help="retrieve Nth clip from history (1 = most recent)",
    )

    p.add_argument(
        "--clear",
        nargs="?",
        const="all",
        default=None,
        metavar="SELECTOR",
        dest="clear_history",
        help=(
            "delete history entries. No argument clears all. "
            "Accepts indices (3), ranges (4:10), or combinations (2,4:10)"
        ),
    )

    p.add_argument(
        "--save", "-s",
        action="store_true",
        dest="save_clip",
        help="save current clipboard contents to history",
    )

    p.add_argument(
        "--config",
        action="store_true",
        dest="show_config",
        help="show current configuration",
    )

    p.add_argument(
        "--no-history",
        action="store_true",
        help="skip history save for this invocation",
    )

    p.add_argument(
        "--encrypt",
        action="store_true",
        help="enable encryption for clipboard history (requires teeclip[secure])",
    )

    p.add_argument(
        "--decrypt",
        action="store_true",
        help="disable encryption and decrypt existing history",
    )

    p.add_argument(
        "--version", "-V",
        action="version",
        version=f"teeclip {get_display_version()} ({__version__})",
    )

    return p


def main(argv=None):
    """Main entry point.

    Dispatch priority: config → clear → list → get → save → paste → tee.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Load config and apply CLI overrides
    from .config import load_config
    config = load_config()
    config = config.with_overrides(
        output_quiet=args.quiet or None,
        clipboard_backend=args.backend or None,
    )

    # --config: show effective configuration
    if args.show_config:
        _cmd_config(config)
        return

    # --encrypt / --decrypt
    if args.encrypt:
        _cmd_encrypt(config)
        return
    if args.decrypt:
        _cmd_decrypt(config)
        return

    # --clear: clear history (all or selective)
    if args.clear_history is not None:
        _cmd_clear(config, args.clear_history)
        return

    # --list [N]: show recent history (0 = use config default)
    if args.list_history is not None:
        count = args.list_history or config.history_list_count
        _cmd_list(config, count)
        return

    # --get N: retrieve clip by index
    if args.get_clip is not None:
        _cmd_get(config, args.get_clip, backend_name=args.backend)
        return

    # --save: save current clipboard to history
    if args.save_clip:
        _cmd_save(config, backend_name=args.backend)
        return

    # --paste mode: print clipboard to stdout
    if args.paste:
        from .clipboard import paste_from_clipboard, ClipboardError
        try:
            data = paste_from_clipboard(backend_name=args.backend)
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        except ClipboardError as e:
            print(f"teeclip: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Default mode: tee stdin to stdout + clipboard + history
    from .tee import tee_to_clipboard
    history_enabled = config.history_enabled and config.history_auto_save and not args.no_history
    tee_to_clipboard(
        files=args.files or None,
        append=args.append,
        backend_name=args.backend,
        quiet=config.output_quiet,
        no_clipboard=args.no_clipboard,
        save_history=history_enabled,
        config=config,
    )


def _cmd_config(config):
    """Show effective configuration."""
    from .config import format_config
    print(format_config(config))


def _cmd_list(config, limit):
    """Show recent clipboard history."""
    from .history import HistoryStore, _make_preview

    with HistoryStore(config=config) as store:
        total = store.count()

        if total == 0:
            print("(no history)")
            return

        entries = store.list_recent(limit=limit)

        # For OS auth, decrypt previews on the fly so --list is useful
        decrypt_key = None
        if (config.security_auth_method != "password"
                and any(e.encrypted for e in entries)):
            try:
                from .encryption import (
                    is_available, get_encryption_key,
                    decrypt as aes_decrypt,
                )
                if is_available():
                    decrypt_key = get_encryption_key(config, store)
            except Exception:
                pass  # fall back to showing "(encrypted)"

        for i, entry in enumerate(entries, 1):
            # Truncate timestamp to just date + time (drop timezone)
            ts = entry.timestamp
            if "T" in ts:
                ts = ts.split("T")[0] + " " + ts.split("T")[1][:8]

            preview = entry.preview or "(empty)"
            if entry.encrypted and decrypt_key is not None:
                try:
                    raw = store.get_clip(i)
                    if raw:
                        plaintext = aes_decrypt(raw, decrypt_key)
                        preview = _make_preview(
                            plaintext, config.history_preview_length
                        )
                except Exception:
                    pass  # keep "(encrypted)" on failure

            enc = " [E]" if entry.encrypted else "    "
            print(f"  {i:>3}  {ts}{enc}  {preview}")

        shown = len(entries)
        if shown < total:
            print(f"  ({shown} of {total} entries -- use --list all to see everything)")


def _cmd_get(config, index, backend_name=None):
    """Retrieve clip by 1-based index, write to stdout and clipboard."""
    from .history import HistoryStore

    with HistoryStore(config=config) as store:
        result = store.get_clip_entry(index)

        if result is None:
            print(f"teeclip: no clip at index {index}", file=sys.stderr)
            sys.exit(1)

        entry, content = result

        # Decrypt if needed
        if entry.encrypted:
            from .encryption import decrypt_single, EncryptionError
            try:
                content = decrypt_single(content, store, config=config)
            except EncryptionError as e:
                print(f"teeclip: {e}", file=sys.stderr)
                sys.exit(1)

    # Write to stdout
    sys.stdout.buffer.write(content)
    sys.stdout.buffer.flush()

    # Also copy to clipboard
    from .clipboard import copy_to_clipboard, ClipboardError
    try:
        copy_to_clipboard(content, backend_name=backend_name)
    except ClipboardError as e:
        if not config.output_quiet:
            print(f"\nteeclip: clipboard: {e}", file=sys.stderr)


def _cmd_save(config, backend_name=None):
    """Save current clipboard contents to history."""
    from .clipboard import paste_from_clipboard, ClipboardError
    from .history import HistoryStore

    try:
        data = paste_from_clipboard(backend_name=backend_name)
    except ClipboardError as e:
        print(f"teeclip: {e}", file=sys.stderr)
        sys.exit(1)

    if not data:
        print("teeclip: clipboard is empty", file=sys.stderr)
        return

    with HistoryStore(config=config) as store:
        clip_id = store.save(data, source="clipboard")

    if clip_id is not None:
        if not config.output_quiet:
            print(f"teeclip: saved to history ({len(data)} bytes)")
    else:
        if not config.output_quiet:
            print("teeclip: already in history (duplicate)")


def _cmd_clear(config, selector):
    """Clear clipboard history — all or selective.

    selector is "all" (no arg) or a string like "3", "4:10", "2,4:10".
    """
    from .history import HistoryStore

    if selector == "all":
        # Clear everything — prompt for confirmation if interactive
        if sys.stdin.isatty():
            try:
                answer = input("Clear all clipboard history? [y/N] ")
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if answer.lower() not in ("y", "yes"):
                return

        with HistoryStore(config=config) as store:
            count = store.clear()

        if not config.output_quiet:
            print(f"teeclip: cleared {count} entries")
        return

    # Selective deletion
    try:
        indices = parse_clear_selector(selector)
    except ValueError as e:
        print(f"teeclip: {e}", file=sys.stderr)
        sys.exit(1)

    with HistoryStore(config=config) as store:
        count = store.delete_by_indices(indices)

    if not config.output_quiet:
        print(f"teeclip: deleted {count} entries")


def parse_clear_selector(selector: str) -> list:
    """Parse a clear selector string into a sorted list of 1-based indices.

    Supports:
        "3"       → [3]
        "4:10"    → [4, 5, 6, 7, 8, 9, 10]
        "2,4:10"  → [2, 4, 5, 6, 7, 8, 9, 10]
        "1,3,5"   → [1, 3, 5]

    Raises ValueError on invalid syntax.
    """
    indices = set()
    for part in selector.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            pieces = part.split(":", 1)
            try:
                start = int(pieces[0])
                end = int(pieces[1])
            except ValueError:
                raise ValueError(
                    f"invalid range: '{part}' (expected START:END)"
                )
            if start < 1 or end < 1:
                raise ValueError(
                    f"indices must be positive: '{part}'"
                )
            if start > end:
                raise ValueError(
                    f"invalid range: '{part}' (start > end)"
                )
            indices.update(range(start, end + 1))
        else:
            try:
                idx = int(part)
            except ValueError:
                raise ValueError(
                    f"invalid index: '{part}' (expected a number)"
                )
            if idx < 1:
                raise ValueError(
                    f"indices must be positive: '{part}'"
                )
            indices.add(idx)

    if not indices:
        raise ValueError("empty selector")

    return sorted(indices)


def _cmd_encrypt(config):
    """Enable encryption for clipboard history."""
    from .encryption import (
        is_available, EncryptionError,
        prompt_password, encrypt_history,
    )
    from .history import HistoryStore

    if not is_available():
        print(
            "teeclip: encryption requires the 'cryptography' package.\n"
            "Install it with: pip install teeclip[secure]",
            file=sys.stderr,
        )
        sys.exit(1)

    password = None
    if config.security_auth_method == "password":
        try:
            password = prompt_password(confirm=True)
        except EncryptionError as e:
            print(f"teeclip: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        with HistoryStore(config=config) as store:
            count = encrypt_history(store, password=password, config=config)
    except EncryptionError as e:
        print(f"teeclip: {e}", file=sys.stderr)
        sys.exit(1)

    if not config.output_quiet:
        print(f"teeclip: encrypted {count} clips")
        if config.security_auth_method != "password":
            print("teeclip: using OS session key (no password needed)")
        print("teeclip: new clips will be encrypted automatically")


def _cmd_decrypt(config):
    """Disable encryption and decrypt existing history."""
    from .encryption import (
        is_available, EncryptionError,
        prompt_password, decrypt_history,
    )
    from .history import HistoryStore

    if not is_available():
        print(
            "teeclip: decryption requires the 'cryptography' package.\n"
            "Install it with: pip install teeclip[secure]",
            file=sys.stderr,
        )
        sys.exit(1)

    password = None
    if config.security_auth_method == "password":
        try:
            password = prompt_password(confirm=False)
        except EncryptionError as e:
            print(f"teeclip: {e}", file=sys.stderr)
            sys.exit(1)

    with HistoryStore(config=config) as store:
        try:
            count = decrypt_history(store, password=password, config=config)
        except EncryptionError as e:
            print(f"teeclip: {e}", file=sys.stderr)
            sys.exit(1)

    if not config.output_quiet:
        print(f"teeclip: decrypted {count} clips")


if __name__ == "__main__":
    main()
