"""Environment resolution helpers for native agent runners."""

from __future__ import annotations

from collections.abc import Mapping
import os

from .base import PreflightError


def resolve_env(spec: Mapping[str, str]) -> dict[str, str]:
    """Resolve declarative role environment values for one runner invocation.

    Supported values:
    - ``literal`` -> used as-is
    - ``env:NAME`` -> value from the host environment, required
    - ``env:NAME?fallback`` -> value from the host environment or fallback

    Keys ending in ``_DIR`` or ``_PATH`` are passed through ``expanduser`` so
    role examples can use stable home-relative config directories.
    """

    resolved: dict[str, str] = {}
    for key, raw_value in spec.items():
        value = _resolve_value(key, raw_value)
        if key.endswith(("_DIR", "_PATH")):
            value = os.path.expanduser(value)
        resolved[key] = value
    return resolved


def _resolve_value(key: str, raw_value: str) -> str:
    if not raw_value.startswith("env:"):
        return raw_value

    env_spec = raw_value.removeprefix("env:")
    name, separator, fallback = env_spec.partition("?")
    if not name:
        raise PreflightError(f"Invalid environment reference for {key}: missing variable name.")

    value = os.environ.get(name)
    if value is not None:
        return value
    if separator:
        return fallback
    raise PreflightError(f"Missing required environment variable {name} for {key}.")
