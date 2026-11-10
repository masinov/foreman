"""Keep a held task lease alive for as long as the task is held.

The orchestrator used to renew a task's lease only while an agent streamed
output and between workflow steps. A built-in step that ran longer than the
lease (a test suite, a worktree setup command) let it lapse *after* doing its
work: the renewal that followed was refused, the engine stopped, recovery
reset the task, and the developer agent ran again, without bound.

A lease says "this engine is working on this task". That is true for the
whole time the engine holds the token, whatever the step is doing, so the
heartbeat belongs to the hold and not to any one kind of step. This mirrors
the project engine lock (``foreman/engine_lock.py``): a daemon thread with
its own database connection renews on a timer.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from .logs import log_event
from .store import ForemanStore

# Renewals per lease lifetime; a lease survives two missed heartbeats.
_BEATS_PER_LEASE = 3
DEFAULT_TASK_LEASE_SECONDS = 300.0
HEARTBEAT_FAILURE_TOLERANCE = 3


class TaskLeaseHeartbeat:
    """Renew one task lease on a timer until stopped or refused."""

    def __init__(
        self,
        *,
        db_path: str,
        project_id: str,
        task_id: str,
        holder_id: str,
        lease_token: str,
        lease_seconds: float = DEFAULT_TASK_LEASE_SECONDS,
        interval_seconds: float | None = None,
        store_factory: Callable[[], ForemanStore] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.project_id = project_id
        self.task_id = task_id
        self.holder_id = holder_id
        self.lease_seconds = lease_seconds
        self.interval_seconds = (
            interval_seconds if interval_seconds is not None else lease_seconds / _BEATS_PER_LEASE
        )
        self._token = lease_token
        self._store_factory = store_factory or (lambda: ForemanStore(db_path))
        self._logger = logger or logging.getLogger("foreman.task_lease")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.lost = False

    def start(self) -> None:
        if self.interval_seconds <= 0 or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, name=f"foreman-task-lease-{self.task_id}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop renewing. Safe to call more than once and from any thread."""

        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)

    def _loop(self) -> None:
        store: ForemanStore | None = None
        failures = 0
        try:
            store = self._store_factory()
            while not self._stop.wait(self.interval_seconds):
                try:
                    renewed = store.renew_lease(
                        project_id=self.project_id,
                        resource_type="task",
                        resource_id=self.task_id,
                        holder_id=self.holder_id,
                        lease_token=self._token,
                        duration_seconds=self.lease_seconds,
                    )
                except Exception as exc:  # noqa: BLE001 - a busy database is not a lost lease
                    failures += 1
                    log_event(
                        self._logger,
                        "task_lease.heartbeat_failed",
                        level=logging.WARNING,
                        project_id=self.project_id,
                        task_id=self.task_id,
                        attempt=failures,
                        reason=str(exc),
                    )
                    if failures >= HEARTBEAT_FAILURE_TOLERANCE:
                        self.lost = True
                        return
                    continue
                if renewed is None:
                    # Expired or taken over. The orchestrator's own renewal
                    # between steps raises LeaseLostError; this thread only
                    # stops pretending.
                    self.lost = True
                    return
                failures = 0
        finally:
            if store is not None:
                try:
                    store.close()
                except Exception:  # noqa: BLE001 - shutdown must not raise
                    pass
