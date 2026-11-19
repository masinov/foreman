"""``_builtin:mark_done``: a task finished, and its worktree removed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ...domain.models import CompletionEvidence, Project, Task, utc_now_text
from ...domain.settings import settings_of
from ...notifications.policy import resolve_notification_policy
from ...repo.git import (
    is_worktree_clean,
)
from ...repo.worktrees import WorktreeError, WorktreeManager
from ...store import ForemanStore
from .base import BuiltinEventRecord, BuiltinExecutorBase, BuiltinResult, _task_worktree
from .completion import _completion_guard_payload


class MarkDoneStep(BuiltinExecutorBase):
    """Marking a task done."""

    def _mark_done(
        self,
        *,
        task: Task,
        project: Project,
        store: ForemanStore,
        evidence_builder: Callable[[Task, Project], CompletionEvidence | None] | None = None,
        working_dir: Path | None = None,
    ) -> BuiltinResult:
        task_dir = _task_worktree(project, task, working_dir)
        if task.branch_name and task_dir is not None and not is_worktree_clean(task_dir):
            return self._block_task(
                task,
                detail=(
                    "Task branch has uncommitted changes. Commit or discard task work before "
                    "marking the task done."
                ),
                event_type="engine.task_finalization_blocked",
                payload={
                    "branch": task.branch_name,
                    "target": project.default_branch,
                    "reason": "dirty_worktree",
                },
            )

        if settings_of(project).completion_guard_enabled:
            # The guard evaluates completion evidence via git diff against the
            # default branch.  After a successful merge the branch tip may equal
            # HEAD (fast-forward or --no-ff with no new commit), making the diff
            # empty even though real implementation was merged.  Detect this by
            # checking whether the default branch is now a direct ancestor of
            # the task branch — if it is, the branch has been absorbed.
            # The merge step already ran this guard before allowing the merge.
            if task.branch_name:
                if self._task_branch_is_absorbed(project, task):
                    if not self._task_has_successful_merge_run(task, store):
                        return self._block_task(
                            task,
                            detail=(
                                f"Task branch {task.branch_name!r} has no recorded successful "
                                f"merge into {project.default_branch!r}. Refusing to mark the "
                                "task done from unmerged branch state."
                            ),
                            event_type="engine.task_finalization_blocked",
                            payload={
                                "branch": task.branch_name,
                                "target": project.default_branch,
                                "reason": "missing_merge_record",
                            },
                        )
                else:
                    evidence = self._build_completion_evidence(
                        project=project,
                        task=task,
                        store=store,
                        evidence_builder=evidence_builder,
                    )
                    task.completion_evidence = evidence
                    if evidence is not None:
                        block_reason = self._completion_guard_block_reason(task, evidence, project, store)
                        if block_reason is not None:
                            task.status = "blocked"
                            task.blocked_reason = block_reason
                            task.workflow_current_step = None
                            task.workflow_carried_output = None
                            return BuiltinResult(
                                outcome="blocked",
                                detail=block_reason,
                                events=(
                                    BuiltinEventRecord(
                                        event_type="engine.completion_guard",
                                        payload=_completion_guard_payload(evidence),
                                    ),
                                ),
                            )
        task.status = "done"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.completed_at = task.completed_at or utc_now_text()
        removal_events = self._remove_task_worktree(project, task)
        return BuiltinResult(
            outcome="success",
            detail="Task marked done.",
            events=(self._task_completed_event(project, task), *removal_events),
        )

    @staticmethod
    def _task_completed_event(project: Project, task: Task) -> BuiltinEventRecord:
        """Announce that a task reached done.

        The single point where a task becomes done, so it is the only honest
        anchor for "a task finished": a workflow step completing is not the
        same claim, and the task row's ``completed_at`` is state rather than a
        moment in the log. ``notify`` records the policy that governed the
        announcement at the time it was made -- see ``foreman.notifications.delivery``.
        """

        return BuiltinEventRecord(
            event_type="task.completed",
            payload={
                "task_id": task.id,
                "title": task.title,
                "task_type": task.task_type,
                "branch": task.branch_name,
                "completed_at": task.completed_at,
                "notify": resolve_notification_policy(project, task),
            },
        )

    def _remove_task_worktree(
        self,
        project: Project,
        task: Task,
    ) -> tuple[BuiltinEventRecord, ...]:
        """Delete the finished task's worktree and forget its path.

        A done task has nothing left to edit, and leaving its tree behind
        would accumulate one full checkout per completed task.
        """

        recorded = task.worktree_path
        if not recorded:
            task.worktree_path = None
            return ()
        try:
            WorktreeManager(project).remove_path(Path(recorded))
        except (WorktreeError, OSError) as exc:
            return (
                BuiltinEventRecord(
                    event_type="engine.worktree_remove_failed",
                    payload={"path": recorded, "error": str(exc)},
                ),
            )
        task.worktree_path = None
        return (
            BuiltinEventRecord(
                event_type="engine.worktree_removed",
                payload={"path": recorded, "reason": "task_done"},
            ),
        )
