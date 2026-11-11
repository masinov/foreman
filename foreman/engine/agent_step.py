"""Running one agent step and turning its event stream into a result.

``AgentStepRunner`` launches the role's backend through ``run_with_retry``,
persists each event as it arrives, keeps the task lease alive while the
agent is silent, lets an operator's command interrupt the step, and settles
the run when the step is abandoned.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
import json
from typing import Any

from ..errors import EngineCommandInterrupt
from ..models import Project, Run, Task, TokenUsage
from ..outcomes import ERROR
from ..roles import RoleDefinition
from ..runner import AgentRunConfig, PreflightError, run_with_retry
from ..runner.base import AgentRunner as NativeAgentRunner
from ..runner.env import resolve_env
from ..runner.process import EngineShutdown
from .branch_sync import task_working_dir
from .coerce import coerce_float_value, coerce_int_value, optional_string
from .errors import LeaseLostError, OrchestratorError
from .leasing import TaskLeases
from .limits import project_timeout_seconds, resolve_project_settings, run_cost_ceiling
from .model_selection import resolve_step_model
from .output_contract import FINAL_MESSAGE_PHASES, extract_completion_output
from .records import RunRecords
from .results import AgentEventRecord, AgentExecutionResult, AgentExecutor

#: How often a silent agent step renews its lease and polls for commands.
DEFAULT_NATIVE_STEP_HEARTBEAT_SECONDS = 30.0


class AgentStepRunner:
    """Executes agent steps for one engine."""

    def __init__(
        self,
        *,
        agent_executor: AgentExecutor | None,
        agent_runners: dict[str, NativeAgentRunner],
        leases: TaskLeases,
        records: RunRecords,
        runner_sleep: Callable[[float], None] | None,
        utc_now: Callable[[], datetime],
        heartbeat_seconds: float,
        poll_commands: Callable[[str], None],
    ) -> None:
        self.agent_executor = agent_executor
        self.agent_runners = agent_runners
        self.leases = leases
        self.records = records
        self.runner_sleep = runner_sleep
        self.utc_now = utc_now
        self.heartbeat_seconds = heartbeat_seconds
        self.poll_commands = poll_commands

    def execute_guarded(
        self,
        *,
        run: Run,
        task: Task,
        project: Project,
        **kwargs: Any,
    ) -> AgentExecutionResult:
        """Run one agent step and settle its run row if the engine is interrupted.

        A shutdown signal or a lost lease is not an agent outcome: the run is
        recorded as ``killed`` with an explicit ``agent.killed`` event, the
        task keeps the resume point persisted before the step, and the
        interruption propagates so the engine exits.
        """

        try:
            return self.execute(task=task, project=project, **kwargs)
        except LeaseLostError as exc:
            self.abandon_run(
                run,
                task,
                project,
                reason=str(exc),
                gate_type="lease_lost",
                release_lease=False,
            )
            raise
        except EngineCommandInterrupt as exc:
            # An operator asked for this. The run is settled exactly as a
            # shutdown settles it — killed, task resumable at its persisted
            # step — and the resident engine decides afterwards whether the
            # task stays resumable (`pause`) or is parked (`stop_task`).
            self.abandon_run(
                run,
                task,
                project,
                reason=str(exc),
                gate_type="command",
                release_lease=True,
            )
            raise
        except (EngineShutdown, KeyboardInterrupt) as exc:
            self.abandon_run(
                run,
                task,
                project,
                reason=f"Engine stopped before the agent finished: {exc}",
                gate_type="shutdown",
                release_lease=True,
            )
            raise

    def abandon_run(
        self,
        run: Run,
        task: Task,
        project: Project,
        *,
        reason: str,
        gate_type: str,
        release_lease: bool,
    ) -> None:
        self.records.emit_event(
            run,
            "agent.killed",
            {"reason": reason, "gate_type": gate_type},
        )
        # The backend announced its session id at start; keep it on the run
        # so the resumed step continues that conversation instead of
        # re-reading the repository from scratch.
        self.records.complete_run(
            run,
            status="killed",
            outcome=ERROR,
            detail=reason,
            session_id=self.records.session_id_from_events(run) or run.session_id,
        )
        if release_lease:
            self.leases.release(task, project)
        else:
            self.leases.forget(task.id)

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
        model: str | None = None,
        event_recorder: Callable[[AgentEventRecord], None] | None = None,
    ) -> AgentExecutionResult:
        try:
            if self.agent_executor is not None:
                return self.agent_executor.execute(
                    role=role,
                    project=project,
                    task=task,
                    workflow_step=workflow_step,
                    prompt=prompt,
                    session_id=session_id,
                    carried_output=carried_output,
                )
            return self.execute_native(
                role=role,
                project=project,
                task=task,
                workflow_step=workflow_step,
                prompt=prompt,
                session_id=session_id,
                model=model,
                event_recorder=event_recorder,
            )
        except LeaseLostError:
            raise
        except Exception as exc:  # pragma: no cover - defensive fallback
            return AgentExecutionResult(
                outcome="error",
                detail=str(exc),
                status="failed",
                events=(
                    AgentEventRecord(
                        event_type="agent.error",
                        payload={"error": str(exc)},
                    ),
                ),
            )

    def execute_native(
        self,
        *,
        role: RoleDefinition,
        project: Project,
        task: Task,
        workflow_step: str,
        prompt: str,
        session_id: str | None,
        model: str | None = None,
        event_recorder: Callable[[AgentEventRecord], None] | None = None,
    ) -> AgentExecutionResult:
        runner = self.agent_runners.get(role.agent.backend)
        if runner is None:
            raise OrchestratorError(
                f"No native runner is configured for backend {role.agent.backend!r}."
            )

        if model is None:
            model = resolve_step_model(
                task=task,
                role=role,
                project=project,
                step_id=workflow_step,
                visit_count=task.step_visit_counts.get(workflow_step, 1) or 1,
            )
        model = model or ""
        try:
            resolved_env = resolve_env(role.agent.env)
        except PreflightError as exc:
            return AgentExecutionResult(
                outcome=ERROR,
                detail=str(exc),
                status="failed",
                model=model or None,
                events=(
                    AgentEventRecord(
                        event_type="agent.error",
                        payload={
                            "error": str(exc),
                            "preflight_failed": True,
                        },
                    ),
                ),
                failure_type="preflight",
            )
        config = AgentRunConfig(
            backend=role.agent.backend,
            model=model or None,
            prompt=prompt,
            # The agent edits its task's own worktree, never the operator's
            # checkout.
            working_dir=task_working_dir(project, task),
            session_id=session_id,
            permission_mode=role.agent.permission_mode,
            disallowed_tools=role.agent.tools.disallowed,
            extra_flags=role.agent.flags,
            env=resolved_env,
            timeout_seconds=project_timeout_seconds(
                project,
                role_timeout_minutes=role.completion.timeout_minutes,
            ),
            max_cost_usd=run_cost_ceiling(project, role.completion.max_cost_usd),
        )
        max_retries = resolve_project_settings(project).max_infra_retries

        events: list[AgentEventRecord] = []
        message_fragments: list[str] = []
        final_message = ""
        saw_final_phase = False
        seen_signals: set[str] = set()
        final_status = "failed"
        outcome = "error"
        detail = ""
        final_session_id = session_id
        cost_usd = 0.0
        aborted_cost_usd = 0.0
        token_count = 0
        token_usage: TokenUsage | None = None
        duration_ms: int | None = None
        failure_type: str | None = None
        retry_after: str | None = None

        retry_kwargs: dict[str, Any] = {"max_retries": max_retries}
        if self.runner_sleep is not None:
            retry_kwargs["sleep"] = self.runner_sleep

        # Heartbeat the task lease while the native runner streams so a long
        # run keeps the lease alive between steps. We track the last heartbeat
        # wall-clock time and only renew once the configured interval has
        # elapsed to avoid hammering SQLite on every event.
        heartbeat_interval = self.heartbeat_seconds
        last_heartbeat: datetime | None = None

        for event in run_with_retry(
            runner,
            config,
            **retry_kwargs,
        ):
            now = self.utc_now()
            if (
                heartbeat_interval > 0
                and (
                    last_heartbeat is None
                    or (now - last_heartbeat).total_seconds() >= heartbeat_interval
                )
            ):
                self.leases.renew(task, project)
                last_heartbeat = now
            if event.event_type == "agent.tick":
                # Silent-child ticks exist only to drive the heartbeat above
                # and the command poll below; they are never persisted. This is
                # the only place a `pause` can reach an agent that has been
                # working quietly for twenty minutes.
                self.poll_commands(task.id)
                continue
            if event.event_type.startswith("signal."):
                # A backend may surface the same signal from more than one
                # stream event, and a replayed attempt re-emits earlier ones.
                signal_key = event.event_type + json.dumps(
                    event.payload, sort_keys=True, default=str
                )
                if signal_key in seen_signals:
                    continue
                seen_signals.add(signal_key)
            event_record = AgentEventRecord(
                event_type=event.event_type,
                payload=dict(event.payload),
                timestamp=event.timestamp,
            )
            events.append(event_record)
            if event_recorder is not None:
                event_recorder(event_record)
            if event.event_type == "agent.message":
                text = optional_string(event.payload.get("text"))
                if text and (not message_fragments or message_fragments[-1] != text):
                    message_fragments.append(text)
                if text:
                    phase = optional_string(event.payload.get("phase"))
                    if phase in FINAL_MESSAGE_PHASES:
                        final_message = text
                        saw_final_phase = True
                    elif not saw_final_phase:
                        final_message = text
                continue

            if event.event_type == "agent.infra_error":
                # The attempt that just failed was charged for; keep its cost
                # on the books and start the next attempt's count from zero.
                aborted_cost_usd += coerce_float_value(
                    event.payload.get("cost_usd"), default=cost_usd
                )
                cost_usd = 0.0
                token_count = 0
                dropped = optional_string(event.payload.get("dropped_session_id"))
                if dropped and final_session_id == dropped:
                    final_session_id = None
                continue

            if event.event_type == "agent.cost_update":
                cost_usd = coerce_float_value(
                    event.payload.get("cumulative_usd"),
                    default=cost_usd,
                )
                token_count = coerce_int_value(
                    event.payload.get("cumulative_tokens"),
                    default=token_count,
                )
                continue

            if event.event_type == "agent.completed":
                final_session_id = (
                    optional_string(event.payload.get("session_id")) or final_session_id
                )
                cost_usd = coerce_float_value(
                    event.payload.get("cost_usd"),
                    default=cost_usd,
                )
                token_count = coerce_int_value(
                    event.payload.get("token_count"),
                    default=token_count,
                )
                token_usage = TokenUsage.from_mapping(event.payload.get("token_usage")) or token_usage
                duration_ms = coerce_int_value(
                    event.payload.get("duration_ms"),
                    default=duration_ms,
                )
                outcome, detail = extract_completion_output(
                    role,
                    final_message,
                    transcript="\n\n".join(message_fragments),
                )
                final_status = "completed"
                continue

            if event.event_type == "agent.session":
                final_session_id = (
                    optional_string(event.payload.get("session_id")) or final_session_id
                )
                continue

            if event.event_type == "agent.killed":
                gate_type = optional_string(event.payload.get("gate_type")) or "gate"
                final_status = "timeout" if gate_type == "time" else "killed"
                outcome = "error"
                detail = (
                    optional_string(event.payload.get("reason"))
                    or "Agent run was killed by a gate."
                )
                # A backend that stops a run at its budget reports what the
                # run cost; a kill must not erase that from the books.
                final_session_id = (
                    optional_string(event.payload.get("session_id")) or final_session_id
                )
                cost_usd = coerce_float_value(event.payload.get("cost_usd"), default=cost_usd)
                token_count = coerce_int_value(
                    event.payload.get("token_count"), default=token_count
                )
                token_usage = TokenUsage.from_mapping(event.payload.get("token_usage")) or token_usage
                duration_ms = coerce_int_value(
                    event.payload.get("duration_ms"), default=duration_ms
                )
                continue

            if event.event_type == "agent.error":
                final_session_id = (
                    optional_string(event.payload.get("session_id")) or final_session_id
                )
                cost_usd = coerce_float_value(
                    event.payload.get("cost_usd"),
                    default=cost_usd,
                )
                token_count = coerce_int_value(
                    event.payload.get("token_count"),
                    default=token_count,
                )
                token_usage = TokenUsage.from_mapping(event.payload.get("token_usage")) or token_usage
                duration_ms = coerce_int_value(
                    event.payload.get("duration_ms"),
                    default=duration_ms,
                )
                final_status = "failed"
                failure_type = _failure_type_for_error(event.payload)
                retry_after = optional_string(event.payload.get("retry_after"))
                detail = (
                    optional_string(event.payload.get("error"))
                    or "\n\n".join(message_fragments)
                    or "Agent execution failed."
                )

        if not detail:
            detail = "\n\n".join(message_fragments).strip()
        if not detail:
            detail = "Agent execution finished without output."

        # Each agent.infra_error means run_with_retry aborted an attempt and
        # replayed the step; surface that as the run's retry count so partial
        # duplicate transcripts are diagnosable.
        infra_retry_count = sum(
            1 for record in events if record.event_type == "agent.infra_error"
        )

        return AgentExecutionResult(
            outcome=outcome,
            detail=detail,
            status=final_status,
            session_id=final_session_id,
            cost_usd=cost_usd + aborted_cost_usd,
            token_count=token_count,
            token_usage=token_usage,
            duration_ms=duration_ms,
            model=model or None,
            events=tuple(events),
            events_streamed=event_recorder is not None,
            retry_count=infra_retry_count,
            failure_type=failure_type,
            retry_after=retry_after,
        )


def _failure_type_for_error(payload: Mapping[str, Any]) -> str:
    """Classify an ``agent.error`` payload for ``Run.failure_type``."""

    if payload.get("quota_exhausted"):
        return "quota"
    if payload.get("preflight_failed"):
        return "preflight"
    if payload.get("retries_exhausted"):
        return "infrastructure"
    return "agent"
