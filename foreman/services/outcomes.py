"""Outcome numbers for a project or one of its sprints (ADR-0034)."""

from __future__ import annotations

from typing import Any

from ..domain.outcome_numbers import outcome_numbers
from .base import Service
from .errors import NotFoundError


class OutcomeService(Service):
    """How well a project's agents do, from what the engine recorded."""

    def numbers(self, project_id: str, *, sprint_id: str | None = None) -> dict[str, Any]:
        """The outcome numbers of *project_id*, or of one of its sprints."""

        project = self._require_project(project_id)
        sprint = None
        if sprint_id:
            sprint = self._require_sprint(sprint_id)
            if sprint.project_id != project.id:
                raise NotFoundError(f"Sprint {sprint_id} is not in project {project.id}.")
        tasks, runs, events = self.store.outcome_records(
            project.id, sprint_id=sprint.id if sprint is not None else None
        )
        return {
            "project_id": project.id,
            "sprint_id": sprint.id if sprint is not None else None,
            "sprint_title": sprint.title if sprint is not None else None,
            **outcome_numbers(tasks, runs, events).as_dict(),
        }
