"""Moving a project from one sprint to the next."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..models import Project, Sprint
from ..store import ForemanStore
from .records import RunRecords


class SprintFlow:
    """Activates, completes and announces sprints for one store."""

    def __init__(
        self, store: ForemanStore, records: RunRecords, utc_now: Callable[[], datetime]
    ) -> None:
        self.store = store
        self.records = records
        self.utc_now = utc_now

    def activate_first_planned(self, project_id: str) -> Sprint | None:
        """Activate the first planned sprint when project-scoped execution starts idle."""

        active = self.store.get_active_sprint(project_id)
        if active is not None:
            return active

        next_sprint = self.store.get_next_planned_sprint(project_id)
        if next_sprint is None:
            return None

        next_sprint.status = "active"
        next_sprint.started_at = next_sprint.started_at or self.utc_now().isoformat()
        next_sprint.completed_at = None
        self.store.save_sprint(next_sprint)
        return next_sprint

    def fully_resolved(self, sprint: Sprint) -> bool:
        """Return True when every task in the sprint is done or cancelled."""
        tasks = self.store.list_tasks(sprint_id=sprint.id)
        return bool(tasks) and all(t.status in {"done", "cancelled"} for t in tasks)

    def advance(self, project: Project, sprint: Sprint) -> str | None:
        """Complete *sprint* and advance to the next planned sprint if appropriate.

        Returns:
            None            — autonomous mode advanced; caller should continue loop.
            "sprint_complete" — next sprint is queued but waiting for human.
            "idle"          — sprint done, no further sprints in the queue.
        """
        now = self.utc_now().isoformat()
        sprint.status = "completed"
        sprint.completed_at = now
        self.store.save_sprint(sprint)
        self.emit_event(project, "engine.sprint_completed", {
            "sprint_id": sprint.id,
            "sprint_title": sprint.title,
        }, sprint=sprint)

        next_sprint = self.store.get_next_planned_sprint(project.id)
        if next_sprint is None:
            # Work is exhausted; the manager may want to plan more.
            self.emit_attention(project, sprint)
            return "idle"

        if project.autonomy_level == "autonomous":
            next_sprint.status = "active"
            next_sprint.started_at = now
            self.store.save_sprint(next_sprint)
            self.emit_event(project, "engine.sprint_started", {
                "sprint_id": next_sprint.id,
                "sprint_title": next_sprint.title,
            }, sprint=next_sprint)
            return None  # continue loop

        # supervised or directed: emit ready signal and stop.
        if project.autonomy_level == "supervised":
            self.emit_event(project, "engine.sprint_ready", {
                "sprint_id": next_sprint.id,
                "sprint_title": next_sprint.title,
            }, sprint=sprint)
        # The engine stops here and hands the next move to the manager/human.
        self.emit_attention(project, sprint)
        return "sprint_complete"

    def emit_event(
        self,
        project: Project,
        event_type: str,
        payload: dict[str, Any],
        *,
        sprint: Sprint,
    ) -> None:
        """Emit a sprint-scoped lifecycle event via a synthetic run."""
        tasks = self.store.list_tasks(sprint_id=sprint.id)
        task = tasks[0] if tasks else self.records.select_project_system_task(project.id)
        if task is None:
            return
        run = self.records.create_system_run(
            task, workflow_step="orchestrator", outcome="success", detail=event_type
        )
        self.records.emit_event(run, event_type, payload)

    def emit_attention(self, project: Project, sprint: Sprint) -> None:
        """Raise one ``sprint_resolved`` attention turn when a sprint finishes and
        the engine stops (a supervised/directed handoff, or no further sprints).

        Autonomous runs that auto-advance to the next sprint do not call this.
        """
        tasks = self.store.list_tasks(sprint_id=sprint.id)
        anchor = tasks[0] if tasks else self.records.select_project_system_task(project.id)
        if anchor is None:
            return
        run = self.records.create_system_run(
            anchor,
            workflow_step="orchestrator",
            outcome="success",
            detail=f"sprint_resolved: {sprint.title}",
        )
        # task_id is None: the digest should lead with the sprint handoff, not a
        # single (already-done) task row.
        self.records.emit_attention_needed(run, None, "sprint_resolved")
