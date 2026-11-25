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

from ..domain.errors import EngineCommandInterrupt
from ..domain.models import Project, Run, Task, TokenUsage
from ..domain.outcomes import ERROR
from ..definitions.roles import RoleDefinition
from ..runner import AgentRunConfig, PreflightError, run_with_retry
from ..runner.base import AgentRunner as NativeAgentRunner
from ..runner.env import passthrough_env, resolve_env
from ..runner.process import EngineShutdown
from .branch_sync import task_working_dir
from .coerce import coerce_float_value, coerce_int_value, optional_string
from .errors import LeaseLostError, OrchestratorError
from .leasing import TaskLeases
from .limits import project_timeout_seconds, resolve_project_settings, run_cost_ceiling
from .model_selection import resolve_step_model
from .output_contract import FINAL_MESSAGE_PHASES, read_completion
from ..history.records import RunRecords
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
        config = self._native_config(
            role=role, project=project, task=task, prompt=prompt, session_id=session_id, model=model
        )
        if isinstance(config, AgentExecutionResult):
            return config

        retry_kwargs: dict[str, Any] = {
            "max_retries": resolve_project_settings(project).max_infra_retries
        }
        if self.runner_sleep is not None:
            retry_kwargs["sleep"] = self.runner_sleep

        tally = _NativeRunTally(role=role, session_id=session_id)
        seen_signals: set[str] = set()
        # Heartbeat the task lease while the native runner streams so a long
        # run keeps the lease alive between steps. We track the last heartbeat
        # wall-clock time and only renew once the configured interval has
        # elapsed to avoid hammering SQLite on every event.
        heartbeat_interval = self.heartbeat_seconds
        last_heartbeat: datetime | None = None

        for event in run_with_retry(runner, config, **retry_kwargs):
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
            tally.events.append(event_record)
            if event_recorder is not None:
                event_recorder(event_record)
            tally.absorb(event.event_type, event.payload)

        return tally.result(model=model or None, events_streamed=event_recorder is not None)

    def _native_config(
        self,
        *,
        role: RoleDefinition,
        project: Project,
        task: Task,
        prompt: str,
        session_id: str | None,
        model: str,
    ) -> AgentRunConfig | AgentExecutionResult:
        """What the runner is started with, or the failed result of a role that cannot start."""

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
        # What the backend already counted for the session being resumed; the
        # runner takes it off, so this run is charged only for itself.
        session_baseline_usd = (
            self.records.store.latest_session_cost(
                session_id=session_id, agent_backend=role.agent.backend
            )
            if session_id
            else 0.0
        )
        return AgentRunConfig(
            backend=role.agent.backend,
            model=model or None,
            prompt=prompt,
            # The agent edits its task's own worktree, never the operator's
            # checkout.
            working_dir=task_working_dir(project, task),
            session_id=session_id,
            permission_mode=role.agent.permission_mode,
            disallowed_tools=role.agent.tools.disallowed,
            allowed_tools=role.agent.tools.allowed,
            no_tools=role.agent.tools.none,
            extra_flags=role.agent.flags,
            # What the project passes through from the host, then what the
            # role sets; the runner adds both to the short list of host
            # variables every agent gets (ADR-0023).
            env={
                **passthrough_env(resolve_project_settings(project).agent_env_passthrough),
                **resolved_env,
            },
            timeout_seconds=project_timeout_seconds(
                project,
                role_timeout_minutes=role.completion.timeout_minutes,
            ),
            max_cost_usd=run_cost_ceiling(project, role.completion.max_cost_usd),
            session_cost_baseline_usd=session_baseline_usd,
        )


class _NativeRunTally:
    """What one native run's stream adds up to: its messages, totals and ending."""

    def __init__(self, *, role: RoleDefinition, session_id: str | None) -> None:
        self.role = role
        self.events: list[AgentEventRecord] = []
        self.message_fragments: list[str] = []
        self.final_message = ""
        self.saw_final_phase = False
        self.final_status = "failed"
        self.outcome = "error"
        self.detail = ""
        self.record: dict[str, Any] | None = None
        self.session_id = session_id
        self.cost_usd = 0.0
        self.session_cost_usd: float | None = None
        self.aborted_cost_usd = 0.0
        self.token_count = 0
        self.token_usage: TokenUsage | None = None
        self.duration_ms: int | None = None
        self.failure_type: str | None = None
        self.retry_after: str | None = None

    def absorb(self, event_type: str, payload: Mapping[str, Any]) -> None:
        """Fold one persisted stream event into the run's totals and ending."""

        if event_type == "agent.message":
            text = optional_string(payload.get("text"))
            if text and (not self.message_fragments or self.message_fragments[-1] != text):
                self.message_fragments.append(text)
            if text:
                phase = optional_string(payload.get("phase"))
                if phase in FINAL_MESSAGE_PHASES:
                    self.final_message = text
                    self.saw_final_phase = True
                elif not self.saw_final_phase:
                    self.final_message = text
        elif event_type == "agent.infra_error":
            # The attempt that just failed was charged for; keep its cost on
            # the books and start the next attempt's count from zero.
            self.aborted_cost_usd += coerce_float_value(
                payload.get("cost_usd"), default=self.cost_usd
            )
            self.cost_usd = 0.0
            self.token_count = 0
            dropped = optional_string(payload.get("dropped_session_id"))
            if dropped and self.session_id == dropped:
                self.session_id = None
        elif event_type == "agent.cost_update":
            self.cost_usd = coerce_float_value(payload.get("cumulative_usd"), default=self.cost_usd)
            self.token_count = coerce_int_value(
                payload.get("cumulative_tokens"), default=self.token_count
            )
        elif event_type == "agent.completed":
            self._take_totals(payload)
            reading = read_completion(
                self.role,
                self.final_message,
                transcript="\n\n".join(self.message_fragments),
            )
            self.outcome, self.detail, self.record = reading.outcome, reading.detail, reading.record
            self.final_status = "completed"
        elif event_type == "agent.session":
            self.session_id = optional_string(payload.get("session_id")) or self.session_id
        elif event_type == "agent.killed":
            gate_type = optional_string(payload.get("gate_type")) or "gate"
            self.final_status = "timeout" if gate_type == "time" else "killed"
            self.outcome = "error"
            self.detail = optional_string(payload.get("reason")) or "Agent run was killed by a gate."
            # A backend that stops a run at its budget reports what the run
            # cost; a kill must not erase that from the books.
            self._take_totals(payload)
        elif event_type == "agent.error":
            self._take_totals(payload)
            self.final_status = "failed"
            self.failure_type = _failure_type_for_error(payload)
            self.retry_after = optional_string(payload.get("retry_after"))
            self.detail = (
                optional_string(payload.get("error"))
                or "\n\n".join(self.message_fragments)
                or "Agent execution failed."
            )

    def _take_totals(self, payload: Mapping[str, Any]) -> None:
        """The session, cost, tokens and duration a terminal event reports."""

        self.session_id = optional_string(payload.get("session_id")) or self.session_id
        self.cost_usd = coerce_float_value(payload.get("cost_usd"), default=self.cost_usd)
        self.session_cost_usd = _reported_session_cost(payload, self.session_cost_usd)
        self.token_count = coerce_int_value(payload.get("token_count"), default=self.token_count)
        self.token_usage = TokenUsage.from_mapping(payload.get("token_usage")) or self.token_usage
        self.duration_ms = coerce_int_value(payload.get("duration_ms"), default=self.duration_ms)

    def result(self, *, model: str | None, events_streamed: bool) -> AgentExecutionResult:
        detail = self.detail or "\n\n".join(self.message_fragments).strip()
        if not detail:
            detail = "Agent execution finished without output."
        # Each agent.infra_error means run_with_retry aborted an attempt and
        # replayed the step; surface that as the run's retry count so partial
        # duplicate transcripts are diagnosable.
        infra_retry_count = sum(
            1 for record in self.events if record.event_type == "agent.infra_error"
        )
        return AgentExecutionResult(
            outcome=self.outcome,
            detail=detail,
            status=self.final_status,
            session_id=self.session_id,
            cost_usd=self.cost_usd + self.aborted_cost_usd,
            session_cost_usd=self.session_cost_usd,
            token_count=self.token_count,
            token_usage=self.token_usage,
            duration_ms=self.duration_ms,
            model=model,
            events=tuple(self.events),
            events_streamed=events_streamed,
            retry_count=infra_retry_count,
            failure_type=self.failure_type,
            retry_after=self.retry_after,
            record=self.record,
        )

def _reported_session_cost(payload: Mapping[str, Any], current: float | None) -> float | None:
    """The session's running total a terminal event carries, if it carries one."""

    reported = payload.get("session_cost_usd")
    if isinstance(reported, (int, float)) and not isinstance(reported, bool):
        return float(reported)
    return current


def _failure_type_for_error(payload: Mapping[str, Any]) -> str:
    """Classify an ``agent.error`` payload for ``Run.failure_type``."""

    if payload.get("quota_exhausted"):
        return "quota"
    if payload.get("preflight_failed"):
        return "preflight"
    if payload.get("retries_exhausted"):
        return "infrastructure"
    return "agent"
