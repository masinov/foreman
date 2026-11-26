"""``_builtin:merge``: merging a task's branch into the default branch.

A branch behind the default branch is brought up to date and tested again
first (ADR-0026); the operator's checkout follows a merge when it is on the
default branch (ADR-0031).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ...domain.models import CompletionEvidence, Project, Task
from ...domain.settings import settings_of
from ...repo.adrs import Settlement, settle, touches_adrs
from ...repo.git import (
    CheckoutFollow,
    GitError,
    GitMergeResult,
    commits_behind,
    follow_branch_in_checkout,
    head_sha,
    is_worktree_clean,
    merge_branch,
    merge_preflight,
    push_branch,
    run_git,
    sync_branch_with_base,
)
from ...repo.worktrees import WorktreeError, WorktreeManager
from ...store import ForemanStore
from ..repo_facts import merge_facts
from .base import BuiltinEventRecord, BuiltinExecutorBase, BuiltinResult, _task_worktree
from .completion import _completion_guard_payload


def _follow_operator_checkout(project: Project, sha: str | None) -> BuiltinEventRecord | None:
    """Bring the project's own checkout to the merge, and say what happened.

    Nothing is said when that checkout is on another branch or already shows
    the merge. A checkout that could not be brought along is reported, not an
    error: the merge is done whatever happens there.
    """

    if not sha:
        return None
    try:
        followed = follow_branch_in_checkout(project.repo_path, project.default_branch, sha)
    except (GitError, OSError) as exc:
        followed = CheckoutFollow("left", reason=str(exc))
    if followed.state == "updated":
        return BuiltinEventRecord(
            event_type="engine.checkout_updated",
            payload={
                "path": str(project.repo_path),
                "branch": project.default_branch,
                "from_sha": followed.from_sha,
                "sha": sha,
            },
        )
    if followed.state == "left":
        return BuiltinEventRecord(
            event_type="engine.checkout_behind",
            payload={
                "path": str(project.repo_path),
                "branch": project.default_branch,
                "sha": sha,
                "reason": followed.reason,
            },
        )
    return None


def _merge_failed(branch: str, error: str) -> BuiltinResult:
    return BuiltinResult(
        outcome="failure",
        detail=error,
        events=(
            BuiltinEventRecord(
                event_type="engine.merge_failed",
                payload={"branch": branch, "error": error},
            ),
        ),
    )


def _read_head(repo_path: Path | str, ref: str) -> str | None:
    """The commit a ref points at, or None; a failed read is not the merge's failure."""

    try:
        return head_sha(repo_path, ref)
    except (GitError, OSError):
        return None


def _landed(
    project: Project,
    task: Task,
    integration_path: Path,
    result: GitMergeResult,
    *,
    target_before: str | None = None,
    branch_head: str | None = None,
    settlements: tuple[Settlement, ...] = (),
) -> BuiltinResult:
    """A merge that landed: bring a person's checkout along and push when asked.

    ``target_before`` and ``branch_head`` are the default branch's and the task
    branch's commits just before the merge; what the merge brought in is
    recorded on the event from them (ADR-0038).
    """

    numbered = [list(pair) for s in settlements for pair in s.numbered]
    adr_facts = {"adrs": numbered} if numbered else {}
    events = [
        BuiltinEventRecord(
            event_type="engine.merge",
            payload={
                "branch": task.branch_name,
                "target": project.default_branch,
                "worktree": str(integration_path),
                "sha": result.sha,
                **merge_facts(project.repo_path, target_before, branch_head, result.sha),
                **adr_facts,
            },
        )
    ]
    detail = result.detail
    for settlement in settlements:
        for old, new in settlement.numbered:
            detail = f"{detail}\nNumbered {old} as {new}."
    followed = _follow_operator_checkout(project, result.sha)
    if followed is not None:
        events.append(followed)
    remote = settings_of(project).merge_push_remote
    if remote:
        # The merge is done whatever the push does: a remote that is
        # down or refuses must not send finished work back to develop.
        pushed = push_branch(
            integration_path, remote=remote, branch=project.default_branch
        )
        if pushed.returncode == 0:
            events.append(
                BuiltinEventRecord(
                    event_type="engine.push",
                    payload={
                        "remote": remote,
                        "branch": project.default_branch,
                        "sha": result.sha,
                    },
                )
            )
            detail = f"{detail}\nPushed {project.default_branch} to {remote}."
        else:
            error = pushed.stderr or pushed.stdout or "git push failed"
            events.append(
                BuiltinEventRecord(
                    event_type="engine.push_failed",
                    payload={
                        "remote": remote,
                        "branch": project.default_branch,
                        "sha": result.sha,
                        "error": error,
                    },
                )
            )
            detail = (
                f"{detail}\nMerged, but not pushed: pushing "
                f"{project.default_branch} to {remote} failed. {error}"
            )
    return BuiltinResult(outcome="success", detail=detail, events=tuple(events))


def _not_landed(project: Project, task: Task, result: GitMergeResult) -> BuiltinResult:
    """A conflict goes back to develop; any other failure fails the step."""

    if result.conflict:
        detail = (
            f"Merge conflict against {project.default_branch!r}. Reconcile branch "
            f"{task.branch_name!r} with the latest {project.default_branch!r}, then "
            "complete another develop pass. Conflict-resolution changes must go back "
            "through code review before merge.\n\n"
            f"{result.detail}"
        )
        return BuiltinResult(
            outcome="conflict",
            detail=detail,
            events=(
                BuiltinEventRecord(
                    event_type="engine.merge_conflict",
                    payload={
                        "branch": task.branch_name,
                        "target": project.default_branch,
                        "error": result.detail,
                    },
                ),
            ),
        )

    return BuiltinResult(
        outcome="failure",
        detail=result.detail,
        events=(
            BuiltinEventRecord(
                event_type="engine.merge_failed",
                payload={
                    "branch": task.branch_name,
                    "error": result.detail,
                },
            ),
        ),
    )


class MergeStep(BuiltinExecutorBase):
    """Merging a task's branch."""

    def _merge(
        self,
        *,
        project: Project,
        task: Task,
        store: ForemanStore | None,
        evidence_builder: Callable[[Task, Project], CompletionEvidence | None] | None = None,
        working_dir: Path | None = None,
    ) -> BuiltinResult:
        if not task.branch_name:
            return _merge_failed("", "Task branch is not set.")

        # Work the developer left uncommitted in the task's own tree is not on
        # the branch, so merging would silently drop it. Refuse instead.
        task_dir = _task_worktree(project, task, working_dir)
        if task_dir is not None and not is_worktree_clean(task_dir):
            return self._block_task(
                task,
                detail=(
                    f"Task worktree {task_dir} has uncommitted changes. Commit or discard "
                    "them before merging."
                ),
                event_type="engine.merge_blocked",
                payload={
                    "branch": task.branch_name,
                    "target": project.default_branch,
                    "reason": "dirty_worktree",
                    "worktree": str(task_dir),
                },
            )

        # What lands must be what was tested and reviewed (ADR-0026). A branch
        # that lacks the default branch's head is brought up to date in the
        # task's own worktree and goes back to the test step; it is not merged.
        behind = commits_behind(project.repo_path, task.branch_name, project.default_branch)
        if behind > 0:
            return self._update_behind_branch(
                project=project, task=task, task_dir=task_dir, behind=behind
            )

        try:
            integration_path = WorktreeManager(project).ensure_integration()
        except WorktreeError as exc:
            return _merge_failed(task.branch_name, str(exc))

        # Run full merge preflight in the integration worktree: the tree the
        # merge will actually happen in is the one that has to be clean.
        preflight = merge_preflight(
            integration_path,
            source_branch=task.branch_name,
            target_branch=project.default_branch,
        )
        if not preflight.success:
            return self._block_task(
                task,
                detail=preflight.detail,
                event_type="engine.merge_blocked",
                payload={
                    "branch": task.branch_name,
                    "target": project.default_branch,
                    "reason": preflight.reason or "preflight_failed",
                },
            )

        if settings_of(project).completion_guard_enabled:
            refused = self._guard_completion(
                project=project, task=task, store=store, evidence_builder=evidence_builder
            )
            if refused is not None:
                return refused

        # The merge lands in Foreman's own integration worktree. A person's
        # checkout sitting on the default branch is then brought along, the
        # way a fast-forward pull would (ADR-0031).
        target_before = _read_head(integration_path, f"refs/heads/{project.default_branch}")
        branch_head = _read_head(project.repo_path, f"refs/heads/{task.branch_name}")
        # A decision a branch wrote as ``new-<slug>.md`` is numbered in the
        # merge commit, against the default branch as it is now (ADR-0040).
        # The branch is not touched, so what lands is what was tested, and the
        # number cannot be taken by a merge that landed since.
        settled: list[Settlement] = []
        adr_dir = settings_of(project).adr_dir

        def number_adrs(tree: Path) -> str | None:
            staged = run_git(tree, "diff", "--cached", "--name-only", "-z", "HEAD", check=False)
            if not touches_adrs(staged.stdout.split("\0"), adr_dir):
                return None
            settlement = settle(tree, adr_dir)
            if settlement is None:
                return None
            settled.append(settlement)
            return settlement.refusal()

        result: GitMergeResult = merge_branch(
            integration_path,
            source_branch=task.branch_name,
            target_branch=project.default_branch,
            finish=number_adrs if adr_dir else None,
        )
        if result.refused:
            return self._block_task(
                task,
                detail=result.detail,
                event_type="engine.merge_blocked",
                payload={
                    "branch": task.branch_name,
                    "target": project.default_branch,
                    "reason": "duplicate_adr_numbers",
                    "duplicates": [
                        {"number": number, "files": list(files)}
                        for s in settled
                        for number, files in s.duplicates
                    ],
                },
            )
        if result.success:
            return _landed(
                project,
                task,
                integration_path,
                result,
                target_before=target_before,
                branch_head=branch_head,
                settlements=tuple(settled),
            )
        return _not_landed(project, task, result)

    def _guard_completion(
        self,
        *,
        project: Project,
        task: Task,
        store: ForemanStore | None,
        evidence_builder: Callable[[Task, Project], CompletionEvidence | None] | None,
    ) -> BuiltinResult | None:
        """Build the task's evidence and refuse the merge when it falls short."""

        evidence = self._build_completion_evidence(
            project=project,
            task=task,
            store=store,
            evidence_builder=evidence_builder,
        )
        task.completion_evidence = evidence
        if evidence is None:
            return self._block_task(
                task,
                detail="Completion evidence could not be built. Cannot merge.",
                event_type="engine.completion_guard",
                payload={"error": "evidence_build_failed"},
            )
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
        return None

    def _update_behind_branch(
        self,
        *,
        project: Project,
        task: Task,
        task_dir: Path | None,
        behind: int,
    ) -> BuiltinResult:
        branch = task.branch_name or ""
        if task_dir is None:
            # The operator's checkout and the integration worktree are not
            # places to update a task branch (ADR-0012).
            return self._block_task(
                task,
                detail=(
                    f"Branch {branch!r} is {behind} commit(s) behind "
                    f"{project.default_branch!r} and the task has no worktree of its own "
                    "to update it in."
                ),
                event_type="engine.merge_blocked",
                payload={
                    "branch": branch,
                    "target": project.default_branch,
                    "reason": "no_task_worktree",
                    "commits_behind": behind,
                },
            )
        sync = sync_branch_with_base(task_dir, branch, project.default_branch)
        if sync.success:
            return BuiltinResult(
                outcome="updated",
                detail=(
                    f"Branch {branch!r} was {behind} commit(s) behind "
                    f"{project.default_branch!r}; merged {project.default_branch!r} into it. "
                    "It is tested again before it is merged."
                ),
                events=(
                    BuiltinEventRecord(
                        event_type="engine.branch_sync",
                        payload={
                            "step": "merge",
                            "branch": branch,
                            "target": project.default_branch,
                            "mode": "merge_update",
                            "commits_behind": behind,
                            "detail": sync.detail,
                        },
                    ),
                ),
            )
        if sync.conflict:
            detail = (
                f"Merge conflict against {project.default_branch!r}. Reconcile branch "
                f"{branch!r} with the latest {project.default_branch!r}, then "
                "complete another develop pass. Conflict-resolution changes must go back "
                "through code review before merge.\n\n"
                f"{sync.detail}"
            )
            return BuiltinResult(
                outcome="conflict",
                detail=detail,
                events=(
                    BuiltinEventRecord(
                        event_type="engine.merge_conflict",
                        payload={
                            "branch": branch,
                            "target": project.default_branch,
                            "error": sync.detail,
                        },
                    ),
                ),
            )
        return BuiltinResult(
            outcome="failure",
            detail=sync.detail,
            events=(
                BuiltinEventRecord(
                    event_type="engine.merge_failed",
                    payload={"branch": branch, "error": sync.detail},
                ),
            ),
        )

    def _task_branch_is_absorbed(self, project: Project, task: Task) -> bool:
        if not task.branch_name:
            return False
        ancestor_check = run_git(
            project.repo_path,
            "merge-base",
            "--is-ancestor",
            task.branch_name,
            project.default_branch,
            check=False,
        )
        return ancestor_check.returncode == 0

    def _task_has_successful_merge_run(self, task: Task, store: ForemanStore) -> bool:
        return any(
            run.workflow_step == "merge" and run.status == "completed" and run.outcome == "success"
            for run in store.list_runs(task_id=task.id)
        )
