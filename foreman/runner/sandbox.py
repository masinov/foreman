"""What a sandboxed step may reach, and the Claude Code settings that enforce it.

A step with ``run_scope = "sandbox"`` (the code reviewer) runs as the operator
with a shell. Foreman does not build a container of its own for it: it uses the
backend's sandbox (ADR new-claude-code-sandbox, amending ADR-0041 section 5).
This module holds the policy, in terms of paths and hosts, and turns it into
what Claude Code is given with ``--settings``.

What the policy closes:

* **Writes**: everywhere but the step's own working copy (Claude Code's
  default for its sandbox; the working copy is a clone, so its git refs and
  config are its own).
* **The network**: every host but the ones the project lists. ``localhost``
  works, which the project's screenshot script needs.
* **Reads**: the operator's home directory and the directory the repository
  sits in (so other projects), except the paths the step needs.
* **The backend's own keys** (``ANTHROPIC_*``, ``OPENAI_*``) in the step's
  environment, from the commands it runs.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .base import PreflightError, SandboxPolicy

#: What a machine needs for Claude Code's sandbox on Linux.
SANDBOX_PROGRAMS: tuple[str, ...] = ("bwrap", "socat")

#: Environment variables a sandboxed command never sees: the backends' own keys.
CREDENTIAL_ENV_PREFIXES: tuple[str, ...] = ("ANTHROPIC_", "OPENAI_", "CLAUDE_CODE_OAUTH")


def credential_env_names(env: Mapping[str, str]) -> tuple[str, ...]:
    """The names in ``env`` that hold a backend's keys, sorted."""

    return tuple(
        sorted(name for name in env if name.upper().startswith(CREDENTIAL_ENV_PREFIXES))
    )


def missing_programs(which: Any = shutil.which) -> tuple[str, ...]:
    """The programs Claude Code's sandbox needs that this machine lacks."""

    return tuple(program for program in SANDBOX_PROGRAMS if which(program) is None)


def check_machine(which: Any = shutil.which) -> None:
    """Raise ``PreflightError`` naming what the sandbox needs when it is not installed.

    A sandboxed step never runs without its sandbox: Claude Code is also told
    to fail when it cannot start one (``failIfUnavailable``).
    """

    missing = missing_programs(which)
    if missing:
        raise PreflightError(
            "The sandbox cannot start on this machine: "
            f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not installed. "
            "A step that must be sandboxed is never run without it. "
            "Install them (Ubuntu: sudo apt install bubblewrap socat) and run the step again."
        )


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def closed_paths(
    deny_roots: Iterable[Path], read_paths: Iterable[Path]
) -> tuple[Path, ...]:
    """The paths to refuse so that each root is closed except ``read_paths``.

    Claude Code's permission rules (which govern the Read, Grep and Glob
    tools) have no exception inside a denied directory: a deny rule wins. So
    the directories are listed entry by entry: an entry that is, or lies
    inside, an allowed path is left out; one that holds an allowed path is
    descended into; any other is closed whole. Symbolic links are never
    followed, so a link is closed (or left) as a file.
    """

    allowed = [_resolved(path) for path in read_paths]
    closed: list[Path] = []

    def walk(directory: Path) -> None:
        try:
            children = sorted(directory.iterdir())
        except OSError:
            return
        for child in children:
            if any(_inside(child, allow) for allow in allowed):
                continue
            holds_allowed = any(_inside(allow, child) for allow in allowed)
            if holds_allowed and child.is_dir() and not child.is_symlink():
                walk(child)
            else:
                closed.append(child)

    for root in deny_roots:
        resolved = _resolved(root)
        if resolved.is_dir():
            walk(resolved)
    return tuple(closed)


def _read_rule(path: Path) -> str:
    # An absolute path in a rule takes two slashes; one is relative to the project.
    suffix = "/**" if path.is_dir() and not path.is_symlink() else ""
    return f"Read(/{path}{suffix})"


def claude_settings(policy: SandboxPolicy) -> dict[str, Any]:
    """The Claude Code settings that sandbox a step to ``policy``.

    ``failIfUnavailable`` and ``allowUnsandboxedCommands = false``: the step
    never runs a command outside the sandbox, nor without one. Reads of the
    closed directories are denied to commands by the sandbox itself, with the
    allowed paths opened inside them, and to the Read, Grep and Glob tools
    (which the sandbox does not cover) by permission rules.
    """

    deny_roots = [str(root) for root in policy.deny_roots]
    allow_read = [str(path) for path in policy.read_paths]
    sandbox: dict[str, Any] = {
        "enabled": True,
        "failIfUnavailable": True,
        "allowUnsandboxedCommands": False,
        "autoAllowBashIfSandboxed": True,
        "filesystem": {"denyRead": deny_roots, "allowRead": allow_read},
        "network": {
            "allowedDomains": list(policy.allowed_hosts),
            "strictAllowlist": True,
        },
    }
    rules = [
        _read_rule(path) for path in closed_paths(policy.deny_roots, policy.read_paths)
    ]
    return {"sandbox": sandbox, "permissions": {"deny": rules}}


def host_environment_names(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Credential variable names in ``env`` (the process environment by default)."""

    return credential_env_names(os.environ if env is None else env)
