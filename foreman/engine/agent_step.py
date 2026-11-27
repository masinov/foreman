"""Running one agent step and turning its event stream into a result.

``AgentStepRunner`` launches the role's backend through ``run_with_retry``,
persists each event as it arrives, keeps the task lease alive while the
agent is silent, lets an operator's command interrupt the step, and settles
the run when the step is abandoned.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
import json
import sqlite3
from contextlib import closing
import time
from pathlib import Path
from typing import Any

from .verdict import criteria_items, session_commands
from ..domain.errors import EngineCommandInterrupt
from ..domain.models import Project, Run, Task, TokenUsage
from ..domain.outcomes import ERROR
from ..definitions.roles import COMMAND_TOOLS, RoleDefinition
from ..runner import AgentRunConfig, PreflightError, run_with_retry
from ..domain.sandbox import SandboxPolicy
from ..domain.settings import without_database_env
from ..runner.base import AgentRunner as NativeAgentRunner
from ..runner.env import passthrough_env, resolve_env
from ..runner.process import EngineShutdown
from ..repo.worktrees import WorktreeError, WorktreeManager
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

#: How often an agent that keeps printing is checked for a user's Stop and
#: for engine commands. A silent agent is checked on every tick.
COMMAND_POLL_SECONDS = 5.0


#: Where a sandbox is given a snapshot of the database (``scripts/review_screenshots.py`` reads it).
REVIEW_DATABASE_COPY = ".review/live.db"


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
            # task stays resumable: paused by a user's Stop (ADR-0043), or
            # started again for a `steer_task`.
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
            if role.run_scope == "sandbox":
                return self._execute_sandboxed(
                    role=role,
                    project=project,
                    task=task,
                    workflow_step=workflow_step,
                    prompt=prompt,
                    session_id=session_id,
                    carried_output=carried_output,
                    model=model,
                    event_recorder=event_recorder,
                )
            return self._execute_in(
                role=role,
                project=project,
                task=task,
                workflow_step=workflow_step,
                prompt=prompt,
                session_id=session_id,
                carried_output=carried_output,
                model=model,
                event_recorder=event_recorder,
            )
        except LeaseLostError:
            raise
        except Exception as exc:  # pragma: no cover - defensive fallback
            # Foreman could not run the agent at all (the runner is missing, the
            # process failed to start): not the step's own work (ADR-0041).
            return AgentExecutionResult(
                outcome="error",
                detail=str(exc),
                status="failed",
                failure_type="infrastructure",
                events=(
                    AgentEventRecord(
                        event_type="agent.error",
                        payload={"error": str(exc)},
                    ),
                ),
            )

    def _execute_sandboxed(
        self,
        *,
        role: RoleDefinition,
        project: Project,
        task: Task,
        workflow_step: str,
        prompt: str,
        session_id: str | None,
        carried_output: str | None,
        model: str | None,
        event_recorder: Callable[[AgentEventRecord], None] | None,
    ) -> AgentExecutionResult:
        """Run a ``run_scope = "sandbox"`` role in a throwaway worktree (ADR-0041).

        The worktree is gone when this returns or raises, whatever ended the
        step. A step that moved the task's branch fails with the reason,
        however it ended otherwise.
        """

        try:
            with WorktreeManager(project).sandbox(task) as box:
                if resolve_project_settings(project).sandbox_database_copy:
                    self._give_database_copy(box.path, project.id)
                result = self._execute_in(
                    role=role,
                    project=project,
                    task=task,
                    workflow_step=workflow_step,
                    prompt=prompt,
                    session_id=session_id,
                    carried_output=carried_output,
                    model=model,
                    event_recorder=event_recorder,
                    working_dir=box.path,
                    sandbox=box.policy,
                )
                violation = box.check()
        except WorktreeError as exc:
            return AgentExecutionResult(
                outcome=ERROR,
                detail=f"The sandbox for this step could not be made: {exc}",
                status="failed",
                events=(
                    AgentEventRecord(
                        event_type="agent.error",
                        payload={"error": str(exc), "preflight_failed": True},
                    ),
                ),
                failure_type="preflight",
            )
        if violation is None:
            return result
        return replace(
            result,
            outcome=ERROR,
            detail=violation,
            status="failed",
            failure_type="sandbox",
            record=None,
            events=(
                *result.events,
                AgentEventRecord(event_type="agent.error", payload={"error": violation}),
            ),
        )

    def _give_database_copy(self, sandbox_path: Path, project_id: str) -> None:
        """Put a copy of this project's records in the sandbox, where the review scripts look.

        Only for a project that asks (``sandbox_database_copy``): the sandbox
        cannot read the main checkout, where the live database is, and the
        reviewer's screenshot script serves the dashboard from a database. The
        copy is a snapshot (SQLite's backup, never the live file) at
        ``.review/live.db`` with only this project's rows: another project's
        records, every API token, notification destination and delivery, and
        the manager's conversations are taken out, and the file is vacuumed
        so nothing deleted is left in its free pages. A step without a store
        has none to give.
        """

        store = getattr(self.records, "store", None)
        db_path = getattr(store, "db_path", None)
        if not db_path or db_path == ":memory:" or not Path(db_path).is_file():
            return
        target = sandbox_path / REVIEW_DATABASE_COPY
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            # ``closing``: a connection's own ``with`` commits but stays open,
            # and an open one locks the copy for what follows.
            with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as source, closing(
                sqlite3.connect(target)
            ) as copy:
                source.backup(copy)
            _keep_only_project(target, project_id)
        except sqlite3.Error:
            # The review can still run; the script says it has no database.
            target.unlink(missing_ok=True)

    def _execute_in(
        self,
        *,
        role: RoleDefinition,
        project: Project,
        task: Task,
        workflow_step: str,
        prompt: str,
        session_id: str | None,
        carried_output: str | None,
        model: str | None,
        event_recorder: Callable[[AgentEventRecord], None] | None,
        working_dir: Path | None = None,
        sandbox: SandboxPolicy | None = None,
    ) -> AgentExecutionResult:
        """One run of the role, in ``working_dir`` when given, else the task's worktree."""

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
            working_dir=working_dir,
            sandbox=sandbox,
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
        working_dir: Path | None = None,
        sandbox: SandboxPolicy | None = None,
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
            )
        model = model or ""
        config = self._native_config(
            role=role,
            project=project,
            task=task,
            prompt=prompt,
            session_id=session_id,
            model=model,
            working_dir=working_dir,
            sandbox=sandbox,
        )
        if isinstance(config, AgentExecutionResult):
            return config

        retry_kwargs: dict[str, Any] = {
            "max_retries": resolve_project_settings(project).max_infra_retries
        }
        if self.runner_sleep is not None:
            retry_kwargs["sleep"] = self.runner_sleep

        tally = _NativeRunTally(
            role=role,
            session_id=session_id,
            task_criteria=criteria_items(task.acceptance_criteria),
            earlier_commands=self._session_commands(task, workflow_step, session_id),
        )
        seen_signals: set[str] = set()
        # Heartbeat the task lease while the native runner streams so a long
        # run keeps the lease alive between steps. We track the last heartbeat
        # wall-clock time and only renew once the configured interval has
        # elapsed to avoid hammering SQLite on every event.
        heartbeat_interval = self.heartbeat_seconds
        last_heartbeat: datetime | None = None
        last_poll = time.monotonic()

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
                # the only place a Stop can reach an agent that has been
                # working quietly for twenty minutes.
                last_poll = time.monotonic()
                self.poll_commands(task.id)
                continue
            if time.monotonic() - last_poll >= COMMAND_POLL_SECONDS:
                # An agent that keeps printing never ticks; a Stop must
                # still reach it within seconds.
                last_poll = time.monotonic()
                self.poll_commands(task.id)
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

    def _session_commands(self, task: Task, step: str, session_id: str | None) -> list[str]:
        if not session_id or self.records is None:
            return []
        return session_commands(self.records.store, task.id, step, session_id)

    def _native_config(
        self,
        *,
        role: RoleDefinition,
        project: Project,
        task: Task,
        prompt: str,
        session_id: str | None,
        model: str,
        working_dir: Path | None = None,
        sandbox: SandboxPolicy | None = None,
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
            # checkout; a sandboxed step is given its throwaway copy instead.
            working_dir=working_dir or task_working_dir(project, task),
            session_id=session_id,
            permission_mode=role.agent.permission_mode,
            disallowed_tools=_disallowed_tools(role),
            allowed_tools=role.agent.tools.allowed,
            no_tools=role.agent.tools.none,
            extra_flags=role.agent.flags,
            # What the project passes through from the host, then what the
            # role sets; the runner adds both to the short list of host
            # variables every agent gets (ADR-0023).
            # Never FOREMAN_DB, whatever a role's [agent.env] says: the agent
            # runs in a worktree, out of the live database's reach (FOR-101).
            env=without_database_env({
                **passthrough_env(resolve_project_settings(project).agent_env_passthrough),
                **resolved_env,
            }),
            timeout_seconds=project_timeout_seconds(
                project,
                role_timeout_minutes=role.completion.timeout_minutes,
            ),
            max_cost_usd=run_cost_ceiling(project, role.completion.max_cost_usd),
            session_cost_baseline_usd=session_baseline_usd,
            sandbox=sandbox,
        )


#: Tables a review's copy of the database never carries, whatever the project:
#: credentials, where notifications go and what they said, the manager's
#: conversations (which can hold anything the operator typed), engine leases.
_TABLES_EMPTIED_IN_A_COPY: tuple[str, ...] = (
    "api_tokens",
    "notification_destinations",
    "notification_deliveries",
    "meta_sessions",
    "meta_turns",
    "leases",
)


def _keep_only_project(path: Path, project_id: str) -> None:
    """Take every other project's rows, and the tables above, out of the copy at ``path``."""

    with closing(sqlite3.connect(path)) as copy:
        copy.execute("PRAGMA foreign_keys = OFF")
        tables = [
            row[0]
            for row in copy.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            columns = {row[1] for row in copy.execute(f'PRAGMA table_info("{table}")')}
            if table in _TABLES_EMPTIED_IN_A_COPY:
                copy.execute(f'DELETE FROM "{table}"')
            elif table == "projects":
                copy.execute('DELETE FROM "projects" WHERE id != ?', (project_id,))
            elif "project_id" in columns:
                copy.execute(
                    f'DELETE FROM "{table}" WHERE project_id IS NOT ? ', (project_id,)
                )
        copy.commit()
    # Outside a transaction: deleted rows stay in free pages until a vacuum.
    # The copy is a WAL database like its source; out of WAL first, or the
    # vacuumed pages sit in the -wal file and the old ones in the main file.
    copy = sqlite3.connect(path, isolation_level=None)
    try:
        copy.execute("PRAGMA journal_mode = DELETE")
        copy.execute("VACUUM")
    finally:
        copy.close()


def _disallowed_tools(role: RoleDefinition) -> tuple[str, ...]:
    """The tools the agent is refused: the role's own, and every command tool for ``run_scope = "none"``.

    A role that runs nothing may list no ``allowed`` tools at all, which leaves
    the backend's whole set, Bash, Monitor and PowerShell included; refusing
    them here keeps the scope true whatever the tool list says. (Codex runs
    commands in its own sandbox without asking: the scope is not enforced
    there; see the MANUAL.)
    """

    disallowed = tuple(role.agent.tools.disallowed)
    if role.run_scope == "none":
        disallowed = (*disallowed, *(tool for tool in COMMAND_TOOLS if tool not in disallowed))
    return disallowed


class _NativeRunTally:
    """What one native run's stream adds up to: its messages, totals and ending."""

    def __init__(
        self,
        *,
        role: RoleDefinition,
        session_id: str | None,
        task_criteria: int | Sequence[str] = 0,
        earlier_commands: Sequence[str] = (),
    ) -> None:
        self.role = role
        self.task_criteria = task_criteria
        #: The commands a verdict's ``ran`` is checked against: this run's, and
        #: those of the earlier runs of the session it resumes (a corrective
        #: retry continues the same review). Never unchecked.
        self.commands: list[str] = list(earlier_commands)
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

        if event_type == "agent.command":
            self.commands.append(str(payload.get("command") or ""))
        elif event_type == "agent.message":
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
                task_criteria=self.task_criteria,
                commands=self.commands,
            )
            self.outcome, self.detail, self.record = reading.outcome, reading.detail, reading.record
            self.final_status = "completed"
        elif event_type == "agent.session":
            self.session_id = optional_string(payload.get("session_id")) or self.session_id
        elif event_type == "agent.killed":
            gate_type = optional_string(payload.get("gate_type")) or "gate"
            self.final_status = "timeout" if gate_type == "time" else "killed"
            self.outcome = "error"
            # A limit the project set, not the step's own work (ADR-0041): the
            # task blocks for a person rather than moving up a model.
            self.failure_type = "gate"
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
