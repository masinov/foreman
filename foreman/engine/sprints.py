"""Moving a project from one sprint to the next."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..domain.models import FINISHED_TASK_STATUSES, Project, Sprint
from ..domain.settings import settings_of
from ..store import ForemanStore
from ..history.records import RunRecords
from ..mutations.checkpoint import SprintCheckpoints


class SprintFlow:
    """Activates, completes and announces sprints for one store."""

    def __init__(
        self, store: ForemanStore, records: RunRecords, utc_now: Callable[[], datetime]
    ) -> None:
        self.store = store
        self.records = records
        self.utc_now = utc_now

    def fully_resolved(self, sprint: Sprint) -> bool:
        """Return True when every task in the sprint is done or cancelled."""
        tasks = self.store.list_tasks(sprint_id=sprint.id)
        return bool(tasks) and all(t.status in FINISHED_TASK_STATUSES for t in tasks)

    def resolve(self, project: Project, sprint: Sprint) -> str | None:
        """Handle a fully resolved active sprint as the project says.

        The engine finishes the sprint only where the project lets Foreman
        finish sprints (``sprint_completion = "auto"``, ADR-0025 amendment).
        Otherwise the sprint stays active and the engine hands the next move
        to a person.

        Returns:
            None              — Foreman finishes: next sprint is active, keep looping.
            "idle"            — Foreman finishes: sprint completed, no further sprint.
            "sprint_resolved" — a person finishes: sprint left active for them.
        """
        if settings_of(project).sprint_completion == "auto":
            return self._complete_and_advance(project, sprint)
        self._announce_resolved(project, sprint)
        return "sprint_resolved"

    def _complete_and_advance(self, project: Project, sprint: Sprint) -> str | None:
        """Complete *sprint* (where Foreman finishes sprints) and activate the next one."""
        now = self.utc_now().isoformat()
        sprint.status = "completed"
        sprint.completed_at = now
        self.store.save_sprint(sprint)
        self.emit_event(project, "engine.sprint_completed", {
            "sprint_id": sprint.id,
            "sprint_title": sprint.title,
        }, sprint=sprint)
        # The same checkpoint as when a user finishes it (spec 6.4).
        SprintCheckpoints(self.store, self.records).record(project, sprint)

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
        """Record one event of the sprint itself (ADR-0037)."""

        self.records.emit_sprint_event(sprint, event_type, payload)

    def emit_attention(self, project: Project, sprint: Sprint) -> None:
        """Raise one ``sprint_resolved`` attention turn when every task of a
        sprint is finished and the next move is a person's (a directed or
        supervised sprint left active, or an autonomous one with no successor).

        Autonomous runs that auto-advance to the next sprint do not call this.
        The turn is the sprint's: the digest leads with the sprint handoff, not
        a single (already-done) task.
        """

        self.records.emit_sprint_attention(sprint, "sprint_resolved")
