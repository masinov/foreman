"""What every service shares (ADR-0032).

A service reads and writes SQLite (ADR-0002) and holds no process handles.
It returns plain dicts, the same for the HTTP API and the CLI, and raises
the errors in ``errors``, which each surface translates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ..definitions.gate_steps import (
    WorkflowGateSteps,
    blocked_kind,
    blocked_kind_counts,
    resolve_gate_steps,
)
from ..domain.models import (
    Event,
    Project,
    Sprint,
    Task,
)
from ..mutations import Mutations
from ..store import ForemanStore
from .errors import NotFoundError

#: Recorded as the requester on commands the dashboard queues when the caller
#: did not name themselves. A shared token is not identity yet (MANUAL §17), so
#: the surface is the best attribution available.
DASHBOARD_REQUESTER = "dashboard"


class Service:
    """What every service shares: the store, the clock, and finding a record or refusing."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self._now = now_factory or (lambda: datetime.now(timezone.utc))

    def _require_sprint(self, sprint_id: str) -> Sprint:
        """Return a sprint; the backlog is not one (ADR-0021) and is not found."""

        sprint = self.store.get_sprint(sprint_id)
        if sprint is None:
            raise NotFoundError(f"Sprint not found: {sprint_id}")
        if sprint.is_backlog:
            raise NotFoundError(
                f"Sprint not found: {sprint_id} is the project's backlog; "
                f"use /projects/{sprint.project_id}/backlog."
            )
        return sprint

    def _require_project(self, project_id: str) -> Project:
        """Return one project or raise the dashboard's not-found error."""

        project = self.store.get_project(project_id)
        if project is None:
            raise NotFoundError(f"Project not found: {project_id}")
        return project

    def _require_task(self, task_id: str) -> Task:
        task = self.store.get_task(task_id)
        if task is None:
            raise NotFoundError(f"Task not found: {task_id}")
        return task

    def _requester(self, requested_by: str | None) -> str:
        """Name recorded on a queued command; never blank."""

        value = (requested_by or "").strip()
        return value or DASHBOARD_REQUESTER

    def _mutations(self, requested_by: str | None = None) -> Mutations:
        """Return the shared mutation service, stamped as the dashboard.

        ``requested_by`` is who the caller says they are. A shared token is
        not identity yet, so it is recorded as given and nothing more.
        """

        actor = (requested_by or "").strip() or None
        return Mutations(self.store, via="dashboard", actor=actor, now=self._now)

    def _gate_steps(self, project: Project | None) -> WorkflowGateSteps:
        """Resolve the human-gate steps of a project's workflow."""

        return resolve_gate_steps(self.store, project)

    def _blocked_kind_counts(
        self, project: Project, gates: WorkflowGateSteps | None = None
    ) -> dict[str, int]:
        """Dead-letter counts for a project summary, keyed for the API payload."""

        counts = blocked_kind_counts(
            self.store.list_tasks(project_id=project.id, status="blocked"),
            gates if gates is not None else self._gate_steps(project),
        )
        return {
            "blocked_gate": counts["gate"],
            "blocked_engine": counts["engine"],
        }

    @staticmethod
    def _gate_policy(task: Task, gates: WorkflowGateSteps) -> str | None:
        """The policy (``plan_approval`` or ``merge_approval``) of the gate a task waits at.

        ``None`` when the task is not at a human gate, or the gate names no policy.
        """

        if blocked_kind(task, gates) != "gate":
            return None
        return gates.gate_policies.get(task.workflow_current_step or "")

    @staticmethod
    def _at_human_gate(task: Task, gates: WorkflowGateSteps) -> bool:
        """True when a blocked task is waiting for Approve/Deny rather than a fix."""

        return blocked_kind(task, gates) == "gate"

    @staticmethod
    def _serialize_event(event: Event) -> dict[str, Any]:
        return {
            "id": event.id,
            "task_id": event.task_id,
            "project_id": event.project_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "role_id": event.role_id,
            "payload": event.payload,
        }
