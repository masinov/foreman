"""Moving a project from one sprint to the next."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..domain.models import Project, Sprint
from ..store import ForemanStore
from ..history.records import RunRecords


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

    def resolve(self, project: Project, sprint: Sprint) -> str | None:
        """Handle a fully resolved active sprint according to the autonomy level.

        Only an autonomous project has its sprint finished by the engine
        (ADR-0025). In a directed or supervised project the sprint stays
        active and the engine hands the next move to a person.

        Returns:
            None              — autonomous: next sprint is active, keep looping.
            "idle"            — autonomous: sprint completed, no further sprint.
            "sprint_resolved" — directed/supervised: sprint left active, waiting
                                for a person to finish it.
        """
        if project.autonomy_level == "autonomous":
            return self._complete_and_advance(project, sprint)
        self._announce_resolved(project, sprint)
        return "sprint_resolved"

    def _complete_and_advance(self, project: Project, sprint: Sprint) -> str | None:
        """Complete *sprint* (autonomous projects only) and activate the next one."""
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

        next_sprint.status = "active"
        next_sprint.started_at = now
        self.store.save_sprint(next_sprint)
        self.emit_event(project, "engine.sprint_started", {
            "sprint_id": next_sprint.id,
            "sprint_title": next_sprint.title,
        }, sprint=next_sprint)
        return None

    def _announce_resolved(self, project: Project, sprint: Sprint) -> None:
        """Say once per resolution that the sprint is ready to be finished.

        ``engine.sprint_ready`` carries the ids of the tasks that resolved the
        sprint. A later pass over the same set adds nothing; a task added,
        run and finished changes the set, so the sprint is announced again.
        """
        task_ids = sorted(t.id for t in self.store.list_tasks(sprint_id=sprint.id))
        previous = self.store.list_sprint_events(
            sprint.id, event_types=["engine.sprint_ready"]
        )
        if previous and previous[-1].payload.get("task_ids") == task_ids:
            return
        self.emit_event(project, "engine.sprint_ready", {
            "sprint_id": sprint.id,
            "sprint_title": sprint.title,
            "task_ids": task_ids,
        }, sprint=sprint)
        self.emit_attention(project, sprint)

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
        """Raise one ``sprint_resolved`` attention turn when every task of a
        sprint is finished and the next move is a person's (a directed or
        supervised sprint left active, or an autonomous one with no successor).

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
