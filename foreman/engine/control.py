"""Reading and steering the resident engine, from any surface.

Three consumers ask the same questions about a project's engine — the CLI
(``foreman engine status``), the dashboard API, and, later, the intake API:

* is an engine resident on this project, whose is it, and how fresh is its
  heartbeat,
* and what is it working on, and what has it been told to do lately.

Whether the work may go on is not the engine's state: it is a user's holds
on the work (ADR-0043, ``foreman.domain.holds``).

Who blocked a blocked task (a human gate, or the engine) is answered by
``foreman.definitions.layers.gate_steps``.

Answering those in each surface separately is how two surfaces come to disagree
about the same database. They live here instead, as pure read-side derivations
over :class:`~foreman.store.ForemanStore`, plus the one write-side helper that
is not a plain store call: spawning a local ``foreman serve`` when nothing is
resident yet.

Nothing here holds a process handle. Control of a resident engine goes through
the ``engine_commands`` table (see ADR-0002 and MANUAL §23); the local spawn
below is only the bootstrap for the single-machine case, where there is no
engine yet to send a command to.
"""

from __future__ import annotations

import getpass
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from ..repo.context import context_directory
from ..domain.models import EngineCommand, EngineLockView, Project, Task
from ..store import ForemanStore

__all__ = [
    "EngineStateView",
    "SERVE_LOG_NAME",
    "ServeSpawn",
    "ServeSpawner",
    "default_command_requester",
    "describe_engine",
    "running_task",
    "serve_command",
    "serve_log_path",
    "spawn_serve",
]

#: Filename of the detached ``foreman serve`` log inside the context directory.
SERVE_LOG_NAME = "serve.log"

# ── Engine state ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EngineStateView:
    """What is known about one project's engine right now.

    ``resident`` means a live lease is held.
    """

    project_id: str
    resident: bool
    lock: EngineLockView | None = None
    lease_expired: bool = False
    heartbeat_age_seconds: float | None = None
    current_task: Task | None = None
    commands: tuple[EngineCommand, ...] = field(default_factory=tuple)

    @property
    def holder_id(self) -> str | None:
        """Identifier of the engine holding the lock, if any."""

        return self.lock.holder_id if self.lock is not None else None

    @property
    def state(self) -> str:
        """One word for the header: ``resident`` or ``stopped``."""

        return "resident" if self.resident else "stopped"


def running_task(store: ForemanStore, project_id: str) -> Task | None:
    """Return the task whose run is currently in flight, if any.

    A ``running`` run is a stronger signal than an ``in_progress`` task: a task
    keeps that status across an engine restart, while a run is only ``running``
    while an agent step is actually executing.
    """

    runs = store.list_runs(project_id=project_id, status="running")
    for run in reversed(runs):
        task = store.get_task(run.task_id)
        if task is not None:
            return task
    return None


def describe_engine(
    store: ForemanStore,
    project_id: str,
    *,
    command_limit: int = 0,
    now: datetime | None = None,
) -> EngineStateView:
    """Assemble the engine view for one project.

    ``command_limit`` of zero skips the command listing, for callers (the
    project cards) that only need residency.
    """

    moment = now or datetime.now(timezone.utc)
    lock = store.get_engine_lock(project_id)
    commands: tuple[EngineCommand, ...] = ()
    if command_limit > 0:
        commands = tuple(store.list_engine_commands(project_id, limit=command_limit))
    return EngineStateView(
        project_id=project_id,
        resident=lock is not None,
        lock=lock,
        lease_expired=lock.is_expired(moment) if lock is not None else False,
        heartbeat_age_seconds=(
            lock.heartbeat_age_seconds(moment) if lock is not None else None
        ),
        current_task=running_task(store, project_id),
        commands=commands,
    )


def default_command_requester() -> str:
    """Name to record on a command when the caller did not name themselves.

    Commands are an audit trail — "who stopped this task" is the first question
    anyone asks — so the requester is never left blank. The OS user name is the
    best answer available from a terminal; a container without a resolvable
    user falls back to a literal rather than failing the command.
    """

    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - no passwd entry, no USER, no LOGNAME
        return "unknown"


# ── Local serve bootstrap ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ServeSpawn:
    """The result of starting a local ``foreman serve``."""

    pid: int
    command: tuple[str, ...]
    log_path: str


#: A spawner takes the argv of a ``foreman serve`` and the log file it should
#: write to, and returns the started process. Injected so callers (and tests)
#: can substitute a recorder for a real fork.
ServeSpawner = Callable[[Sequence[str], Path], ServeSpawn]


def serve_log_path(project: Project) -> Path:
    """Where a locally spawned engine writes its stdout and stderr.

    Inside the project's context directory: it is already the runtime,
    gitignored, per-project scratch space, and an operator looking for "what
    did the engine say" looks there first.
    """

    return context_directory(project) / SERVE_LOG_NAME


def serve_command(project_id: str, db_path: str) -> tuple[str, ...]:
    """Argv for a resident engine on one project, using this interpreter's CLI."""

    foreman_bin = str(Path(sys.executable).parent / "foreman")
    return (foreman_bin, "serve", project_id, "--db", db_path)


def spawn_serve(command: Sequence[str], log_path: Path) -> ServeSpawn:
    """Start a detached ``foreman serve``, appending its output to ``log_path``.

    Detached deliberately: the engine outlives the dashboard request that
    started it, and — with its own session — outlives the dashboard process
    too. Nothing keeps the handle, because nothing is allowed to steer the
    engine by killing it; a ``shutdown`` command ends it, and a user's holds
    stop the work (ADR-0043).
    """

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab") as log_file:
        process = subprocess.Popen(  # noqa: S603 - argv is built, not shell
            list(command),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    return ServeSpawn(pid=process.pid, command=tuple(command), log_path=str(log_path))
