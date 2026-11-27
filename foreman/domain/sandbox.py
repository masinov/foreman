"""What a sandboxed step may reach (the policy; ``runner.sandbox`` enforces it)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


#: The flag under ``[agent.flags]`` with which a ``sandbox`` role on Codex
#: accepts that Codex's sandbox leaves reads of the home directory open. It is
#: Foreman's, never passed to a backend's command line.
ACCEPT_OPEN_READS_FLAG = "accept_open_reads"


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
    #: The step's own temporary directory, made for it and removed with the
    #: sandbox: its commands' ``TMPDIR`` and Claude Code's, instead of the
    #: per-user directory every session shares. Short, under ``/tmp``: Claude
    #: Code puts its proxy's unix sockets there, and a socket path is limited
    #: to 108 bytes (a directory in the clone was too long; seen 2026-11-27).
    temp_dir: Path | None = None
