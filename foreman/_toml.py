"""TOML loading helpers with Python 3.10 compatibility."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10.
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover - fallback for repo validation installs.
        from pip._vendor import tomli as tomllib  # type: ignore[no-redef]


def load_toml_file(path: str | Path) -> dict[str, Any]:
    """Load one TOML file into a dictionary."""

    with Path(path).open("rb") as handle:
        return tomllib.load(handle)
