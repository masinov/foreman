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

The loop is a plain object with injectable clocks, so all of that is testable
without a subprocess. The CLI handler only parses arguments and maps
:class:`ServeResult` to an exit code.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from .engine_lock import EngineBusyError, EngineLock
from .logs import get_logger, log_event
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
    ) -> None:
        self.store = store
        self.project_id = project_id
        self.orchestrator = orchestrator
        self.lock = lock
        self.poll_seconds = max(0.0, float(poll_seconds))
        self.logger = logger if logger is not None else _LOGGER
        self._sleep = sleep or time.sleep
        self._monotonic = monotonic or time.monotonic
        self._tick_seconds = max(0.01, float(tick_seconds))
        self._backoff = _Backoff()

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

        self._log(
            "serve.started",
            poll_seconds=self.poll_seconds,
            once=once,
            holder_id=self.orchestrator.holder_id,
        )

        try:
            while True:
                if self._lock_is_lost():
                    stop_reason, exit_code = "lock_lost", 1
                    detail = self._lock_lost_reason()
                    self._log("serve.lock_lost", level=logging.ERROR, reason=detail)
                    break

                passes += 1
                try:
                    result = self.orchestrator.run_project(
                        self.project_id, maintenance=maintenance_due
                    )
                except TaskExecutionError as exc:
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

                executed.extend(result.executed_task_ids)
                blocked.extend(result.blocked_task_ids)
                last_pass_reason = result.stop_reason
                self._backoff.reset()
                self._log_pass(result)

                if once:
                    stop_reason = "once"
                    break

                did_work = bool(result.executed_task_ids)
                maintenance_due = did_work
                if not did_work:
                    self._log("serve.idle", stop_reason=result.stop_reason)
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
        """Sleep for ``seconds`` in ticks, returning early if the lock is lost."""

        deadline = self._monotonic() + seconds
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0 or self._lock_is_lost():
                return
            self._sleep(min(self._tick_seconds, remaining))

    def _wait_for_change(self, timeout: float) -> bool:
        """Block until another process commits, or ``timeout`` elapses.

        ``PRAGMA data_version`` only moves when a *different* connection
        commits, so this detects a task queued by the dashboard, the CLI, or
        the intake API without polling any table. The baseline is re-read on
        every wait, so the lock heartbeat (a different connection, committing
        on its own timer) costs at most one extra wake per interval.
        """

        baseline = self.store.data_version()
        deadline = self._monotonic() + timeout
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return False
            self._sleep(min(self._tick_seconds, remaining))
            if self._lock_is_lost():
                return False
            if self.store.data_version() != baseline:
                return True

    # ── helpers ──────────────────────────────────────────────────────────

    def _lock_is_lost(self) -> bool:
        return self.lock is not None and self.lock.lost

    def _lock_lost_reason(self) -> str:
        if self.lock is None:
            return "Engine lock was lost."
        return self.lock.lost_reason or "Engine lock was lost."

    def _log_pass(self, result: ProjectRunResult) -> None:
        self._log(
            "serve.pass_completed",
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
    "EngineBusyError",
    "ResidentEngine",
    "ServeResult",
    "serve_project",
]
