"""Command-line interface for the Foreman package.

`parser` builds the argument parser and holds `main`. Each group of commands
lives in its own module with its handlers and a `register_<command>` function
that adds it to the parser; `common` holds what they share.
"""

from __future__ import annotations

from .parser import build_parser, main

__all__ = ["build_parser", "main"]
