"""Agent executor implementations for Foreman.

This module provides AgentExecutor implementations that use the runner
backends to execute agent steps and capture events.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Project, Task, utc_now_text
from .orchestrator import AgentEventRecord, AgentExecutionResult, AgentExecutor
from .roles import RoleDefinition
from .runner.base import AgentEvent, AgentRunConfig, InfrastructureError
from .runner.claude_code import ClaudeCodeRunner


@dataclass(slots=True)
class RunnerExecutorConfig:
    """Configuration for the runner-based executor."""

    default_timeout_seconds: int = 3600
    default_max_cost_usd: float = 10.0
    default_permission_mode: str = "auto"
    capture_all_events: bool = True


class ClaudeCodeExecutor:
    """AgentExecutor implementation using Claude Code runner.

    This executor uses the ClaudeCodeRunner to execute agent steps
    and captures events for persistence.
    """

    def __init__(self, config: RunnerExecutorConfig | None = None) -> None:
        self.config = config or RunnerExecutorConfig()
        self.runner = ClaudeCodeRunner()

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
        """Execute one agent step using Claude Code."""
        config = self._build_run_config(
            role=role,
            project=project,
            prompt=prompt,
            session_id=session_id,
        )

        events: list[AgentEventRecord] = []
        start_time = time.monotonic()
        outcome = "error"
        detail = ""
        status = "failed"
        result_session_id = session_id
        cost_usd = 0.0
        token_count = 0
        model = config.model

        try:
            for event in self.runner.run(config):
                # Capture event
                if self.config.capture_all_events or event.event_type.startswith("signal."):
                    events.append(self._event_to_record(event))

                # Track cost
                if event.event_type == "agent.completed":
                    cost_usd = event.payload.get("cost_usd", cost_usd)
                    token_count = event.payload.get("token_count", token_count)
                    outcome = "done"
                    detail = event.payload.get("result", "") or "Completed successfully."
                    status = "completed"
                elif event.event_type == "agent.error":
                    detail = event.payload.get("error", "Agent error.")
                    outcome = "error"
                    status = "failed"
                elif event.event_type == "agent.killed":
                    reason = event.payload.get("reason", "unknown")
                    detail = f"Agent killed: {reason}"
                    outcome = "killed"
                    status = "failed"
                elif event.event_type == "signal.completion":
                    # Agent can signal completion with custom outcome
                    signal_outcome = event.payload.get("outcome")
                    if signal_outcome:
                        outcome = signal_outcome
                        detail = event.payload.get("detail", "")

        except InfrastructureError as exc:
            events.append(
                AgentEventRecord(
                    event_type="agent.error",
                    payload={"error": str(exc)},
                )
            )
            detail = str(exc)
            outcome = "error"
            status = "failed"

        duration_ms = int((time.monotonic() - start_time) * 1000)

        return AgentExecutionResult(
            outcome=outcome,
            detail=detail,
            status=status,
            session_id=result_session_id,
            cost_usd=cost_usd,
            token_count=token_count,
            duration_ms=duration_ms,
            model=model,
            events=tuple(events),
        )

    def _build_run_config(
        self,
        *,
        role: RoleDefinition,
        project: Project,
        prompt: str,
        session_id: str | None,
    ) -> AgentRunConfig:
        """Build runner config from role and project settings."""
        timeout = _project_timeout_seconds(project, self.config.default_timeout_seconds)
        max_cost = _float_setting(project, "runner_max_cost_usd", self.config.default_max_cost_usd)
        permission_mode = _string_setting(
            project,
            "runner_permission_mode",
            self.config.default_permission_mode,
        )

        return AgentRunConfig(
            backend="claude_code",
            model=role.agent.model,
            prompt=prompt,
            working_dir=Path(project.repo_path),
            session_id=session_id,
            permission_mode=permission_mode,
            disallowed_tools=list(role.agent.tools.disallowed),
            timeout_seconds=timeout,
            max_cost_usd=max_cost,
        )

    def _event_to_record(self, event: AgentEvent) -> AgentEventRecord:
        """Convert runner event to orchestrator event record."""
        return AgentEventRecord(
            event_type=event.event_type,
            payload=dict(event.payload),
            timestamp=event.timestamp,
        )


def _int_setting(project: Project, key: str, default: int) -> int:
    value = project.settings.get(key, default)
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _float_setting(project: Project, key: str, default: float) -> float:
    value = project.settings.get(key, default)
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _string_setting(project: Project, key: str, default: str) -> str:
    value = project.settings.get(key, default)
    return value if isinstance(value, str) else default


def _project_timeout_seconds(project: Project, default: int) -> int:
    """Return runner timeout seconds, preferring the product-level project setting."""

    time_limit_minutes = project.settings.get("time_limit_per_run_minutes")
    if isinstance(time_limit_minutes, bool):
        return default
    if isinstance(time_limit_minutes, int) and time_limit_minutes > 0:
        return time_limit_minutes * 60
    if isinstance(time_limit_minutes, float) and time_limit_minutes > 0:
        return int(time_limit_minutes * 60)
    return _int_setting(project, "runner_timeout_seconds", default)
