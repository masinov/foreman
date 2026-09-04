"""Reading and steering the resident engine, from any surface.

Three consumers ask the same questions about a project's engine — the CLI
(``foreman engine status``), the dashboard API, and, later, the intake API:

* is an engine resident on this project, whose is it, and how fresh is its
  heartbeat,
* is it paused,
* what is it working on, and what has it been told to do lately,
* and, when a *blocked* task shows up, who blocked it: a human gate waiting for
  a decision, or the engine itself giving up on the task.

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
from typing import Callable, Iterable, Sequence

from .context import context_directory
from .models import EngineCommand, EngineLockView, Project, Task
from .store import ForemanStore

__all__ = [
    "BLOCKED_KINDS",
    "EngineStateView",
    "HUMAN_GATE_BLOCKED_REASON",
    "HUMAN_GATE_ROLE",
    "SERVE_LOG_NAME",
    "ServeSpawn",
    "ServeSpawner",
    "WorkflowGateSteps",
    "blocked_kind",
    "blocked_kind_counts",
    "default_command_requester",
    "describe_engine",
    "engine_is_paused",
    "resolve_gate_steps",
    "serve_log_path",
    "spawn_serve",
]

#: The workflow role that marks a step as a human decision point.
HUMAN_GATE_ROLE = "_builtin:human_gate"

#: The reason ``_builtin:human_gate`` writes when it parks a task. Used only as
#: a tie-breaker when the workflow definition cannot answer.
HUMAN_GATE_BLOCKED_REASON = "Awaiting human approval"

#: The two ways a task ends up ``blocked``. ``gate`` is waiting for a person and
#: is resolved with ``foreman approve``/``deny``; ``engine`` is the engine's
#: dead-letter state (loop limit, unhandled outcome, cost or time gate, branch
#: violation, failure isolation, ``stop_task``) and is resolved with
#: ``foreman task unblock`` or by editing the task.
BLOCKED_KINDS: tuple[str, ...] = ("gate", "engine")

#: Filename of the detached ``foreman serve`` log inside the context directory.
SERVE_LOG_NAME = "serve.log"

#: How many commands the engine views carry by default.
DEFAULT_COMMAND_LIMIT = 10

#: How far back :func:`engine_is_paused` looks for the last applied
#: pause/resume. A project that has taken more commands than this since it was
#: last paused is not paused in any sense an operator cares about.
PAUSE_LOOKBACK_COMMANDS = 200


# ── Dead-letter classification ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WorkflowGateSteps:
    """Which steps of one workflow are human gates.

    ``step_ids`` is ``None`` when the workflow could not be loaded at all (a
    missing or broken TOML file, or a project pointing at a workflow that no
    longer exists). Keeping that distinct from "loaded, and has no gate steps"
    is what lets :func:`blocked_kind` fall back to the gate builtin's own
    blocked reason instead of silently calling every gated task an engine
    failure.
    """

    step_ids: frozenset[str] | None
    gate_step_ids: frozenset[str] = frozenset()

    @property
    def loaded(self) -> bool:
        """True when a workflow definition backed this answer."""

        return self.step_ids is not None


#: Used when no workflow could be resolved for a project.
UNKNOWN_WORKFLOW = WorkflowGateSteps(step_ids=None)


def resolve_gate_steps(workflow_id: str | None) -> WorkflowGateSteps:
    """Return the human-gate steps of one workflow, tolerating load failures.

    A workflow that will not load must not take a dashboard or a board listing
    down with it, so every failure resolves to :data:`UNKNOWN_WORKFLOW`.
    """

    if not workflow_id:
        return UNKNOWN_WORKFLOW

    from .roles import load_roles
    from .workflows import load_workflows

    try:
        roles = load_roles()
        workflows = load_workflows(
            available_role_ids=set(roles),
            role_outcomes={
                role_id: role.completion.outcomes for role_id, role in roles.items()
            },
        )
    except Exception:  # noqa: BLE001 - a broken definition must not hide tasks
        return UNKNOWN_WORKFLOW

    workflow = workflows.get(workflow_id)
    if workflow is None:
        return UNKNOWN_WORKFLOW
    return WorkflowGateSteps(
        step_ids=frozenset(step.id for step in workflow.steps),
        gate_step_ids=frozenset(
            step.id for step in workflow.steps if step.role == HUMAN_GATE_ROLE
        ),
    )


def blocked_kind(task: Task, gates: WorkflowGateSteps) -> str | None:
    """Classify why a task is blocked, or return None when it is not blocked.

    The task's persisted step decides: a step the project's workflow runs with
    ``_builtin:human_gate`` is a ``gate``, and anything else is the engine's
    dead-letter state. A persisted step alone is not enough — the engine also
    persists a resume point when it blocks a task after a failure — so the step
    has to be looked up in the workflow rather than merely be present.
    """

    if task.status != "blocked":
        return None
    step = task.workflow_current_step
    if step and gates.step_ids is not None and step in gates.step_ids:
        return "gate" if step in gates.gate_step_ids else "engine"
    # No usable step: the gate builtin's own reason is the only signal left.
    return "gate" if (task.blocked_reason or "") == HUMAN_GATE_BLOCKED_REASON else "engine"


def blocked_kind_counts(
    tasks: Iterable[Task], gates: WorkflowGateSteps
) -> dict[str, int]:
    """Count blocked tasks by kind. Keys are always present, even at zero."""

    counts = {kind: 0 for kind in BLOCKED_KINDS}
    for task in tasks:
        kind = blocked_kind(task, gates)
        if kind is not None:
            counts[kind] += 1
    return counts


# ── Engine state ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EngineStateView:
    """What is known about one project's engine right now.

    ``resident`` means a live lease is held; ``paused`` is derived from the
    command log rather than from the engine's memory, because the flag lives in
    a process nobody else can read.
    """

    project_id: str
    resident: bool
    paused: bool
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
        """One word for the header: ``resident``, ``paused``, or ``stopped``."""

        if not self.resident:
            return "stopped"
        return "paused" if self.paused else "resident"


def engine_is_paused(store: ForemanStore, project_id: str) -> bool:
    """True when the last applied pause/resume for a project was a pause.

    ``foreman serve`` keeps the paused flag in memory, so the command log is
    the only place another process can read it from: the most recent *applied*
    ``pause``/``shutdown``/``resume`` is the engine's current intent.
    """

    for command in store.list_engine_commands(
        project_id, limit=PAUSE_LOOKBACK_COMMANDS
    ):
        if command.status != "completed":
            continue
        if command.command in {"pause", "shutdown"}:
            return command.command == "pause"
        if command.command == "resume":
            return False
    return False


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
        paused=engine_is_paused(store, project_id),
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
    engine by killing it; ``pause`` and ``shutdown`` commands do that.
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
