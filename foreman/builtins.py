"""Built-in workflow step executors for Foreman."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING, Any

from .context import relative_project_path, write_project_context
from .git import GitMergeResult, merge_branch
from .models import CompletionEvidence, Project, Task, utc_now_text

if TYPE_CHECKING:
    from .store import ForemanStore


@dataclass(slots=True)
class BuiltinEventRecord:
    """One structured event emitted by a built-in step."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


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
    ) -> BuiltinResult:
        """Dispatch one built-in role by identifier."""

        if role_id == "_builtin:run_tests":
            return self._run_tests(project=project)
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

    def _run_tests(self, *, project: Project) -> BuiltinResult:
        command = str(project.settings.get("test_command", "")).strip()
        if not command:
            detail = "Project test_command is not configured."
            return BuiltinResult(
                outcome="failure",
                detail=detail,
                events=(
                    BuiltinEventRecord(
                        event_type="engine.test_run",
                        payload={
                            "command": command,
                            "exit_code": None,
                            "output_tail": detail,
                        },
                    ),
                ),
            )

        result = subprocess.run(
            ["bash", "-lc", command],
            cwd=Path(project.repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
        output = _combine_output(result.stdout, result.stderr)
        output_tail = _tail_lines(output, 200)
        outcome = "success" if result.returncode == 0 else "failure"
        detail = output_tail or f"Command exited with {result.returncode}."
        return BuiltinResult(
            outcome=outcome,
            detail=detail,
            events=(
                BuiltinEventRecord(
                    event_type="engine.test_run",
                    payload={
                        "command": command,
                        "exit_code": result.returncode,
                        "output_tail": output_tail,
                    },
                ),
            ),
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

        if _bool_setting(project, "completion_guard_enabled", default=True):
            evidence = self._build_completion_evidence(
                project=project,
                task=task,
                store=store,
            )
            task.completion_evidence = evidence
            if evidence is not None:
                block_reason = self._completion_guard_block_reason(task, evidence)
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
        del project, store
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
    ) -> str | None:
        """Return a block reason when merge-time evidence is too weak."""

        if task.task_type not in {"feature", "fix", "refactor"}:
            return None
        if not evidence.changed_files:
            return (
                f"Completion evidence too weak (verdict: {evidence.verdict}). "
                "Blocking merge because the task branch has no material file changes."
            )
        if self._changes_are_docs_or_tests_only(evidence.changed_files):
            return (
                f"Completion evidence too weak (verdict: {evidence.verdict}). "
                "Blocking merge because only docs or tests changed for an implementation task."
            )
        return None

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
