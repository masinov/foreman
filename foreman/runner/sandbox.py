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
from dataclasses import replace
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ..domain.sandbox import SandboxPolicy
from .base import PreflightError

#: What a machine needs for Claude Code's sandbox on Linux.
SANDBOX_PROGRAMS: tuple[str, ...] = ("bwrap", "socat")

#: Environment variables a sandboxed command never sees: the backends' own keys.
CREDENTIAL_ENV_PREFIXES: tuple[str, ...] = (
    "ANTHROPIC_", "OPENAI_", "CODEX_", "CLAUDE_CODE_OAUTH",
)


def claude_temp_dir(uid: int | None = None) -> Path:
    """Claude Code's per-user temporary directory, shared by every session of the user.

    It holds every other session's temporary files and scratch work, the
    operator's own included. A sandboxed step is given a temporary directory
    inside its clone instead (``TMPDIR`` and ``CLAUDE_CODE_TMPDIR``), and this
    one is closed to it.
    """

    return Path(f"/tmp/claude-{os.getuid() if uid is None else uid}")


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


def _is_real_directory(path: Path) -> bool:
    """A directory that is not a link; an entry that cannot be examined is not one."""

    try:
        return path.is_dir() and not path.is_symlink()
    except OSError:
        return False


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
    roots = [_resolved(root) for root in deny_roots]
    # A root inside another is covered by it: listed once, not twice.
    roots = [
        root for index, root in enumerate(roots)
        if root not in roots[:index]
        and not any(other != root and _inside(root, other) for other in roots)
    ]

    def walk(directory: Path) -> None:
        try:
            children = sorted(directory.iterdir())
        except OSError:
            return
        for child in children:
            if any(_inside(child, allow) for allow in allowed):
                continue
            holds_allowed = any(_inside(allow, child) for allow in allowed)
            if holds_allowed and _is_real_directory(child):
                walk(child)
            else:
                closed.append(child)

    for root in roots:
        if not any(_inside(allow, root) for allow in allowed):
            # Nothing inside it is opened: one rule closes it whole, and
            # what is created in it later is closed too.
            closed.append(root)
        elif _is_real_directory(root):
            walk(root)
    return tuple(closed)


#: Where the host keeps sockets that reach more than a program: the session bus
#: and the init system (``/run``), the container engine, a user's ssh agent and
#: X server (``/tmp``).
SOCKET_DIRECTORIES: tuple[str, ...] = ("/run", "/tmp", "/var/tmp")


def socket_policy(policy: SandboxPolicy, *, uid: int | None = None) -> SandboxPolicy:
    """``policy`` with the host's socket directories closed, for a step that may create sockets.

    Creating unix sockets is blocked in the sandbox unless the project allows
    it (``sandbox_allow_unix_sockets``, for a browser's profile lock). Allowed,
    a command can connect to any socket it can see, and file permissions are
    the only wall: a session bus or a container engine is an escape (checked
    on 2026-11-27: the user's session bus was reachable). So ``/run`` and the
    temporary directories are closed to it, except what Claude Code's own
    sandbox needs, which is in the step's own temporary directory
    (``SandboxPolicy.temp_dir``). Nothing under them is opened again: ``/run/user/<uid>/cc-socks``
    holds the messaging sockets of the operator's own Claude Code sessions
    (checked on 2026-11-27), and ``/tmp/claude-<uid>`` every session's files.
    A socket file cannot be hidden by itself, a directory can.
    """

    del uid  # kept for callers; nothing per user is opened any more
    roots = tuple(Path(name) for name in SOCKET_DIRECTORIES if Path(name).is_dir())
    return replace(policy, deny_roots=(*policy.deny_roots, *roots))


def _read_rule(path: Path) -> str:
    # An absolute path in a rule takes two slashes; one is relative to the project.
    suffix = "/**" if _is_real_directory(path) else ""
    return f"Read(/{path}{suffix})"


def claude_settings(policy: SandboxPolicy) -> dict[str, Any]:
    """The Claude Code settings that sandbox a step to ``policy``.

    ``failIfUnavailable`` and ``allowUnsandboxedCommands = false``: the step
    never runs a command outside the sandbox, nor without one. Reads of the
    closed directories are denied to commands by the sandbox itself, with the
    allowed paths opened inside them, and to the Read, Grep and Glob tools
    (which the sandbox does not cover) by permission rules.
    """

    if policy.allow_unix_sockets:
        policy = socket_policy(policy)
    # The shared per-user temporary directory of Claude Code is always closed;
    # the step has one of its own (``SandboxPolicy.temp_dir``).
    policy = replace(policy, deny_roots=(*policy.deny_roots, claude_temp_dir()))
    if policy.temp_dir is not None:
        policy = replace(policy, read_paths=(*policy.read_paths, policy.temp_dir))
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
    if policy.allow_unix_sockets:
        sandbox["network"]["allowAllUnixSockets"] = True
    rules = [
        _read_rule(path) for path in closed_paths(policy.deny_roots, policy.read_paths)
    ]
    # No hook runs, the operator's or a branch's: a hook is a command Claude
    # Code runs itself, outside the sandbox, as the operator (a branch under
    # review could commit one in .claude/settings.json; seen on 2026-11-27).
    # The runner also loads no project settings (``--setting-sources user``).
    return {"disableAllHooks": True, "sandbox": sandbox, "permissions": {"deny": rules}}


def sandboxed_process_env(policy: SandboxPolicy) -> dict[str, str]:
    """The environment that gives a sandboxed step its own temporary directory.

    Claude Code puts its sandbox's temporary directory, its proxy's sockets
    and the commands' ``TMPDIR`` under ``TMPDIR``/``CLAUDE_CODE_TMPDIR``
    (``/tmp`` by default, so the shared ``/tmp/claude-<uid>``). Pointed at the
    step's own directory, its temporary files go with the sandbox.
    """

    if policy.temp_dir is None:
        return {}
    return {"TMPDIR": str(policy.temp_dir), "CLAUDE_CODE_TMPDIR": str(policy.temp_dir)}


def host_environment_names(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Credential variable names in ``env`` (the process environment by default)."""

    return credential_env_names(os.environ if env is None else env)
