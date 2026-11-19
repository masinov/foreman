"""A project's task worktrees (ADR-0012): listing and pruning them.
"""

from __future__ import annotations

from typing import Any

from ..domain.models import (
    Task,
)
from ..repo.worktrees import (
    WorktreeEntry,
    WorktreeError,
    WorktreeManager,
    max_live_worktrees,
    prune_project_worktrees,
    worktree_root,
)
from .base import Service
from .errors import InvalidRequestError


class WorktreeService(Service):
    """A project's task worktrees: listing and pruning them."""

    def list_worktrees(self, project_id: str) -> dict[str, Any]:
        """Return the Foreman-owned worktrees for one project.

        The project screen shows what the engine is holding on disk so an
        operator can see whether a prune would free anything before running it.
        """

        project = self._require_project(project_id)
        tasks_by_path = {
            task.worktree_path: task
            for task in self.store.list_tasks(project_id=project.id)
            if task.worktree_path
        }
        try:
            entries = WorktreeManager(project).list()
        except WorktreeError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return {
            "project_id": project.id,
            "root": str(worktree_root(project)),
            "max_live_worktrees": max_live_worktrees(project),
            "worktrees": [
                self._serialize_worktree(entry, tasks_by_path.get(str(entry.path)))
                for entry in entries
            ],
        }

    def prune_worktrees(
        self,
        project_id: str,
        *,
        requested_by: str | None = None,
    ) -> dict[str, Any]:
        """Remove the worktrees of done, cancelled, and vanished tasks.

        The same policy as ``foreman worktree prune``: it never touches the
        integration tree or a live task's tree, so it is safe to offer as a
        one-click control.
        """

        project = self._require_project(project_id)
        try:
            removed, kept = prune_project_worktrees(self.store, project)
        except WorktreeError as exc:
            raise InvalidRequestError(str(exc)) from exc

        return {
            "ok": "pruned",
            "project_id": project.id,
            "root": str(worktree_root(project)),
            "requested_by": self._requester(requested_by),
            "removed": [self._serialize_worktree(entry, None) for entry in removed],
            "kept": [self._serialize_worktree(entry, None) for entry in kept],
        }

    @staticmethod
    def _serialize_worktree(
        entry: WorktreeEntry,
        task: Task | None,
    ) -> dict[str, Any]:
        return {
            "slug": entry.slug,
            "path": str(entry.path),
            "branch": entry.branch,
            "exists": entry.exists,
            "is_integration": entry.is_integration,
            "owned": entry.owned,
            "task_id": task.id if task is not None else None,
            "task_key": (task.task_key or task.id) if task is not None else None,
            "task_status": task.status if task is not None else None,
        }
