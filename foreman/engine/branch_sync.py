"""Keeping a task branch workable before a develop pass.

A task can wait a long time between visits while the default branch moves,
and a merge can fail on a conflict. These functions refresh the task branch
from the default branch in the task's own worktree and, when that conflicts,
turn the conflict into instructions for the developer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import context_directory
from ..git import (
    branch_exists,
    commits_behind,
    is_worktree_clean,
    merge_in_progress,
    sync_branch_with_base,
)
from ..models import Project, Task


def task_working_dir(project: Project, task: Task) -> Path:
    """Return the directory a step for this task should run in."""

    recorded = task.worktree_path
    if recorded and Path(recorded).is_dir():
        return Path(recorded)
    return Path(project.repo_path)


def context_mirror_dirs(project: Project, task: Task) -> tuple[Path, ...]:
    """Return the worktree context directory the projection is mirrored into."""

    working_dir = task_working_dir(project, task)
    if working_dir == Path(project.repo_path):
        return ()
    return (context_directory(project, root=working_dir),)


def prepare_task_branch_for_step(
    *,
    project: Project,
    task: Task,
    step: str,
    carried_output: str | None,
) -> tuple[str | None, tuple[str, dict[str, Any]] | None]:
    """Prepare one task branch before a native role step.

    Merge conflicts are special: the next develop pass should work from an
    existing task branch that has been refreshed against the latest default
    branch whenever that refresh is clean. If the refresh still conflicts,
    carry explicit resolution guidance into the developer prompt and force
    the usual develop -> review cycle after the resolution.
    """

    if step != "develop" or not task.branch_name:
        return carried_output, None

    # Every merge below happens in the task's own worktree; the operator's
    # checkout is never a party to conflict recovery.
    work_dir = task_working_dir(project, task)

    if merge_in_progress(work_dir):
        # The previous develop pass was cut off (quota, shutdown) while
        # concluding a merge. Aborting it here would throw away the
        # developer's conflict resolution; leave the tree as it is and say
        # so, because the resumed session knows where it stopped.
        guidance = append_feedback_note(
            carried_output,
            (
                f"A merge into branch {task.branch_name!r} is still in progress in the "
                "working tree (MERGE_HEAD exists) from the previous pass. Finish "
                "resolving it and commit the merge before continuing the task."
            ),
        )
        return (
            guidance,
            (
                "engine.branch_sync",
                {
                    "step": step,
                    "branch": task.branch_name,
                    "target": project.default_branch,
                    "mode": "merge_in_progress",
                    "detail": "Unconcluded merge left by the previous pass; not aborted.",
                },
            ),
        )

    if not is_merge_conflict_feedback(carried_output):
        return refresh_task_branch(
            project=project,
            task=task,
            step=step,
            carried_output=carried_output,
        )

    sync_result = sync_branch_with_base(
        work_dir,
        task.branch_name,
        project.default_branch,
    )
    if sync_result.success:
        guidance = append_feedback_note(
            carried_output,
            (
                f"Foreman refreshed branch {task.branch_name!r} with the latest "
                f"{project.default_branch!r} before this develop pass. Review the "
                "merged base-branch changes, make any remaining adjustments, and end "
                "with TASK_COMPLETE. This conflict-resolution pass will go back "
                "through code review before merge."
            ),
        )
        return (
            guidance,
            (
                "engine.branch_sync",
                {
                    "step": step,
                    "branch": task.branch_name,
                    "target": project.default_branch,
                    "mode": "merge_conflict_recovery",
                    "detail": sync_result.detail,
                },
            ),
        )

    guidance = append_feedback_note(
        carried_output,
        (
            f"You are resolving a merge conflict against {project.default_branch!r}. "
            f"Reconcile branch {task.branch_name!r} with the latest "
            f"{project.default_branch!r} so it merges cleanly, then complete another "
            "develop pass. Your conflict-resolution changes will go back through code "
            "review before merge.\n\n"
            f"Latest merge attempt detail:\n{sync_result.detail}"
        ),
    )
    return (
        guidance,
        (
            "engine.branch_sync_conflict",
            {
                "step": step,
                "branch": task.branch_name,
                "target": project.default_branch,
                "mode": "merge_conflict_recovery",
                "detail": sync_result.detail,
            },
        ),
    )


def refresh_task_branch(
    *,
    project: Project,
    task: Task,
    step: str,
    carried_output: str | None,
) -> tuple[str | None, tuple[str, dict[str, Any]] | None]:
    """Bring a task branch up to date with the default branch before a develop pass.

    A task can wait a long time between visits (a human gate, a quota
    reset, a review round) while the default branch moves. Merging the
    base in now, while the merge is clean, means the developer works on
    current code and the final merge cannot conflict on changes it never
    saw. A refresh that conflicts is handed to the developer as guidance,
    exactly like a merge conflict found at the end.
    """

    branch = task.branch_name or ""
    work_dir = task_working_dir(project, task)
    if not branch_exists(project.repo_path, branch):
        return carried_output, None
    behind = commits_behind(project.repo_path, branch, project.default_branch)
    if behind <= 0:
        return carried_output, None
    if not is_worktree_clean(work_dir):
        return carried_output, None

    sync_result = sync_branch_with_base(work_dir, branch, project.default_branch)
    payload = {
        "step": step,
        "branch": branch,
        "target": project.default_branch,
        "mode": "refresh",
        "commits_behind": behind,
        "detail": sync_result.detail,
    }
    if sync_result.success:
        guidance = append_feedback_note(
            carried_output,
            (
                f"Foreman refreshed branch {branch!r} with the latest "
                f"{project.default_branch!r} ({behind} new commit(s)) before this "
                "develop pass. Review the merged base-branch changes where they touch "
                "your work; no other action is needed."
            ),
        )
        return guidance, ("engine.branch_sync", payload)

    payload["mode"] = "refresh_conflict"
    guidance = append_feedback_note(
        carried_output,
        (
            f"Branch {branch!r} is {behind} commit(s) behind {project.default_branch!r} "
            "and merging the base branch into it conflicts. Reconcile the branch with "
            f"the latest {project.default_branch!r} first (resolve the conflict, commit "
            "the merge), then continue the task. The result goes through test and "
            "review as usual.\n\n"
            f"Merge attempt detail:\n{sync_result.detail}"
        ),
    )
    return guidance, ("engine.branch_sync_conflict", payload)


def is_merge_conflict_feedback(text: str | None) -> bool:
    if not text:
        return False
    normalized = text.lower()
    return "merge conflict against" in normalized or "conflict (" in normalized


def append_feedback_note(existing: str | None, note: str) -> str:
    existing = (existing or "").strip()
    note = note.strip()
    if not existing:
        return note
    return f"{existing}\n\n{note}"
