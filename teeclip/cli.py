"""
Command-line interface for teeclip.

Usage:
    my-command | teeclip              # stdout + clipboard + history
    my-command | teeclip -a log.txt   # stdout + clipboard + append to file
    my-command | teeclip output.txt   # stdout + clipboard + write to file
    teeclip --paste                   # print current clipboard to stdout
    teeclip --list                    # show recent clipboard history
    teeclip --get 1                   # retrieve most recent clip
    teeclip --version                 # show version
"""

import argparse
import sys

from ._version import __version__, get_display_version


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
            "  teeclip --get 1                   # retrieve most recent clip\n"
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
        action="store_true",
        dest="list_history",
        help="show recent clipboard history",
    )

    p.add_argument(
        "--list-count",
        type=int,
        default=10,
        metavar="N",
        help="number of entries to show with --list (default: 10)",
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
        action="store_true",
        dest="clear_history",
        help="clear all clipboard history",
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

    # --clear: clear history
    if args.clear_history:
        _cmd_clear(config)
        return

    # --list: show recent history
    if args.list_history:
        _cmd_list(config, args.list_count)
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
        entries = store.list_recent(limit=limit)

        if not entries:
            print("(no history)")
            return

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

            encrypted_marker = " [encrypted]" if entry.encrypted else ""
            print(f"  {i:>3}  {ts}  {preview}{encrypted_marker}")


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


def _cmd_clear(config):
    """Clear all clipboard history."""
    # Prompt for confirmation if running interactively
    if sys.stdin.isatty():
        try:
            answer = input("Clear all clipboard history? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer.lower() not in ("y", "yes"):
            return

    from .history import HistoryStore

    with HistoryStore(config=config) as store:
        count = store.clear()

    if not config.output_quiet:
        print(f"teeclip: cleared {count} entries")


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
