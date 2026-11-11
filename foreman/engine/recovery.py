"""Putting tasks back in order after an engine stopped mid-work.

A run left ``running`` by an engine that died is settled, and its task is
made resumable, but only once nothing suggests the run is still alive: a
recent event, or a live lease held by someone else.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from ..models import Lease, Project, Run, Task, utc_now_text
from ..store import ForemanStore
from .errors import LeaseLostError
from .leasing import TaskLeases
from .limits import active_run_recovery_timeout_seconds
from .records import RunRecords
from .task_writes import TaskWrites

#: A lease whose heartbeat is older than this no longer vouches for its holder.
LEASE_LIVENESS_THRESHOLD_SECONDS = 60.0


class Recovery:
    """Crash recovery for the tasks and runs of one store."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        records: RunRecords,
        leases: TaskLeases,
        tasks: TaskWrites,
        utc_now: Callable[[], datetime],
        liveness_threshold_seconds: float = LEASE_LIVENESS_THRESHOLD_SECONDS,
    ) -> None:
        self.store = store
        self.records = records
        self.leases = leases
        self.tasks = tasks
        self.utc_now = utc_now
        self.holder_id = leases.holder_id
        self.liveness_threshold_seconds = liveness_threshold_seconds

    def recover_orphaned_tasks(self, project_id: str) -> None:
        """Reset orphaned in-progress tasks after a prior engine crash."""

        project = self.store.get_project(project_id)
        if project is None:
            return
        orphaned_tasks = self.store.list_tasks(project_id=project_id, status="in_progress")
        for task in orphaned_tasks:
            if task.workflow_current_step is not None:
                continue

            active_runs = self.store.list_runs(task_id=task.id, status="running")
            stale_runs = [run for run in active_runs if self.run_is_stale(project, run)]
            if active_runs and not stale_runs:
                continue

            if stale_runs:
                self.recover_stale_running_runs(project, task, stale_runs)
                continue

            if not active_runs:
                system_run = self.records.create_system_run(
                    task,
                    workflow_step=task.workflow_current_step or "orchestrator",
                    outcome="error",
                    detail="Recovered orphaned task without an active run.",
                )
                self.records.emit_event(
                    system_run,
                    "engine.crash_recovery",
                    {
                        "task_id": task.id,
                        "message": "Reset to todo after orphaned run.",
                    },
                )

            task.status = "todo"
            task.blocked_reason = None
            task.step_visit_counts = {}
            self.tasks.save(task)

    def recover_stale_running_runs(
        self,
        project: Project,
        task: Task,
        runs: list[Run],
    ) -> None:
        """Fail stale running runs and reset task state so the slice can be retried safely."""

        now = utc_now_text()

        # Capture lease metadata for the recovery event.
        task_lease = self.store.get_active_lease(
            project_id=project.id,
            resource_type="task",
            resource_id=task.id,
        )

        for run in runs:
            run.status = "failed"
            run.outcome = "error"
            run.outcome_detail = "Recovered stale running run after exceeding the active-run limit."
            run.completed_at = now
            self.store.save_run(run)
            self.records.emit_event(
                run,
                "engine.crash_recovery",
                {
                    "task_id": task.id,
                    "lease_id": task_lease.id if task_lease else None,
                    "holder_id": task_lease.holder_id if task_lease else None,
                    "fencing_token": task_lease.fencing_token if task_lease else None,
                    "message": "Marked stale running run as failed.",
                },
            )

        # Force-expire any active task lease for the recovered task so the
        # next orchestrator can acquire it immediately. Without this, a lease
        # whose `expires_at` is still in the future would block re-acquisition
        # even after the run is marked failed.
        # ``run_task`` reaches this holding the lease it has just acquired.
        # Expiring that one too made the very next renewal fail, so every
        # resume after a crash cost one wasted agent run. Clear what a dead
        # engine left, then hold the task again.
        held_by_us = self.leases.holds(task.id)
        heartbeating = task.id in self.leases.heartbeats
        if held_by_us:
            self.leases.forget(task.id)
        self.store.expire_resource_leases(
            project_id=project.id,
            resource_type="task",
            resource_id=task.id,
            force=True,
        )
        if held_by_us:
            token = self.leases.acquire(task, project)
            if token is None:
                raise LeaseLostError(
                    f"Lease on task {task.id!r} could not be re-acquired after stale-run recovery."
                )
            if heartbeating:
                self.leases.start_heartbeat(task, project, token)

        task.status = "todo"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.step_visit_counts = {}
        self.tasks.save(task)

    def run_is_stale(self, project: Project, run: Run) -> bool:
        """Return whether a persisted running run has exceeded its allowed ownership window.

        A run is considered stale when:
        1. Its configured timeout has elapsed, AND
        2. The task's active lease is either missing, expired, or held by a
           holder whose heartbeat is older than the liveness threshold
           (meaning the original holder is gone and the lease is no longer
           being heartbeated).
        """

        timeout_seconds = active_run_recovery_timeout_seconds(project)
        if timeout_seconds is None or timeout_seconds <= 0:
            return False

        # Check if the run's timeout has elapsed.
        reference = self.store.get_latest_event_timestamp(run.id) or run.started_at or run.created_at
        started = _parse_utc_timestamp(reference)
        if started is None:
            return False
        if (self.utc_now() - started).total_seconds() <= timeout_seconds:
            return False

        # Timeout has elapsed: expire any past-due leases for this task, then
        # check the liveness of the remaining lease by its heartbeat timestamp.
        # A lease whose heartbeat is stale is treated as if its holder is gone.
        self.store.expire_resource_leases(
            project_id=project.id,
            resource_type="task",
            resource_id=run.task_id,
        )
        task_lease = self.store.get_active_lease(
            project_id=project.id,
            resource_type="task",
            resource_id=run.task_id,
        )
        if task_lease is not None and task_lease.holder_id != self.holder_id:
            if _is_lease_live(task_lease, self.utc_now(), self.liveness_threshold_seconds):
                # Another orchestrator is actively heartbeating, so not stale.
                return False

        return True


def _is_lease_live(
    lease: Lease,
    utc_now: datetime,
    liveness_threshold_seconds: float,
) -> bool:
    """Return True if the lease's heartbeat is recent enough to trust the holder.

    A lease is considered live when its ``heartbeat_at`` is within
    ``liveness_threshold_seconds`` of ``utc_now``. Older heartbeats are
    treated as if the holder is gone so recovery can take over the resource.
    """
    heartbeat = _parse_utc_timestamp(lease.heartbeat_at)
    if heartbeat is None:
        return False
    return (utc_now - heartbeat).total_seconds() <= liveness_threshold_seconds


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
