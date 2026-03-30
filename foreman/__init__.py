"""Foreman package bootstrap."""

from __future__ import annotations

__all__ = ["__version__", "get_version"]

__version__ = "0.1.0"


def get_version() -> str:
    """Return the installed Foreman package version."""

    return __version__
