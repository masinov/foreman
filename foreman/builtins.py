"""Built-in workflow step executors for Foreman."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import Any

from .git import GitMergeResult, merge_branch
from .models import Project, Task, utc_now_text


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
    ) -> BuiltinResult:
        """Dispatch one built-in role by identifier."""

        if role_id == "_builtin:run_tests":
            return self._run_tests(project=project)
        if role_id == "_builtin:merge":
            return self._merge(project=project, task=task)
        if role_id == "_builtin:mark_done":
            return self._mark_done(task=task)
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

    def _merge(self, *, project: Project, task: Task) -> BuiltinResult:
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

    def _mark_done(self, *, task: Task) -> BuiltinResult:
        task.status = "done"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.completed_at = task.completed_at or utc_now_text()
        return BuiltinResult(
            outcome="success",
            detail="Task marked done.",
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
