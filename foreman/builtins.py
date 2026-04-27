"""Built-in workflow step executors for Foreman."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import selectors
import subprocess
from typing import TYPE_CHECKING, Any, Callable

from .context import relative_project_path, write_project_context
from .git import GitMergeResult, is_worktree_clean, merge_branch, merge_preflight, run_git
from .models import CompletionEvidence, Project, Task, utc_now_text

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
    ) -> BuiltinResult:
        """Dispatch one built-in role by identifier."""

        if role_id == "_builtin:run_tests":
            return self._run_tests(project=project, event_recorder=event_recorder)
        if role_id == "_builtin:context_write":
            return self._context_write(
                store=store,
                project=project,
                task=task,
                carried_output=carried_output,
            )
        if role_id == "_builtin:merge":
            return self._merge(project=project, task=task, store=store)
        if role_id == "_builtin:mark_done":
            return self._mark_done(task=task, project=project, store=store)
        if role_id == "_builtin:human_gate":
            return self._human_gate(task=task, step_id=step_id, carried_output=carried_output)
        raise ValueError(f"Unsupported builtin role: {role_id}")

    def _run_tests(
        self,
        *,
        project: Project,
        event_recorder: Callable[[BuiltinEventRecord], None] | None = None,
    ) -> BuiltinResult:
        command = str(project.settings.get("test_command", "")).strip()
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

        emit("engine.test_started", {"command": command})
        proc = subprocess.Popen(
            ["bash", "-lc", command],
            cwd=Path(project.repo_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        assert proc.stderr is not None

        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
        selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        while selector.get_map():
            for key, _ in selector.select():
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

        proc.wait()
        stdout_text = "".join(stdout_chunks).strip()
        stderr_text = "".join(stderr_chunks).strip()
        output = _combine_output(stdout_text, stderr_text)
        output_tail = _tail_lines(output, 200)
        outcome = "success" if proc.returncode == 0 else "failure"
        detail = output_tail or f"Command exited with {proc.returncode}."
        emit(
            "engine.test_run",
            {
                "command": command,
                "exit_code": proc.returncode,
                "passed": proc.returncode == 0,
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

        # Run full merge preflight
        preflight = merge_preflight(
            project.repo_path,
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

        if _bool_setting(project, "completion_guard_enabled", default=True):
            evidence = self._build_completion_evidence(
                project=project,
                task=task,
                store=store,
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
                            payload={
                                "verdict": evidence.verdict,
                                "score": evidence.score,
                                "score_breakdown": evidence.score_breakdown,
                                "changed_files": list(evidence.changed_files),
                                "reasons": list(evidence.verdict_reasons),
                            },
                        ),
                    ),
                )

        result: GitMergeResult = merge_branch(
            project.repo_path,
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
                outcome="failure",
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
    ) -> BuiltinResult:
        if task.branch_name and not is_worktree_clean(project.repo_path):
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

        if _bool_setting(project, "completion_guard_enabled", default=True):
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
                                        payload={
                                            "verdict": evidence.verdict,
                                            "score": evidence.score,
                                            "score_breakdown": evidence.score_breakdown,
                                            "changed_files": list(evidence.changed_files),
                                            "reasons": list(evidence.verdict_reasons),
                                        },
                                    ),
                                ),
                            )
        task.status = "done"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.completed_at = task.completed_at or utc_now_text()
        return BuiltinResult(outcome="success", detail="Task marked done.")

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
    ) -> BuiltinResult:
        if store is None:
            raise ValueError("Context projection requires a store.")

        projection = write_project_context(
            store,
            project,
            current_task=task,
            carried_output=carried_output,
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
    ) -> CompletionEvidence | None:
        """Best-effort completion evidence build for pre-merge guard checks."""

        if store is None:
            return None
        try:
            from .orchestrator import ForemanOrchestrator

            return ForemanOrchestrator(store).build_completion_evidence(task, project)
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
            block_reason = (
                f"Completion evidence too weak (verdict: {evidence.verdict}). "
                "Blocking merge because the task branch has no material file changes."
            )
            if not self._active_waiver_applies(store, task, evidence, "no_code_delta"):
                return block_reason
        if self._changes_are_docs_or_tests_only(evidence.changed_files):
            block_reason = (
                f"Completion evidence too weak (verdict: {evidence.verdict}). "
                "Blocking merge because only docs or tests changed for an implementation task."
            )
            if not self._active_waiver_applies(store, task, evidence, "docs_only_impl_task"):
                return block_reason
        # Gate on proof status - require explicit "passed"
        if evidence.proof_status != "passed":
            reasons = "; ".join(evidence.failure_reasons) if evidence.failure_reasons else "proof_status is " + evidence.proof_status
            block_reason = (
                f"Completion proof not passed. Blocking merge until proof_status is 'passed'. "
                f"Current: {evidence.proof_status}. Reasons: {reasons}"
            )
            # Check for applicable waiver (only for proof-related deficiencies, never for tests/score)
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
        involves tests, score, reviewer, or security.
        """
        non_waivable_markers = (
            "tests failed",
            "exit code",
            "evidence score too low",
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

    def _task_branch_has_committed_delta(self, project: Project, task: Task) -> bool | None:
        if not task.branch_name:
            return None
        result = run_git(
            project.repo_path,
            "rev-list",
            "--right-only",
            "--count",
            f"{project.default_branch}...{task.branch_name}",
            check=False,
        )
        if result.returncode != 0:
            return None
        try:
            return int(result.stdout or "0") > 0
        except ValueError:
            return None

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


def _bool_setting(project: Project, key: str, *, default: bool) -> bool:
    value = project.settings.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    return default


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
