"""
Core tee-to-clipboard logic.

Reads stdin, writes to stdout (pass-through), and copies the full
content to the system clipboard on EOF. Optionally writes to files
like standard `tee`.
"""

import sys

from .clipboard import copy_to_clipboard, ClipboardError


def tee_to_clipboard(
    files=None,
    append=False,
    backend_name=None,
    quiet=False,
    no_clipboard=False,
):
    """
    Read stdin, write to stdout and clipboard.

    Args:
        files: Optional list of file paths to also write to (like tee).
        append: If True, append to files instead of overwriting.
        backend_name: Force a specific clipboard backend.
        quiet: Suppress warning messages.
        no_clipboard: Skip clipboard (useful for testing file-only tee).
    """
    # Open output files if specified
    file_handles = []
    if files:
        mode = "ab" if append else "wb"
        for path in files:
            try:
                file_handles.append(open(path, mode))
            except OSError as e:
                print(f"teeclip: {path}: {e}", file=sys.stderr)

    # Read stdin in binary mode, pass through to stdout, buffer for clipboard
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    chunks = []

    try:
        while True:
            chunk = stdin.read(8192)
            if not chunk:
                break

            # Pass through to stdout immediately
            stdout.write(chunk)
            stdout.flush()

            # Write to any output files
            for fh in file_handles:
                fh.write(chunk)

            # Buffer for clipboard
            if not no_clipboard:
                chunks.append(chunk)

    except KeyboardInterrupt:
        # Ctrl+C — still try to copy what we have so far
        pass
    except BrokenPipeError:
        # Downstream pipe closed (e.g., `teeclip | head`)
        # Still copy what we buffered
        pass
    finally:
        # Close file handles
        for fh in file_handles:
            try:
                fh.close()
            except OSError:
                pass

    # Copy buffered content to clipboard
    if not no_clipboard and chunks:
        data = b"".join(chunks)
        try:
            copy_to_clipboard(data, backend_name=backend_name)
        except ClipboardError as e:
            if not quiet:
                print(f"teeclip: clipboard: {e}", file=sys.stderr)
