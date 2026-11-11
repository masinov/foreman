"""Built-in workflow step executors for Foreman."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import selectors
import subprocess
import time
from typing import TYPE_CHECKING, Any, Callable

from .context import context_directory, relative_project_path, write_project_context
from .git import GitMergeResult, head_sha, is_worktree_clean, merge_branch, merge_preflight, run_git
from .models import CompletionEvidence, Project, Task, utc_now_text
from .notifications import resolve_notification_policy
from .runner.process import ManagedProcess
from .engine.evidence import EvidenceBuilder
from .roles import load_roles
from .settings import settings_of
from .worktrees import WorktreeError, WorktreeManager

DEFAULT_TEST_TIMEOUT_SECONDS = 1800

if TYPE_CHECKING:
    from .store import ForemanStore


@dataclass(slots=True)
class BuiltinEventRecord:
    """One structured event emitted by a built-in step."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"


@dataclass(slots=True)
class BuiltinResult:
    """Normalized outcome from one built-in workflow step."""

    outcome: str
    detail: str
    events: tuple[BuiltinEventRecord, ...] = ()


class BuiltinExecutor:
    """Execute built-in Foreman workflow roles."""

    def execute(
        self,
        role_id: str,
        *,
        project: Project,
        task: Task,
        step_id: str,
        carried_output: str | None,
        store: ForemanStore | None = None,
        event_recorder: Callable[[BuiltinEventRecord], None] | None = None,
        evidence_builder: Callable[[Task, Project], CompletionEvidence | None] | None = None,
        working_dir: Path | None = None,
    ) -> BuiltinResult:
        """Dispatch one built-in role by identifier.

        ``evidence_builder`` lets the orchestrator supply its own completion
        evidence builder, so the merge guard sees the same role definitions
        (and their declared review kinds) that executed the workflow.

        ``working_dir`` is the task's git worktree. Built-ins that touch a
        working tree — running the test command, checking for uncommitted work
        — use it so they see what the agent actually produced, and never the
        operator's checkout.
        """

        task_dir = Path(working_dir) if working_dir is not None else _task_dir(project, task)
        if role_id == "_builtin:run_tests":
            return self._run_tests(
                project=project,
                working_dir=task_dir,
                event_recorder=event_recorder,
            )
        if role_id == "_builtin:context_write":
            return self._context_write(
                store=store,
                project=project,
                task=task,
                carried_output=carried_output,
                working_dir=task_dir,
            )
        if role_id == "_builtin:merge":
            return self._merge(
                project=project,
                task=task,
                store=store,
                evidence_builder=evidence_builder,
                working_dir=task_dir,
            )
        if role_id == "_builtin:mark_done":
            return self._mark_done(
                task=task,
                project=project,
                store=store,
                evidence_builder=evidence_builder,
                working_dir=task_dir,
            )
        if role_id == "_builtin:human_gate":
            return self._human_gate(task=task, step_id=step_id, carried_output=carried_output)
        raise ValueError(f"Unsupported builtin role: {role_id}")

    def _run_tests(
        self,
        *,
        project: Project,
        working_dir: Path,
        event_recorder: Callable[[BuiltinEventRecord], None] | None = None,
    ) -> BuiltinResult:
        settings = settings_of(project)
        command = settings.test_command.strip()
        emitted_events: list[BuiltinEventRecord] = []

        def emit(event_type: str, payload: dict[str, Any]) -> None:
            record = BuiltinEventRecord(event_type=event_type, payload=payload)
            if event_recorder is not None:
                event_recorder(record)
            else:
                emitted_events.append(record)

        if not command:
            detail = "Project test_command is not configured."
            emit(
                "engine.test_run",
                {
                    "command": command,
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "",
                    "output_tail": detail,
                },
            )
            return BuiltinResult(outcome="failure", detail=detail, events=tuple(emitted_events))

        timeout_seconds = settings.test_timeout_seconds
        emit(
            "engine.test_started",
            {
                "command": command,
                "timeout_seconds": timeout_seconds,
                "working_dir": str(working_dir),
            },
        )
        started_at = time.monotonic()
        proc = subprocess.Popen(
            ["bash", "-lc", command],
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=True,
        )
        assert proc.stdout is not None
        assert proc.stderr is not None
        # Registered (not pumped) so a shutdown signal kills the whole test
        # process group along with any agent processes.
        managed = ManagedProcess(proc, name="tests", pump=False)

        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
        selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        deadline = time.monotonic() + timeout_seconds if timeout_seconds > 0 else None
        timed_out = False

        try:
            while selector.get_map():
                remaining: float | None = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        break
                for key, _ in selector.select(timeout=remaining):
                    stream_name = str(key.data)
                    line = key.fileobj.readline()
                    if line == "":
                        selector.unregister(key.fileobj)
                        continue
                    text = line.rstrip("\n")
                    if stream_name == "stdout":
                        stdout_chunks.append(line)
                    else:
                        stderr_chunks.append(line)
                    emit(
                        "engine.test_output",
                        {
                            "command": command,
                            "stream": stream_name,
                            "text": text,
                        },
                    )
        finally:
            selector.close()
            if timed_out:
                managed.kill()
            else:
                proc.wait()
                managed.close()

        duration_seconds = round(max(time.monotonic() - started_at, 0.0), 1)
        stdout_text = "".join(stdout_chunks).strip()
        stderr_text = "".join(stderr_chunks).strip()
        output = _combine_output(stdout_text, stderr_text)
        output_tail = _tail_lines(output, 200)
        if timed_out:
            outcome = "failure"
            detail = (
                f"Test command timed out after {timeout_seconds}s and was killed."
                + (f"\n\n{output_tail}" if output_tail else "")
            )
            exit_code: int | None = None
        else:
            outcome = "success" if proc.returncode == 0 else "failure"
            verdict = "passed" if proc.returncode == 0 else "failed"
            detail = (
                f"Tests {verdict} in {duration_seconds:.1f}s (exit {proc.returncode})."
                + (f"\n\n{output_tail}" if output_tail else "")
            )
            exit_code = proc.returncode
        emit(
            "engine.test_run",
            {
                "command": command,
                "working_dir": str(working_dir),
                "exit_code": exit_code,
                "passed": exit_code == 0,
                "timed_out": timed_out,
                "duration_seconds": duration_seconds,
                "head_sha": _safe_head_sha(working_dir),
                "stdout": stdout_text,
                "stderr": stderr_text,
                "output_tail": output_tail,
            },
        )
        return BuiltinResult(
            outcome=outcome,
            detail=detail,
            events=tuple(emitted_events),
        )

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
            detail = "Task branch is not set."
            return BuiltinResult(
                outcome="failure",
                detail=detail,
                events=(
                    BuiltinEventRecord(
                        event_type="engine.merge_failed",
                        payload={"branch": "", "error": detail},
                    ),
                ),
            )

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

        try:
            integration_path = WorktreeManager(project).ensure_integration()
        except WorktreeError as exc:
            return BuiltinResult(
                outcome="failure",
                detail=str(exc),
                events=(
                    BuiltinEventRecord(
                        event_type="engine.merge_failed",
                        payload={"branch": task.branch_name, "error": str(exc)},
                    ),
                ),
            )

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

        # The merge lands in Foreman's own integration worktree; the
        # operator's checkout only ever sees the default-branch ref move.
        result: GitMergeResult = merge_branch(
            integration_path,
            source_branch=task.branch_name,
            target_branch=project.default_branch,
        )
        if result.success:
            return BuiltinResult(
                outcome="success",
                detail=result.detail,
                events=(
                    BuiltinEventRecord(
                        event_type="engine.merge",
                        payload={
                            "branch": task.branch_name,
                            "target": project.default_branch,
                            "worktree": str(integration_path),
                        },
                    ),
                ),
            )

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
        announcement at the time it was made -- see ``foreman.notifications``.
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

    def _human_gate(
        self,
        *,
        task: Task,
        step_id: str,
        carried_output: str | None,
    ) -> BuiltinResult:
        task.workflow_current_step = step_id
        task.workflow_carried_output = carried_output
        task.status = "blocked"
        task.blocked_reason = "Awaiting human approval"
        return BuiltinResult(
            outcome="paused",
            detail=task.blocked_reason,
        )

    def _context_write(
        self,
        *,
        store: ForemanStore | None,
        project: Project,
        task: Task,
        carried_output: str | None,
        working_dir: Path | None = None,
    ) -> BuiltinResult:
        if store is None:
            raise ValueError("Context projection requires a store.")

        projection = write_project_context(
            store,
            project,
            current_task=task,
            carried_output=carried_output,
            mirror_dirs=_context_mirror_dirs(project, working_dir),
        )
        return BuiltinResult(
            outcome="success",
            detail="Runtime context written.",
            events=tuple(
                BuiltinEventRecord(
                    event_type="engine.context_write",
                    payload={"path": relative_project_path(project, path)},
                )
                for path in projection.written_paths
            ),
        )

    # ── Completion evidence helpers ─────────────────────────────────────────

    def _build_completion_evidence(
        self,
        *,
        project: Project,
        task: Task,
        store: ForemanStore | None,
        evidence_builder: Callable[[Task, Project], CompletionEvidence | None] | None = None,
    ) -> CompletionEvidence | None:
        """Best-effort completion evidence build for pre-merge guard checks."""

        try:
            if evidence_builder is not None:
                return evidence_builder(task, project)
            if store is None:
                return None
            return EvidenceBuilder(store, load_roles()).build(task, project)
        except Exception:  # pragma: no cover - guard logic must not crash execution
            return None

    def _completion_guard_block_reason(
        self,
        task: Task,
        evidence: CompletionEvidence,
        project: Project,
        store: ForemanStore | None = None,
    ) -> str | None:
        """Return a block reason when merge-time evidence is too weak.

        A MergeWaiver can override blocks due to missing/incomplete acceptance criteria
        or docs-only-on-impl-task, but not blocks due to test failures,
        reviewer denial, or security reviewer denial.
        """

        if task.task_type not in {"feature", "fix", "refactor"}:
            return None

        if not evidence.changed_files:
            block_reason = "Blocking merge because the task branch has no file changes."
            if not self._active_waiver_applies(store, task, evidence, "no_code_delta"):
                return block_reason
        if self._changes_are_docs_or_tests_only(evidence.changed_files):
            block_reason = (
                "Blocking merge because only docs or tests changed for an implementation task."
            )
            if not self._active_waiver_applies(store, task, evidence, "docs_only_impl_task"):
                return block_reason
        # Gate on proof status - require explicit "passed"
        if evidence.proof_status != "passed":
            listed = evidence.failure_reasons or evidence.outstanding
            reasons = "; ".join(listed) if listed else "proof_status is " + evidence.proof_status
            block_reason = (
                f"Completion proof not passed. Blocking merge until proof_status is 'passed'. "
                f"Current: {evidence.proof_status}. Reasons: {reasons}"
            )
            # A waiver can cover missing or unmet criteria, never tests or review.
            waiver_type = self._waiver_type_for_proof_failure(evidence.failure_reasons)
            if waiver_type:
                if not self._active_waiver_applies(store, task, evidence, waiver_type):
                    return block_reason
            else:
                return block_reason
        # Gate on code review approval - require explicit approve
        if evidence.review_outcome != "approve":
            return (
                f"Code review not approved (outcome: {evidence.review_outcome!r}). "
                "Blocking merge until code review approves."
            )
        # Gate on security review for secure workflows - require explicit approve
        if project.workflow_id == "development_secure":
            if evidence.security_review_outcome != "approve":
                return (
                    f"Security review not approved (outcome: {evidence.security_review_outcome!r}). "
                    "Blocking merge until security review approves."
                )
        return None

    def _waiver_type_for_proof_failure(self, failure_reasons: tuple[str, ...]) -> str | None:
        """Determine the waiver type that could apply given failure reasons.

        Returns a waiver type only if ALL failures are waiveable proof deficiencies
        (missing/incomplete criteria). Never returns a waiver type if any failure
        involves tests, reviewer, or security.
        """
        non_waivable_markers = (
            "tests failed",
            "tests ran on",
            "exit code",
            "review",
            "security",
        )
        reasons_lower = [r.lower() for r in failure_reasons]

        # If there are any non-waivable failures, no waiver can apply
        for reason in reasons_lower:
            if any(marker in reason for marker in non_waivable_markers):
                return None

        # All failures are proof-related — determine waiver type
        if not reasons_lower:
            return None

        if all("no acceptance criteria" in r for r in reasons_lower):
            return "missing_acceptance_criteria"

        if all("criterion not fully addressed" in r for r in reasons_lower):
            return "incomplete_criteria"

        return None

    def _active_waiver_applies(
        self,
        store: ForemanStore | None,
        task: Task,
        evidence: CompletionEvidence,
        waiver_type: str,
    ) -> bool:
        """Return True if an active waiver of the given type exists for the task/branch."""
        if not store or not task.branch_name or not evidence.head_sha:
            return False
        waiver = store.get_active_merge_waiver(task.id, task.branch_name, evidence.head_sha)
        return waiver is not None and waiver.waiver_type == waiver_type

    def _block_task(
        self,
        task: Task,
        *,
        detail: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> BuiltinResult:
        task.status = "blocked"
        task.blocked_reason = detail
        task.workflow_current_step = None
        task.workflow_carried_output = None
        return BuiltinResult(
            outcome="blocked",
            detail=detail,
            events=(BuiltinEventRecord(event_type=event_type, payload=payload),),
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

    def _changes_are_docs_or_tests_only(self, changed_files: tuple[str, ...]) -> bool:
        """Return True when every changed path is documentation or test-only."""

        normalized = [path.strip().lower() for path in changed_files if path.strip()]
        if not normalized:
            return False
        return all(self._is_docs_or_tests_path(path) for path in normalized)

    def _is_docs_or_tests_path(self, path: str) -> bool:
        """Classify one path as documentation or test-only."""

        candidate = Path(path)
        name = candidate.name.lower()
        parts = [part.lower() for part in candidate.parts]
        if name.endswith(".md") or name in {"readme", "readme.txt"}:
            return True
        if parts and parts[0] == "docs":
            return True
        if "tests" in parts:
            return True
        if name.startswith("test_") or name.endswith("_test.py"):
            return True
        return False


def _task_dir(project: Project, task: Task) -> Path:
    """Return the working tree a task's built-ins should act on."""

    worktree = _task_worktree(project, task, None)
    return worktree if worktree is not None else Path(project.repo_path)


def _task_worktree(
    project: Project,
    task: Task,
    working_dir: Path | None,
) -> Path | None:
    """Return the task's *own* worktree, or None when it has none.

    Callers that judge a tree — "is there uncommitted work here?" — must use
    this rather than :func:`_task_dir`. Falling back to ``project.repo_path``
    there would let an operator's unrelated edits in their own checkout block
    a task, and the operator's checkout is explicitly not the engine's to
    judge (ADR-0012).
    """

    candidate = working_dir if working_dir is not None else getattr(task, "worktree_path", None)
    if not candidate:
        return None
    path = Path(candidate)
    if path == Path(project.repo_path) or not path.is_dir():
        return None
    return path


def _context_mirror_dirs(project: Project, working_dir: Path | None) -> tuple[Path, ...]:
    """Return the worktree context directory to mirror the projection into."""

    if working_dir is None:
        return ()
    resolved = Path(working_dir)
    if resolved == Path(project.repo_path):
        return ()
    return (context_directory(project, root=resolved),)


def _completion_guard_payload(evidence: CompletionEvidence) -> dict[str, Any]:
    """Return the facts a blocked merge is recorded with."""

    return {
        "proof_status": evidence.proof_status,
        "tests_status": evidence.tests_status,
        "review_outcome": evidence.review_outcome,
        "head_sha": evidence.head_sha,
        "changed_files": list(evidence.changed_files),
        "reasons": [*evidence.failure_reasons, *evidence.outstanding],
    }


def _safe_head_sha(working_dir: Path) -> str | None:
    try:
        return head_sha(working_dir) or None
    except OSError:
        return None


def _combine_output(stdout: str, stderr: str) -> str:
    stdout = stdout.strip()
    stderr = stderr.strip()
    if stdout and stderr:
        return f"{stdout}\n{stderr}"
    return stdout or stderr


def _tail_lines(text: str, limit: int) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[-limit:])
