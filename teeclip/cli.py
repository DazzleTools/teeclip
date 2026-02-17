"""
Command-line interface for teeclip.

Usage:
    my-command | teeclip              # stdout + clipboard
    my-command | teeclip -a log.txt   # stdout + clipboard + append to file
    my-command | teeclip output.txt   # stdout + clipboard + write to file
    teeclip --paste                   # print current clipboard to stdout
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

    p.add_argument(
        "--version", "-V",
        action="version",
        version=f"teeclip {get_display_version()} ({__version__})",
    )

    return p


def main(argv=None):
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

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

    # Default mode: tee stdin to stdout + clipboard
    from .tee import tee_to_clipboard
    tee_to_clipboard(
        files=args.files or None,
        append=args.append,
        backend_name=args.backend,
        quiet=args.quiet,
        no_clipboard=args.no_clipboard,
    )


if __name__ == "__main__":
    main()
