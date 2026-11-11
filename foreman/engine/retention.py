"""Pruning old history when a project asks for it."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from ..models import Project
from ..settings import ProjectSettings
from ..store import ForemanStore
from .limits import resolve_project_settings
from .records import RunRecords


class Retention:
    """Applies a project's retention settings to its events, runs and prompts."""

    def __init__(
        self, store: ForemanStore, records: RunRecords, utc_now: Callable[[], datetime]
    ) -> None:
        self.store = store
        self.records = records
        self.utc_now = utc_now

    def prune_old_history(
        self,
        project: Project,
        *,
        settings: ProjectSettings | None = None,
    ) -> dict[str, int]:
        """Prune old project history according to per-type retention settings.

        Reads three optional retention settings through the validated
        ``ProjectSettings`` model:

        - ``event_retention_days`` — hard-delete old events
        - ``run_retention_days`` — hard-delete old terminal runs and their events
        - ``prompt_retention_days`` — null out prompt_text on old terminal runs

        Each setting is independent and disabled when unset. Returns a dict
        with counts for each type that was actually pruned.
        """

        counts: dict[str, int] = {}
        if settings is None:
            settings = resolve_project_settings(project)

        event_days = settings.event_retention_days
        if event_days is not None:
            cutoff = self.cutoff(event_days)
            n = self.store.prune_old_events(project_id=project.id, older_than=cutoff)
            if n > 0:
                counts["events"] = n
                self.emit_pruned_event(project, "engine.event_pruned", n, cutoff)

        run_days = settings.run_retention_days
        if run_days is not None:
            cutoff = self.cutoff(run_days)
            n = self.store.prune_old_runs(project_id=project.id, older_than=cutoff)
            if n > 0:
                counts["runs"] = n
                self.emit_pruned_event(project, "engine.run_pruned", n, cutoff)

        prompt_days = settings.prompt_retention_days
        if prompt_days is not None:
            cutoff = self.cutoff(prompt_days)
            n = self.store.strip_old_run_prompts(project_id=project.id, older_than=cutoff)
            if n > 0:
                counts["prompts"] = n
                self.emit_pruned_event(project, "engine.prompt_stripped", n, cutoff)

        return counts

    def cutoff(self, days: int) -> str:
        """Return an ISO 8601 UTC timestamp ``days`` before now."""

        return (
            self.utc_now() - timedelta(days=days)
        ).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def emit_pruned_event(
        self,
        project: Project,
        event_type: str,
        count: int,
        older_than: str,
    ) -> None:
        """Emit a project-scoped lifecycle event for a completed pruning operation."""

        task = self.records.select_project_system_task(project.id)
        if task is None:
            return
        run = self.records.create_system_run(
            task,
            workflow_step="orchestrator",
            outcome="success",
            detail=f"{event_type}: {count} rows older than {older_than}.",
        )
        self.records.emit_event(run, event_type, {"count": count, "older_than": older_than})

    # Keep the old name as a thin delegate so any existing call sites outside
    # this class continue to work during the transition period.
