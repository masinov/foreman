"""What the engine hands back: step results, run results, gate results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..models import Project, Task, TokenUsage, utc_now_text
from ..roles import RoleDefinition
from .errors import QuotaPauseError


@dataclass(slots=True)
class AgentEventRecord:
    """One structured event returned from an agent executor."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now_text)


@dataclass(slots=True)
class AgentExecutionResult:
    """Normalized output from one agent workflow step."""

    outcome: str
    detail: str = ""
    status: str = "completed"
    session_id: str | None = None
    cost_usd: float = 0.0
    token_count: int = 0
    token_usage: TokenUsage | None = None
    duration_ms: int | None = None
    model: str | None = None
    events: tuple[AgentEventRecord, ...] = ()
    events_streamed: bool = False
    retry_count: int = 0
    #: ``quota`` | ``preflight`` | ``infrastructure`` | ``agent`` when the run failed.
    failure_type: str | None = None
    #: ISO 8601 UTC time after which a quota failure may be retried.
    retry_after: str | None = None


@dataclass(slots=True)
class ProjectRunResult:
    """Summary of one orchestrator invocation."""

    project_id: str
    executed_task_ids: tuple[str, ...]
    blocked_task_ids: tuple[str, ...]
    stop_reason: str
    #: Set with ``stop_reason="quota_exhausted"``: when the backend said it will serve again.
    retry_after: str | None = None
    detail: str | None = None


@dataclass(slots=True)
class HumanGateResumeResult:
    """Summary of one human-gate decision and any resumed execution."""

    task: Task
    decision: str
    paused_step: str
    next_step: str
    deferred: bool
    carried_output: str | None = None
    note: str | None = None


class AgentExecutor(Protocol):
    """Execution protocol for workflow agent steps."""

    def execute(
        self,
        *,
        role: RoleDefinition,
        project: Project,
        task: Task,
        workflow_step: str,
        prompt: str,
        session_id: str | None,
        carried_output: str | None,
    ) -> AgentExecutionResult:
        """Execute one agent step and return normalized results."""


def quota_run_result(
    project: Project,
    exc: QuotaPauseError,
    executed_task_ids: list[str],
    blocked_task_ids: list[str],
) -> ProjectRunResult:
    """Summarize a pass that stopped because the backend quota ran out."""

    executed_task_ids.append(exc.task_id)
    return ProjectRunResult(
        project_id=project.id,
        executed_task_ids=tuple(executed_task_ids),
        blocked_task_ids=tuple(blocked_task_ids),
        stop_reason="quota_exhausted",
        retry_after=exc.retry_after,
        detail=exc.detail,
    )
