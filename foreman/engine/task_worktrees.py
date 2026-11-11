"""Giving each task its own checkout (ADR-0012).

``TaskWorktrees`` creates the task's worktree on its first visit, records
where it is, and reclaims idle trees so a project stays under its cap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import Project, Task
from ..store import ForemanStore
from ..worktrees import WorktreeError, WorktreeManager, enforce_worktree_limit, task_slug
from .errors import OrchestratorError
from .records import RunRecords
from .task_writes import TaskWrites


class TaskWorktrees:
    """Per-task worktrees for the projects of one store."""

    def __init__(self, store: ForemanStore, *, records: RunRecords, tasks: TaskWrites) -> None:
        self.store = store
        self.records = records
        self.tasks = tasks
        self.managers: dict[str, WorktreeManager] = {}

    def manager(self, project: Project) -> WorktreeManager:
        """Return the worktree manager for one project, created once per run."""

        manager = self.managers.get(project.id)
        if manager is None or manager.project.repo_path != project.repo_path:
            manager = WorktreeManager(project)
            self.managers[project.id] = manager
        return manager

    def ensure(self, project: Project, task: Task) -> Path | None:
        """Return the task's own checkout, creating it on the first develop visit.

        Every agent step, every test run, and every branch invariant works in
        this tree. The operator's checkout is never checked out or merged by
        the engine, so a person editing it — or a second engine — cannot
        corrupt a run. Existing in-progress tasks get a worktree here on their
        next visit; their branch already exists, so the tree is just added.
        """

        if not task.branch_name:
            return None
        manager = self.manager(project)
        if not manager.is_git_repository():
            return None
        self.reclaim_for(project, task, manager)
        path = manager.ensure(task)
        recorded = str(path)
        if task.worktree_path != recorded:
            task.worktree_path = recorded
            self.tasks.save(task)
        return path

    def reclaim_for(
        self,
        project: Project,
        task: Task,
        manager: WorktreeManager,
    ) -> None:
        """Make room under ``max_live_worktrees`` before this task's tree exists.

        Enforced here rather than after the fact so the cap bounds peak disk
        use, not just its steady state. A reclaim is invisible to the task that
        loses its tree — the branch keeps the work and the next visit recreates
        the checkout — so it is recorded, not raised.
        """

        try:
            outcome = enforce_worktree_limit(
                self.store, project, keep_slug=task_slug(task), manager=manager
            )
        except WorktreeError as exc:
            # Reclaiming is an optimisation; failing it must not stop the task
            # that was about to run from getting its worktree.
            self.emit_event(
                task,
                "engine.worktree_reclaim_failed",
                {"error": str(exc)},
                detail=f"Could not enforce max_live_worktrees: {exc}",
            )
            return

        if outcome.reclaimed:
            self.emit_event(
                task,
                "engine.worktrees_reclaimed",
                {
                    "limit": outcome.limit,
                    "live_before": outcome.live_before,
                    "live_after": outcome.live_after,
                    "reclaimed": [entry.slug for entry in outcome.reclaimed],
                },
                detail=(
                    f"Reclaimed {len(outcome.reclaimed)} worktree(s) to stay under "
                    f"max_live_worktrees={outcome.limit}."
                ),
            )
        if outcome.over_limit:
            # Not a failure: the alternative was destroying uncommitted work.
            self.emit_event(
                task,
                "engine.worktree_limit_exceeded",
                {
                    "limit": outcome.limit,
                    "live_after": outcome.live_after,
                    "retained_dirty": [
                        entry.slug for entry in outcome.retained_dirty
                    ],
                },
                detail=(
                    f"{outcome.live_after} worktrees exceed max_live_worktrees="
                    f"{outcome.limit}; "
                    f"{len(outcome.retained_dirty)} hold uncommitted work and were "
                    f"kept."
                ),
            )

    def emit_event(
        self,
        task: Task,
        event_type: str,
        payload: dict[str, Any],
        *,
        detail: str,
    ) -> None:
        """Record one worktree-lifecycle event against a synthetic system run."""

        run = self.records.create_system_run(
            task,
            workflow_step="orchestrator",
            outcome="success",
            detail=detail,
        )
        self.records.emit_event(run, event_type, payload)

    def preflight(self, project: Project) -> None:
        """Fail a run at the start when the repository cannot host worktrees.

        Every task runs in a Foreman-owned worktree, so a git that is too old
        or a worktree root git would try to commit is a project-level problem.
        Discovering it here, before any task is leased, gives the operator one
        clear message instead of a task blocked halfway through a step.
        """

        try:
            self.manager(project).preflight()
        except WorktreeError as exc:
            raise OrchestratorError(str(exc)) from exc
