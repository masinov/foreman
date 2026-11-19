"""The leases one engine holds on the tasks it is working on.

A lease says "this engine is working on this task". ``TaskLeases`` acquires,
renews and releases them for one holder, remembers the token of each lease it
holds, and keeps a heartbeat thread per task so a lease does not expire under
a long, silent step.

The heartbeat belongs to the hold and not to any one kind of step. The
orchestrator used to renew a task's lease only while an agent streamed output
and between workflow steps. A built-in step that ran longer than the lease (a
test suite, a worktree setup command) let it lapse *after* doing its work: the
renewal that followed was refused, the engine stopped, recovery reset the
task, and the developer agent ran again, without bound. ``TaskLeaseHeartbeat``
mirrors the project engine lock (``foreman/engine/lock.py``): a daemon thread
with its own database connection renews on a timer.

The lease rules (token, expiry) are ``foreman.domain.leases``; their rows are
``foreman.store.leases``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from ..domain.leases import generate_lease_token
from ..domain.models import Project, Task
from ..store import ForemanStore
from .errors import LeaseLostError
from .logs import log_event

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


#: How often a held task lease is renewed in the background.
TASK_LEASE_HEARTBEAT_SECONDS = 20.0


class TaskLeases:
    """Task leases held by one engine (one ``holder_id``)."""

    def __init__(
        self,
        store: ForemanStore,
        holder_id: str,
        *,
        heartbeat_seconds: float = TASK_LEASE_HEARTBEAT_SECONDS,
    ) -> None:
        self.store = store
        self.holder_id = holder_id
        self.heartbeat_seconds = heartbeat_seconds
        self.tokens: dict[str, str] = {}
        self.heartbeats: dict[str, TaskLeaseHeartbeat] = {}

    def holds(self, task_id: str) -> bool:
        """Whether this engine holds a lease token for the task."""

        return task_id in self.tokens

    def token_for(self, task_id: str) -> str | None:
        """Return the token of the lease held on a task, if any."""

        return self.tokens.get(task_id)

    def acquire(self, task: Task, project: Project) -> str | None:
        """Acquire a lease on a task. Returns the lease token or None if denied."""
        token = generate_lease_token()
        lease = self.store.acquire_lease(
            project_id=project.id,
            resource_type="task",
            resource_id=task.id,
            holder_id=self.holder_id,
            lease_token=token,
        )
        if lease is None:
            return None
        self.tokens[task.id] = token
        return token

    def start_heartbeat(self, task: Task, project: Project, token: str) -> None:
        """Renew the lease on a timer while this engine works on the task.

        ``run_task`` starts the timer and stops it when it returns or raises,
        so the timer never outlives the work it vouches for. A step is not
        obliged to produce output, and a built-in step produces none the
        orchestrator sees, so renewal cannot depend on step activity.
        An in-memory database has one connection and no second process to
        defend against; it gets no heartbeat thread.
        """

        previous = self.heartbeats.pop(task.id, None)
        if previous is not None:
            previous.stop()
        if self.store.db_path == ":memory:" or self.heartbeat_seconds <= 0:
            return
        heartbeat = TaskLeaseHeartbeat(
            db_path=self.store.db_path,
            project_id=project.id,
            task_id=task.id,
            holder_id=self.holder_id,
            lease_token=token,
            interval_seconds=self.heartbeat_seconds,
        )
        heartbeat.start()
        self.heartbeats[task.id] = heartbeat

    def stop_heartbeat(self, task_id: str) -> bool:
        """Stop the timer for one task. Returns whether one was running."""

        heartbeat = self.heartbeats.pop(task_id, None)
        if heartbeat is None:
            return False
        heartbeat.stop()
        return True

    def forget(self, task_id: str) -> str | None:
        """Stop heartbeating a task and drop its token without releasing it."""

        self.stop_heartbeat(task_id)
        return self.tokens.pop(task_id, None)

    def close(self) -> None:
        """Stop every lease heartbeat this engine started.

        Leases whose tokens are still held are left to expire on their own,
        which is what a crashed engine's leases do.
        """

        for task_id in list(self.heartbeats):
            self.stop_heartbeat(task_id)

    def release(self, task: Task, project: Project) -> None:
        """Release the lease on a task if held by this orchestrator."""
        token = self.forget(task.id)
        if token is not None:
            self.store.release_lease(
                project_id=project.id,
                resource_type="task",
                resource_id=task.id,
                holder_id=self.holder_id,
                lease_token=token,
            )

    def renew(self, task: Task, project: Project) -> bool:
        """Renew the lease on a task held by this orchestrator.

        Returns True when renewed, False when this orchestrator holds no
        token for the task. Raises ``LeaseLostError`` when the token exists
        but the store refuses the renewal, meaning the lease expired or was
        taken over: continuing would race the new holder in the same checkout.
        """
        token = self.tokens.get(task.id)
        if token is None:
            return False
        renewed = self.store.renew_lease(
            project_id=project.id,
            resource_type="task",
            resource_id=task.id,
            holder_id=self.holder_id,
            lease_token=token,
        )
        if renewed is None:
            self.forget(task.id)
            raise LeaseLostError(
                f"Lease on task {task.id!r} was lost (expired or taken over by another "
                "engine). Stopping this engine without touching the task."
            )
        return True
