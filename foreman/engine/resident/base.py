"""The resident loop: a pass, the commands, a wait, until told to stop.
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from ...domain.errors import EngineCommandInterrupt
from ...domain.models import (
    EngineCommand,
    Task,
)
from ...history.logs import get_logger, log_event
from ...notifications.delivery import NotificationDeliveryWorker
from ...runner import process
from ...runner.process import EngineShutdown
from ...store import ForemanStore
from ..control import engine_is_paused
from ..errors import LeaseLostError, OrchestratorError, TaskExecutionError
from ..lock import EngineLock
from ..orchestrator import ForemanOrchestrator
from ..results import ProjectRunResult

#: How long an idle pass waits before running another pass anyway.
DEFAULT_POLL_SECONDS = 5.0


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


#: How often the idle wait re-reads ``PRAGMA data_version``. Small enough that
#: work arriving from another process is picked up promptly, and cheap enough
#: that it is the only thing an idle engine does between wakes.
DATA_VERSION_TICK_SECONDS = 0.5


def _runnable_on_request(task: Task) -> bool:
    """A todo task, or one left part-way with a step to resume at."""

    return task.status == "todo" or (
        task.status == "in_progress" and bool(task.workflow_current_step)
    )


def _standing_pause(store: ForemanStore, project_id: str) -> bool:
    """True when the project's last applied pause/resume was a pause."""


    return engine_is_paused(store, project_id)


class ResidentEngineBase:
    """The loop, attaching to a project, and the engine's log."""

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
        if not once:
            # A single pass (`--once`) ends when it ends; nothing would come
            # back for the tasks a shortened pass left.
            self.orchestrator.yield_between_tasks = self._has_something_waiting

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
                if run_request is not None:
                    # The request was checked when it was accepted; the task
                    # may have run, or been blocked or cancelled, since.
                    target = self.store.get_task(run_request[0])
                    if target is None or not _runnable_on_request(target):
                        self._finish_run_request(
                            run_request,
                            "completed",
                            f"Task {target_task_id!r} was not run on request: it is "
                            f"{target.status if target else 'gone'!r} now.",
                        )
                        continue
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
            process.terminate_all(grace_seconds=2.0)
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
            process.terminate_all(grace_seconds=2.0)
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
