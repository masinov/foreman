"""What is checked before a step runs: the worktree, the branch, the limits.
"""

from __future__ import annotations

from typing import Any

from ...domain.models import Project, Task
from ...domain.settings import ProjectSettings
from ...repo.git import (
    GitError,
    branch_exists,
    head_sha,
    worktree_branch,
)
from ...repo.worktrees import WorktreeError
from ..errors import OrchestratorError
from .base import WorkflowRunnerBase


class StepChecks(WorkflowRunnerBase):
    """The checks before a step."""

    def _branch_commit(self, project: Project, task: Task) -> str | None:
        """The commit the task's branch points at now, or None if it has none."""

        if not task.branch_name:
            return None
        try:
            return head_sha(project.repo_path, f"refs/heads/{task.branch_name}")
        except GitError:
            return None

    def _task_worktree_problem(self, project: Project, task: Task) -> str | None:
        """Say why a task's worktree cannot host a step, or None when it can.

        The operator's checkout is not consulted: what is checked out there
        is none of the engine's business.
        """

        try:
            worktree_path = self.task_worktrees.ensure(project, task)
            if worktree_path is None:
                raise OrchestratorError(f"Task branch {task.branch_name!r} has no worktree.")
            if not branch_exists(project.repo_path, task.branch_name):
                raise OrchestratorError(f"Task branch {task.branch_name!r} does not exist.")
            active_branch = worktree_branch(worktree_path)
            if active_branch != task.branch_name:
                raise OrchestratorError(
                    f"Worktree {worktree_path} should be on task branch "
                    f"{task.branch_name!r} but is on {active_branch!r}."
                )
        except (OrchestratorError, WorktreeError, GitError) as exc:
            return str(exc)
        return None

    def _limit_reached(
        self,
        task: Task,
        step: str,
        visit_count: int,
        settings: ProjectSettings,
    ) -> dict[str, Any] | None:
        """Return how to block the task when a project limit is reached.

        Checked in order: visits to this step, the task's cost, the sprint's
        cost, the task's time. A limit of 0 is off. The result is the keyword
        arguments for ``_block_at_step``.
        """

        max_step_visits = settings.max_step_visits
        if visit_count > max_step_visits:
            return {
                "detail": (
                    f"Step '{step}' visited {visit_count} times "
                    f"(limit: {max_step_visits}). Stuck in a loop."
                ),
                "event_type": "workflow.loop_limit",
                "payload": {
                    "step": step,
                    "visit_count": visit_count,
                    "max_visits": max_step_visits,
                },
                "attention_trigger": "loop_limit",
            }

        task_cost = sum(run.cost_usd for run in self.store.list_runs(task_id=task.id))
        cost_limit = settings.cost_limit_per_task_usd
        # 0 is the documented "off" value, and what the settings screen saves.
        if cost_limit > 0 and task_cost >= cost_limit:
            return {
                "detail": f"Task cost ${task_cost:.2f} exceeds limit ${cost_limit:.2f}",
                "event_type": "gate.cost_exceeded",
                "payload": {"limit_usd": cost_limit, "actual_usd": task_cost, "scope": "task"},
            }

        sprint_cost_limit = settings.cost_limit_per_sprint_usd
        sprint_cost = float(self.store.run_totals(sprint_id=task.sprint_id)["total_cost_usd"])
        if sprint_cost_limit > 0 and sprint_cost >= sprint_cost_limit:
            return {
                "detail": (
                    f"Sprint cost ${sprint_cost:.2f} exceeds limit ${sprint_cost_limit:.2f}"
                ),
                "event_type": "gate.cost_exceeded",
                "payload": {
                    "limit_usd": sprint_cost_limit,
                    "actual_usd": sprint_cost,
                    "scope": "sprint",
                },
            }

        task_duration_ms = sum(
            run.duration_ms or 0 for run in self.store.list_runs(task_id=task.id)
        )
        time_limit_ms = settings.time_limit_per_task_ms
        if time_limit_ms > 0 and task_duration_ms >= time_limit_ms:
            return {
                "detail": (
                    f"Task time {task_duration_ms/1000:.1f}s exceeds limit "
                    f"{time_limit_ms/1000:.1f}s"
                ),
                "event_type": "gate.time_exceeded",
                "payload": {
                    "task_id": task.id,
                    "total_duration_ms": task_duration_ms,
                    "time_limit_ms": time_limit_ms,
                },
            }
        return None
