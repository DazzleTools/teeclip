"""
teeclip - Cross-platform tee-to-clipboard CLI with history management.

Like Unix `tee`, but for the clipboard. Pipe any command's output to both
stdout and the system clipboard simultaneously.

Usage:
    my-command | teeclip          # stdout + clipboard
    my-command | teeclip -a log   # stdout + clipboard + append to file
    teeclip --paste               # print clipboard contents
    teeclip --list                # show clipboard history
"""

from ._version import __version__, get_version, get_base_version, VERSION, BASE_VERSION

__all__ = [
    "__version__",
    "get_version",
    "get_base_version",
    "VERSION",
    "BASE_VERSION",
]
