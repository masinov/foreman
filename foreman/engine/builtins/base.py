"""Dispatching a built-in role to its step, and what every step shares.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ...domain.models import CompletionEvidence, Project, Task
from ...repo.context import (
    context_directory,
    relative_project_path,
    write_project_context,
)
from ...repo.git import (
    head_sha,
)
from ...store import ForemanStore


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


def _safe_head_sha(working_dir: Path) -> str | None:
    try:
        return head_sha(working_dir) or None
    except OSError:
        return None


class BuiltinExecutorBase:
    """The dispatch, the human gate and the context write; the parts are the steps."""

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
