"""The resident engine: `foreman serve`.

``foreman run`` is a one-shot pass. It exits the moment no runnable task is
left, so work that arrives afterwards — from the dashboard, from the CLI, from
the intake API — waits until a person presses Run again. ``foreman serve`` is
the same engine kept resident: it runs a pass, and when the pass has nothing to
do it sleeps until the database changes or the poll interval elapses, then runs
another one.

Three properties make it safe to leave running unattended:

* **One engine per project.** The whole loop runs inside an
  :class:`~foreman.engine_lock.EngineLock`, so a second ``serve`` or a
  ``run`` on the same project is refused rather than allowed to race.
* **A failed task cannot stop the service.** A task whose execution raises is
  parked as ``blocked`` with an attention turn and the loop continues after a
  doubling backoff.
* **A stop is not a failure.** SIGTERM and SIGINT settle the active run as
  ``killed`` with the task resumable, release the lock, and exit 0.

Signals are a blunt control channel: they cannot say "run *that* task", they
cannot be queued for an engine that is not up yet, and they leave no record of
who asked. So the engine also consumes the ``engine_commands`` table — the
durable channel the CLI, the dashboard, and the intake API all write to. The
loop drains pending commands at the top of every pass, and supplies the
orchestrator with a ``command_poll`` callback so a ``pause`` or a ``stop_task``
reaches an agent step that may already be twenty minutes into its work.

The loop is a plain object with injectable clocks, so all of that is testable
without a subprocess. The CLI handler only parses arguments and maps
:class:`ServeResult` to an exit code.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable

from .engine_lock import EngineBusyError, EngineLock
from .errors import EngineCommandInterrupt
from .logs import get_logger, log_event
from .models import ENGINE_COMMANDS_NEEDING_A_RESIDENT_ENGINE, EngineCommand
from .notifications import NotificationDeliveryWorker
from .orchestrator import (
    ForemanOrchestrator,
    LeaseLostError,
    OrchestratorError,
    ProjectRunResult,
    TaskExecutionError,
)
from .runner.process import EngineShutdown, terminate_all
from .store import ForemanStore

#: How long an idle pass waits before running another pass anyway.
DEFAULT_POLL_SECONDS = 5.0

#: How often the idle wait re-reads ``PRAGMA data_version``. Small enough that
#: work arriving from another process is picked up promptly, and cheap enough
#: that it is the only thing an idle engine does between wakes.
DATA_VERSION_TICK_SECONDS = 0.5

#: Backoff after a task failure, doubling per consecutive failure.
INITIAL_BACKOFF_SECONDS = 5.0
MAX_BACKOFF_SECONDS = 300.0

#: How long to wait after a backend quota ran out when the backend did not say
#: when it resets, and the bounds applied when it did. The upper bound keeps a
#: stale or malformed reset time from parking the engine for a day.
DEFAULT_QUOTA_WAIT_SECONDS = 900.0
MIN_QUOTA_WAIT_SECONDS = 60.0
MAX_QUOTA_WAIT_SECONDS = 6 * 3600.0
QUOTA_WAIT_GRACE_SECONDS = 5.0

#: Recorded on commands a starting engine refuses because they were addressed
#: to a resident engine that is no longer there.
STALE_COMMAND_DETAIL = "no engine was resident"

#: Why a command an earlier engine had picked up, but not finished, is closed.
UNFINISHED_COMMAND_DETAIL = "the engine stopped before it finished applying this command"

#: How long a terminated agent process group is given to die before the engine
#: stops waiting for it.
COMMAND_TERMINATE_GRACE_SECONDS = 2.0

_LOGGER = get_logger("serve")


@dataclass(slots=True)
class ServeResult:
    """Why the resident engine stopped, and with which exit code."""

    project_id: str
    #: ``once`` | ``stopped`` | ``lock_lost`` | ``error``
    stop_reason: str
    exit_code: int
    passes: int = 0
    executed_task_ids: tuple[str, ...] = ()
    blocked_task_ids: tuple[str, ...] = ()
    last_pass_reason: str | None = None
    detail: str | None = None


@dataclass(slots=True)
class _Backoff:
    """Doubling backoff over consecutive task failures."""

    initial: float = INITIAL_BACKOFF_SECONDS
    maximum: float = MAX_BACKOFF_SECONDS
    failures: int = field(default=0)

    def record_failure(self) -> float:
        """Count one failure and return how long to wait before the next pass."""

        self.failures += 1
        return min(self.initial * (2 ** (self.failures - 1)), self.maximum)

    def reset(self) -> None:
        self.failures = 0


class ResidentEngine:
    """Run one project's orchestrator in a loop until asked to stop.

    The engine assumes ``lock`` is already held; :func:`serve_project` wires
    that up. Passing the lock in (rather than acquiring it here) keeps the loop
    testable with a stub and keeps the lock's lifetime owned by the caller that
    can guarantee its release.
    """

    def __init__(
        self,
        *,
        store: ForemanStore,
        project_id: str,
        orchestrator: ForemanOrchestrator,
        lock: EngineLock | None = None,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        logger: logging.Logger | None = None,
        sleep: Callable[[float], None] | None = None,
        monotonic: Callable[[], float] | None = None,
        tick_seconds: float = DATA_VERSION_TICK_SECONDS,
        utc_now: Callable[[], datetime] | None = None,
        notification_worker: NotificationDeliveryWorker | None = None,
        accepts_run_requests: bool = True,
        honour_standing_pause: bool = True,
    ) -> None:
        self.store = store
        self.project_id = project_id
        self.orchestrator = orchestrator
        self.lock = lock
        self.poll_seconds = max(0.0, float(poll_seconds))
        self.logger = logger if logger is not None else _LOGGER
        self._sleep = sleep or time.sleep
        self._monotonic = monotonic or time.monotonic
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._tick_seconds = max(0.01, float(tick_seconds))
        #: Sends what the engine queued for the project's notification
        #: destinations. It runs between passes rather than inside one, so a
        #: destination that is slow or down costs the *worker* time and never
        #: a task's.
        self._notifications = (
            notification_worker
            if notification_worker is not None
            else NotificationDeliveryWorker(store, utc_now=self._utc_now)
        )
        self._backoff = _Backoff()
        #: Set by a `pause`, cleared by a `resume`. A paused engine picks no
        #: new work but stays resident, keeps heartbeating its lock, and keeps
        #: reading commands — so it can still be resumed or shut down. A pause
        #: outlives the process that applied it: an engine that is restarted
        #: (by a supervisor, or by hand) while the project is paused starts
        #: paused, so what every other process reads from the command log is
        #: what this engine does.
        self._paused = honour_standing_pause and _standing_pause(store, project_id)
        #: False for a one-shot `foreman run`, which ends after its pass and
        #: so cannot promise to run a task later.
        self._accepts_run_requests = accepts_run_requests
        #: Set by a `shutdown`. Ends the loop cleanly with exit code 0.
        self._stopping = False
        #: Filled by `run_task`, drained one per pass. A list rather than a
        #: single slot because two `run_task` commands are two requests: the
        #: second must not silently discard the first. Each entry keeps its
        #: command, which stays ``acknowledged`` until the task has run.
        self._run_requests: list[tuple[str, EngineCommand]] = []

    # ── loop ─────────────────────────────────────────────────────────────

    def run(self, *, once: bool = False) -> ServeResult:
        """Run passes until stopped. Returns why, and with which exit code."""

        executed: list[str] = []
        blocked: list[str] = []
        passes = 0
        # Retention pruning and crash recovery belong to startup and to passes
        # that actually did something. Repeating them on every idle wake would
        # turn the lock heartbeat — which commits from another connection and
        # so bumps ``data_version`` — into a busy loop.
        maintenance_due = True
        stop_reason = "stopped"
        exit_code = 0
        detail: str | None = None
        last_pass_reason: str | None = None
        idle_streak = 0
        paused_streak = 0

        self._log(
            "serve.started",
            poll_seconds=self.poll_seconds,
            once=once,
            holder_id=self.orchestrator.holder_id,
            paused=self._paused,
        )
        self.attach()

        try:
            while True:
                if self._lock_is_lost():
                    stop_reason, exit_code = "lock_lost", 1
                    detail = self._lock_lost_reason()
                    self._log("serve.lock_lost", level=logging.ERROR, reason=detail)
                    break

                self._drain_commands()
                self._deliver_notifications()

                if self._stopping:
                    stop_reason, exit_code = "stopped", 0
                    detail = "Engine was shut down by command."
                    self._log("serve.stopping", reason=detail)
                    break

                if self._paused:
                    # Idle by instruction rather than for lack of work. The
                    # wait is the same one an idle engine uses, so a `resume`
                    # committed from another process wakes it immediately.
                    if once:
                        stop_reason, detail = "once", "Engine is paused."
                        break
                    paused_streak += 1
                    # Entering the paused state is worth narrating; staying
                    # paused is not, and a pause can last all day.
                    self._log(
                        "serve.paused",
                        level=logging.INFO if paused_streak == 1 else logging.DEBUG,
                    )
                    self._wait_for_change(self.poll_seconds)
                    continue
                paused_streak = 0

                passes += 1
                run_request = self._take_run_request()
                target_task_id = run_request[0] if run_request else None
                try:
                    result = self.orchestrator.run_project(
                        self.project_id,
                        task_id=target_task_id,
                        maintenance=maintenance_due,
                    )
                except EngineCommandInterrupt as exc:
                    self._finish_run_request(
                        run_request,
                        "completed",
                        f"Task {target_task_id!r} was started and then interrupted by "
                        f"`{exc.command.command}`.",
                    )
                    self._settle_interrupt(exc)
                    maintenance_due = True
                    if once:
                        stop_reason, detail = "once", str(exc)
                        break
                    continue
                except TaskExecutionError as exc:
                    self._finish_run_request(
                        run_request,
                        "completed",
                        f"Task {target_task_id!r} was run and failed: {exc.cause}",
                    )
                    delay = self._isolate_task_failure(exc)
                    blocked.append(exc.task_id)
                    maintenance_due = True
                    if once:
                        # A pass that isolated a failure still did its job: the
                        # task is blocked with an attention turn and the engine
                        # is healthy, so a cron-style `--once` exits 0.
                        stop_reason, detail = "once", str(exc)
                        break
                    self._wait(delay)
                    continue
                except LeaseLostError as exc:
                    # This engine's lease on the task it was running expired or
                    # was taken over. The run is already settled as killed and
                    # the task is resumable; retry the project after a backoff
                    # rather than ending the service.
                    self._finish_run_request(
                        run_request,
                        "completed",
                        f"Task {target_task_id!r} was started; the engine then lost "
                        f"its lease on it: {exc}",
                    )
                    delay = self._backoff.record_failure()
                    self._log(
                        "serve.task_lease_lost",
                        level=logging.WARNING,
                        reason=str(exc),
                        backoff_seconds=delay,
                    )
                    maintenance_due = True
                    if once:
                        stop_reason, detail = "once", str(exc)
                        break
                    self._wait(delay)
                    continue
                except OrchestratorError as exc:
                    # Ordered last of the OrchestratorError family: the two
                    # subclasses above are handled on their own terms, and
                    # QuotaPauseError never reaches here because run_project
                    # turns it into a `quota_exhausted` result. A *targeted*
                    # run that cannot even start is about that one task (it was
                    # leased away, or it moved) rather than about the project,
                    # so isolating it keeps a bad `run_task` from ending the
                    # service. Anything else still ends it.
                    if target_task_id is None:
                        raise
                    self._finish_run_request(
                        run_request,
                        "rejected",
                        f"Task {target_task_id!r} could not be started: {exc}",
                    )
                    delay = self._isolate_task_failure(
                        TaskExecutionError(target_task_id, exc)
                    )
                    blocked.append(target_task_id)
                    maintenance_due = True
                    if once:
                        stop_reason, detail = "once", str(exc)
                        break
                    self._wait(delay)
                    continue

                if run_request is not None:
                    ran = target_task_id in result.executed_task_ids
                    self._finish_run_request(
                        run_request,
                        "completed",
                        (
                            f"Task {target_task_id!r} was run"
                            if ran
                            else f"Task {target_task_id!r} was not run"
                        )
                        + f"; the pass ended with {result.stop_reason!r}."
                        + (f" {result.detail}" if result.detail and not ran else ""),
                    )
                executed.extend(result.executed_task_ids)
                blocked.extend(result.blocked_task_ids)
                last_pass_reason = result.stop_reason
                self._backoff.reset()
                did_work = bool(result.executed_task_ids)
                idle_streak = 0 if did_work else idle_streak + 1
                # The transition into idleness is worth narrating once; a
                # second consecutive empty pass is routine and stays at DEBUG
                # so an idle service does not fill its own log.
                self._log_pass(
                    result,
                    level=logging.INFO if idle_streak <= 1 else logging.DEBUG,
                )

                if result.stop_reason == "quota_exhausted":
                    # The backend's usage window is spent. The task kept its
                    # resume point; nothing will succeed before the reset, so
                    # wait for it instead of blocking the task or spinning.
                    delay = quota_wait_seconds(result.retry_after, now=self._utc_now())
                    self._log(
                        "serve.quota_exhausted",
                        level=logging.WARNING,
                        retry_after=result.retry_after,
                        wait_seconds=delay,
                        detail=result.detail,
                    )
                    maintenance_due = False
                    if once:
                        stop_reason, detail = "once", result.detail
                        break
                    self._wait(delay)
                    continue

                if once:
                    stop_reason = "once"
                    break

                maintenance_due = did_work
                if not did_work:
                    self._log(
                        "serve.idle",
                        level=logging.INFO if idle_streak == 1 else logging.DEBUG,
                        stop_reason=result.stop_reason,
                    )
                    self._wait_for_change(self.poll_seconds)

        except (EngineShutdown, KeyboardInterrupt) as exc:
            if self._lock_is_lost():
                stop_reason, exit_code = "lock_lost", 1
                detail = self._lock_lost_reason()
                self._log("serve.lock_lost", level=logging.ERROR, reason=detail)
            else:
                # A requested stop is not a failure. The orchestrator has
                # already settled the active run as killed and left the task
                # resumable at its persisted step.
                stop_reason, exit_code, detail = "stopped", 0, str(exc)
                self._log("serve.stopping", reason=detail)
            terminate_all(grace_seconds=2.0)
        except OrchestratorError as exc:
            # Not task-scoped: an unknown project or an invalid project
            # configuration will not fix itself, so retrying forever would only
            # hide it. Stop and report.
            stop_reason, exit_code, detail = "error", 1, str(exc)
            self._log("serve.failed", level=logging.ERROR, reason=detail)
        except Exception as exc:  # noqa: BLE001 - reported with a non-zero exit, not hidden
            # A bug in the engine. A supervisor decides from the exit code
            # whether to restart, so this must not look like a clean stop.
            stop_reason, exit_code = "crashed", 1
            detail = f"{type(exc).__name__}: {exc}"
            self._log(
                "serve.crashed",
                level=logging.ERROR,
                reason=detail,
                traceback=traceback.format_exc(),
            )
            terminate_all(grace_seconds=2.0)
        finally:
            self._log(
                "serve.stopped",
                stop_reason=stop_reason,
                exit_code=exit_code,
                passes=passes,
                executed_task_ids=list(executed),
            )

        return ServeResult(
            project_id=self.project_id,
            stop_reason=stop_reason,
            exit_code=exit_code,
            passes=passes,
            executed_task_ids=tuple(executed),
            blocked_task_ids=tuple(blocked),
            last_pass_reason=last_pass_reason,
            detail=detail,
        )

    def _deliver_notifications(self) -> None:
        """Send whatever notifications are due for this project.

        Called once per iteration, which means after every pass and on every
        idle wake -- so a retry that came due while the engine had nothing to
        do is still sent. A resident engine is the only thing that runs often
        enough to work a backoff schedule; a one-shot ``foreman run`` drains
        once at exit and leaves the rest to the next engine that runs.
        """

        result = self._notifications.drain(self.project_id)
        if result.did_work:
            self._log(
                "serve.notifications",
                level=logging.INFO if result.failed else logging.DEBUG,
                attempted=result.attempted,
                delivered=result.delivered,
                retrying=result.retrying,
                failed=result.failed,
            )

    # ── commands ─────────────────────────────────────────────────────────

    def attach(self) -> None:
        """Become the engine that answers this project's commands.

        Called by :meth:`run`, and by a one-shot `foreman run`, which holds the
        project lock for its pass and so is the only process that can act on a
        `pause` or a `stop_task` sent while it works.
        """

        # This engine is the one that just took the lock, so it owns the
        # decision about commands addressed to the engine that was not there.
        self.orchestrator.command_poll = self._poll_commands
        self._reject_stale_commands()

    def settle_interrupt(self, interrupt: EngineCommandInterrupt) -> None:
        """Finish the command that stopped a step run outside :meth:`run`."""

        self._settle_interrupt(interrupt)

    def _reject_stale_commands(self) -> None:
        """Settle commands left over from an engine that is gone.

        A pending `pause`, `stop_task`, or `shutdown` describes an intent
        about a process that is no longer running: applying them to *this*
        engine would pause a service nobody asked to pause, or block a task
        nobody is working on. A `resume` and a `run_task` describe work rather
        than a process, and work outlives the engine, so both are left pending
        for the first pass to pick up.

        A command the previous engine had acknowledged but not finished (it
        stopped in between) gets the same treatment: a `run_task` is queued
        again, anything else is closed with the reason.
        """

        for command in self.store.list_engine_commands(
            self.project_id, status="pending", limit=1000
        ):
            if command.command not in ENGINE_COMMANDS_NEEDING_A_RESIDENT_ENGINE:
                continue
            self._finish_command(command, "rejected", STALE_COMMAND_DETAIL)
        unfinished = self.store.list_engine_commands(
            self.project_id, status="acknowledged", limit=1000
        )
        for command in reversed(unfinished):  # oldest first
            if command.command in {"run_task", "resume"}:
                self._apply_idle_command(command)
            else:
                self._finish_command(command, "rejected", UNFINISHED_COMMAND_DETAIL)

    def _drain_commands(self) -> None:
        """Apply every pending command, oldest first, before the next pass."""

        while True:
            command = self.store.next_pending_engine_command(self.project_id)
            if command is None:
                return
            self._acknowledge(command)
            self._apply_idle_command(command)

    def _poll_commands(self, running_task_id: str) -> None:
        """Command hook the orchestrator calls before a step and on every tick.

        Returns normally to let the step continue. Raises
        :class:`~foreman.errors.EngineCommandInterrupt` when the command needs
        the running step stopped; the orchestrator settles the run as
        ``killed`` on the way out and :meth:`_settle_interrupt` finishes the
        command once the stack has unwound.
        """

        while True:
            command = self.store.next_pending_engine_command(self.project_id)
            if command is None:
                return
            self._acknowledge(command)

            if command.command in {"pause", "shutdown"} or (
                command.command == "stop_task"
                and command.task_id == running_task_id
            ):
                # Kill the agent's whole process group first: the run must be
                # settled against a child that is already gone, not one still
                # writing to the repository.
                terminate_all(grace_seconds=COMMAND_TERMINATE_GRACE_SECONDS)
                self._log(
                    "serve.command_interrupting",
                    command_id=command.id,
                    command=command.command,
                    task_id=running_task_id,
                    requested_by=command.requested_by,
                )
                raise EngineCommandInterrupt(command, task_id=running_task_id)

            self._apply_idle_command(command, running_task_id=running_task_id)

    def _apply_idle_command(
        self,
        command: EngineCommand,
        *,
        running_task_id: str | None = None,
    ) -> None:
        """Apply one command that does not need the running step stopped."""

        name = command.command
        if name == "pause":
            self._paused = True
            self._finish_command(command, "completed", "Engine paused; no task was running.")
        elif name == "shutdown":
            self._paused = True
            self._stopping = True
            self._finish_command(
                command, "completed", "Engine shutting down; no task was running."
            )
        elif name == "resume":
            was_paused = self._paused
            self._paused = False
            self._finish_command(
                command,
                "completed",
                "Engine resumed." if was_paused else "Engine was already running.",
            )
        elif name == "run_task":
            self._apply_run_task(command)
        elif name == "stop_task":
            self._finish_command(
                command,
                "rejected",
                self._stop_task_rejection(command, running_task_id),
            )
        else:  # pragma: no cover - the schema CHECK constraint prevents this
            self._finish_command(
                command, "rejected", f"Unknown engine command {name!r}."
            )

    def _apply_run_task(self, command: EngineCommand) -> None:
        """Queue a `run_task` for the next pass, or reject it with a reason.

        A queued request stays ``acknowledged``; it is ``completed`` when the
        pass that ran the task has ended, with what happened as its detail.
        """

        if not self._accepts_run_requests:
            self._finish_command(
                command,
                "rejected",
                "A one-shot `foreman run` holds this project and ends after its "
                "pass, so it cannot take a run request. Ask again when it has "
                "finished, or start `foreman serve`.",
            )
            return
        task_id = command.task_id
        if not task_id:
            self._finish_command(
                command, "rejected", "run_task needs a task id."
            )
            return
        task = self.store.get_task(task_id)
        if task is None:
            self._finish_command(
                command, "rejected", f"Unknown task {task_id!r}."
            )
            return
        if task.project_id != self.project_id:
            self._finish_command(
                command,
                "rejected",
                f"Task {task_id!r} belongs to project {task.project_id!r}, "
                f"not {self.project_id!r}.",
            )
            return
        runnable = task.status == "todo" or (
            task.status == "in_progress" and bool(task.workflow_current_step)
        )
        if not runnable:
            self._finish_command(
                command,
                "rejected",
                f"Task {task_id!r} is {task.status!r} and not runnable. Only a "
                "todo task, or an in_progress task with a persisted resume "
                "point, can be run on request.",
            )
            return
        self._run_requests.append((task_id, command))
        position = len(self._run_requests)
        self.store.mark_engine_command(
            command.id,
            "acknowledged",
            detail=(
                f"Task {task_id!r} will run next."
                if position == 1
                else f"Task {task_id!r} is queued to run ({position} requests ahead of the sprint)."
            ),
        )

    def _stop_task_rejection(
        self, command: EngineCommand, running_task_id: str | None
    ) -> str:
        """Explain why a `stop_task` could not be applied."""

        if not command.task_id:
            return "stop_task needs a task id."
        if running_task_id is None:
            return (
                f"Task {command.task_id!r} is not running: the engine is idle. "
                "Use `foreman task block` to park a task that is not running."
            )
        return (
            f"Task {command.task_id!r} is not the task this engine is running "
            f"({running_task_id!r})."
        )

    def _settle_interrupt(self, interrupt: EngineCommandInterrupt) -> None:
        """Finish the command whose interrupt just unwound the stack.

        By now the orchestrator has settled the agent run as ``killed`` and the
        task is resumable at its persisted step. What remains is the difference
        between the two stops: a `pause` leaves the task exactly as it is, a
        `stop_task` parks it as ``blocked`` naming who stopped it.
        """

        command = interrupt.command
        assert isinstance(command, EngineCommand)  # only this module raises it
        task_id = interrupt.task_id

        if command.command == "stop_task":
            reason = f"Stopped by {command.requested_by}"
            self.orchestrator.stop_task(command.task_id or task_id, reason=reason)
            detail = (
                f"Stopped task {command.task_id!r}: the agent process group was "
                f"terminated, its run settled as killed, and the task is blocked "
                f"({reason})."
            )
        else:
            # `pause` and `shutdown` both leave the task resumable. The lease
            # goes back so the task is not pinned to an engine that has stopped
            # working on it; the guarded step usually released it already, and
            # releasing twice is a no-op.
            if task_id:
                self.orchestrator.release_task(task_id)
            self._paused = True
            if command.command == "shutdown":
                self._stopping = True
            detail = (
                f"{'Shut down' if command.command == 'shutdown' else 'Paused'} "
                f"during task {task_id!r}: the agent process group was terminated, "
                "its run settled as killed, and the task is resumable."
            )
        self._finish_command(command, "completed", detail, task_id=task_id)

    def _acknowledge(self, command: EngineCommand) -> None:
        """Record that this engine has picked a command up."""

        self.store.mark_engine_command(command.id, "acknowledged")
        self._log(
            "serve.command_acknowledged",
            command_id=command.id,
            command=command.command,
            task_id=command.task_id,
            requested_by=command.requested_by,
        )

    def _finish_command(
        self,
        command: EngineCommand,
        status: str,
        detail: str,
        *,
        task_id: str | None = None,
    ) -> None:
        """Close a command out and leave a durable trace of what happened."""

        self.store.mark_engine_command(command.id, status, detail=detail)
        event_type = (
            "engine.command_applied" if status == "completed" else "engine.command_rejected"
        )
        self._log(
            f"serve.command_{status}",
            level=logging.INFO if status == "completed" else logging.WARNING,
            command_id=command.id,
            command=command.command,
            task_id=command.task_id or task_id,
            requested_by=command.requested_by,
            detail=detail,
        )
        try:
            self.orchestrator.record_engine_event(
                project_id=self.project_id,
                event_type=event_type,
                task_id=command.task_id or task_id,
                detail=detail,
                payload={
                    "command_id": command.id,
                    "command": command.command,
                    "requested_by": command.requested_by,
                    "task_id": command.task_id,
                    "detail": detail,
                },
            )
        except Exception as exc:  # noqa: BLE001 - a lost trace must not stop the engine
            self._log(
                "serve.command_event_failed",
                level=logging.ERROR,
                command_id=command.id,
                reason=str(exc),
            )

    def _take_run_request(self) -> tuple[str, EngineCommand] | None:
        """Consume the next queued `run_task` request, if one is waiting."""

        if not self._run_requests:
            return None
        return self._run_requests.pop(0)

    def _finish_run_request(
        self,
        request: tuple[str, EngineCommand] | None,
        status: str,
        detail: str,
    ) -> None:
        """Close a `run_task` command once its pass has ended."""

        if request is not None:
            self._finish_command(request[1], status, detail)

    # ── failure isolation ────────────────────────────────────────────────

    def _isolate_task_failure(self, exc: TaskExecutionError) -> float:
        """Park the failed task, raise attention, and return the backoff delay."""

        reason = str(exc.cause) or repr(exc.cause)
        delay = self._backoff.record_failure()
        try:
            self.orchestrator.block_task_for_error(exc.task_id, reason)
        except Exception as block_error:  # noqa: BLE001 - reported, never fatal
            self._log(
                "serve.task_block_failed",
                level=logging.ERROR,
                task_id=exc.task_id,
                reason=str(block_error),
            )
        self._log(
            "serve.task_failed",
            level=logging.ERROR,
            task_id=exc.task_id,
            reason=reason,
            error_type=type(exc.cause).__name__,
            consecutive_failures=self._backoff.failures,
            backoff_seconds=delay,
        )
        return delay

    # ── waiting ──────────────────────────────────────────────────────────

    def _wait(self, seconds: float) -> None:
        """Sleep for ``seconds`` in ticks, returning early if the lock is lost
        or a command is waiting.

        These waits are the long ones: a failure backoff reaches five minutes,
        and a quota wait reaches six hours. An engine that ignored `shutdown`
        for six hours would not be controllable, so a queued command cuts the
        wait short and the loop drains it on the next pass.

        ``data_version`` is checked first because it is a pragma rather than a
        table read, so the common case — nothing committed since the last tick
        — costs nothing beyond it. Only an actual commit by another connection
        is worth a lookup in ``engine_commands``.
        """

        deadline = self._monotonic() + seconds
        baseline = self.store.data_version()
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0 or self._lock_is_lost():
                return
            self._sleep(min(self._tick_seconds, remaining))
            version = self.store.data_version()
            if version != baseline:
                baseline = version
                if self._has_pending_command():
                    return

    def _has_pending_command(self) -> bool:
        """True when a command is waiting for this engine to pick it up."""

        return self.store.next_pending_engine_command(self.project_id) is not None

    def _wait_for_change(self, timeout: float) -> bool:
        """Block until another process commits, or ``timeout`` elapses.

        ``PRAGMA data_version`` only moves when a *different* connection
        commits, so this detects a task queued by the dashboard, the CLI, or
        the intake API without polling any table. The baseline is re-read on
        every wait.

        A commit is not necessarily about this project: lock heartbeats,
        another project's engine and a running agent's event stream all move
        ``data_version``. Only a change to this project's own settings,
        sprints, tasks, commands or queued notifications ends the wait; the
        rest cost one small read each instead of a full pass.
        """

        baseline = self.store.data_version()
        activity = self.store.project_activity_token(self.project_id)
        deadline = self._monotonic() + timeout
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return False
            self._sleep(min(self._tick_seconds, remaining))
            if self._lock_is_lost():
                return False
            version = self.store.data_version()
            if version == baseline:
                continue
            baseline = version
            if self.store.project_activity_token(self.project_id) != activity:
                return True

    # ── helpers ──────────────────────────────────────────────────────────

    def _lock_is_lost(self) -> bool:
        return self.lock is not None and self.lock.lost

    def _lock_lost_reason(self) -> str:
        if self.lock is None:
            return "Engine lock was lost."
        return self.lock.lost_reason or "Engine lock was lost."

    def _log_pass(self, result: ProjectRunResult, *, level: int = logging.INFO) -> None:
        self._log(
            "serve.pass_completed",
            level=level,
            stop_reason=result.stop_reason,
            executed_task_ids=list(result.executed_task_ids),
            blocked_task_ids=list(result.blocked_task_ids),
        )

    def _log(self, event: str, *, level: int = logging.INFO, **fields: object) -> None:
        log_event(
            self.logger,
            event,
            level=level,
            project_id=self.project_id,
            **fields,
        )


def _standing_pause(store: ForemanStore, project_id: str) -> bool:
    """True when the project's last applied pause/resume was a pause."""

    from .engine_control import engine_is_paused

    return engine_is_paused(store, project_id)


def quota_wait_seconds(retry_after: str | None, *, now: datetime) -> float:
    """Return how long to wait for a backend quota reset reported as ISO 8601.

    A missing or unparseable time falls back to ``DEFAULT_QUOTA_WAIT_SECONDS``;
    a reported time is honoured with a small grace period and clamped to
    ``[MIN_QUOTA_WAIT_SECONDS, MAX_QUOTA_WAIT_SECONDS]``.
    """

    if not retry_after:
        return DEFAULT_QUOTA_WAIT_SECONDS
    try:
        reset = datetime.fromisoformat(retry_after.replace("Z", "+00:00"))
    except ValueError:
        return DEFAULT_QUOTA_WAIT_SECONDS
    if reset.tzinfo is None:
        reset = reset.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    seconds = (reset - now).total_seconds() + QUOTA_WAIT_GRACE_SECONDS
    return min(max(seconds, MIN_QUOTA_WAIT_SECONDS), MAX_QUOTA_WAIT_SECONDS)


def serve_project(
    *,
    store: ForemanStore,
    project_id: str,
    orchestrator: ForemanOrchestrator | None = None,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    once: bool = False,
    lock: EngineLock | None = None,
    logger: logging.Logger | None = None,
    **engine_kwargs: object,
) -> ServeResult:
    """Acquire the project engine lock and run the resident engine under it.

    Raises :class:`~foreman.engine_lock.EngineBusyError` when another engine
    holds the lock; the lock is released on every other exit path, including an
    unhandled error.
    """

    engine_logger = logger if logger is not None else _LOGGER
    orchestrator = orchestrator or ForemanOrchestrator(store)
    engine_lock = lock or EngineLock(
        store=store,
        project_id=project_id,
        holder_id=orchestrator.holder_id,
    )

    try:
        engine_lock.acquire()
    except EngineBusyError as exc:
        # A supervisor reading only the process log must be able to tell a
        # refused start from a crash, so the refusal is logged before it is
        # raised for the CLI to print.
        log_event(
            engine_logger,
            "serve.lock_busy",
            level=logging.ERROR,
            project_id=project_id,
            holder_id=exc.holder_id,
            expires_at=exc.expires_at,
            reason=str(exc),
        )
        raise
    log_event(
        engine_logger,
        "serve.lock_acquired",
        project_id=project_id,
        holder_id=orchestrator.holder_id,
        lease_id=engine_lock.lease.id if engine_lock.lease else None,
        expires_at=engine_lock.lease.expires_at if engine_lock.lease else None,
    )
    try:
        engine = ResidentEngine(
            store=store,
            project_id=project_id,
            orchestrator=orchestrator,
            lock=engine_lock,
            poll_seconds=poll_seconds,
            logger=engine_logger,
            **engine_kwargs,  # type: ignore[arg-type]
        )
        return engine.run(once=once)
    finally:
        engine_lock.release()
        log_event(
            engine_logger,
            "serve.lock_released",
            project_id=project_id,
            holder_id=orchestrator.holder_id,
        )


__all__ = [
    "DEFAULT_POLL_SECONDS",
    "DEFAULT_QUOTA_WAIT_SECONDS",
    "quota_wait_seconds",
    "EngineBusyError",
    "ResidentEngine",
    "ServeResult",
    "serve_project",
]
