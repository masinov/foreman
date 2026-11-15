"""Environment resolution helpers for native agent runners."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import os

from .base import PreflightError


#: Host variables an agent process is started with. Everything else in the
#: engine's environment (tokens for the dashboard, the forge, cloud accounts,
#: an SSH agent) stays with the engine. A role names what else it needs in
#: ``[agent.env]``; a project in the ``agent_env_passthrough`` setting. ADR-0023.
AGENT_ENV_NAMES: frozenset[str] = frozenset(
    {
        "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "COLORTERM",
        "LANG", "LANGUAGE", "TZ", "TMPDIR", "TEMP", "TMP",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS",
        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "no_proxy", "all_proxy",
    }
)
#: Prefixes of host variables an agent process is started with: locale and
#: per-user directories, and the two backends' own configuration and keys.
AGENT_ENV_PREFIXES: tuple[str, ...] = ("LC_", "XDG_", "ANTHROPIC_", "CLAUDE_", "OPENAI_", "CODEX_")


def agent_environment(
    extra: Mapping[str, str] | None = None,
    *,
    host: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The whole environment for one agent process.

    The host variables on the list above, then ``extra`` (the engine's own
    additions and the role's ``[agent.env]``) over them.
    """

    source = os.environ if host is None else host
    environment = {
        name: value
        for name, value in source.items()
        if name in AGENT_ENV_NAMES or name.startswith(AGENT_ENV_PREFIXES)
    }
    environment.update(extra or {})
    return environment


def passthrough_env(names: Iterable[str], *, host: Mapping[str, str] | None = None) -> dict[str, str]:
    """The host's values for the variables a project asks to pass through."""

    source = os.environ if host is None else host
    return {name: source[name] for name in names if name in source}


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
