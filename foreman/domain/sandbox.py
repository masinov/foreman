"""What a sandboxed step may reach (the policy; ``runner.sandbox`` enforces it)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """The reach of one sandboxed step (see ``runner.sandbox`` for what enforces it)."""

    #: Hosts the step may reach (names or ``*.example.com``); none by default.
    allowed_hosts: tuple[str, ...] = ()
    #: Directories closed to reads, each except what ``read_paths`` names inside it.
    deny_roots: tuple[Path, ...] = ()
    #: What stays readable inside the closed directories: the step's own
    #: working copy, the repository objects it reads, its toolchain.
    read_paths: tuple[Path, ...] = ()
    #: Whether commands may create unix sockets, which a browser needs for its
    #: own profile lock. Off by default: it lets a command connect to any
    #: socket it can see, so the sockets of the host are closed to it (see
    #: ``runner.sandbox.host_sockets``).
    allow_unix_sockets: bool = False
