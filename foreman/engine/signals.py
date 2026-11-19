"""Acting on what an agent reports while it works.

Agents emit ``FOREMAN_SIGNAL`` lines: the task they chose, a task they want
created, progress, a blocker. ``SignalHandler`` persists every agent event
and applies the signals a role is allowed to send.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..domain.models import TASK_COMPLEXITIES, TASK_TYPES, Project, Run, Task
from ..mutations import Mutations
from ..definitions.roles import RoleDefinition
from ..store import ForemanStore
from .coerce import optional_string
from .leasing import TaskLeases
from .records import RunRecords
from .results import AgentEventRecord
from .task_writes import TaskWrites


class SignalHandler:
    """Persists agent events and applies their signals for one store."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        roles: Mapping[str, RoleDefinition],
        records: RunRecords,
        leases: TaskLeases,
        tasks: TaskWrites,
    ) -> None:
        self.store = store
        self.roles = roles
        self.records = records
        self.leases = leases
        self.tasks = tasks

    def emit_agent_events(
        self,
        run: Run,
        task: Task,
        project: Project,
        role_id: str,
        events: tuple[AgentEventRecord, ...],
    ) -> None:
        for event_record in events:
            self.records.emit_event(
                run,
                event_record.event_type,
                event_record.payload,
                role_id=role_id,
                timestamp=event_record.timestamp,
            )
            self.apply(run, task, project, role_id, event_record)

    def persist_agent_event(
        self,
        run: Run,
        task: Task,
        project: Project,
        role_id: str,
        event_record: AgentEventRecord,
    ) -> None:
        """Persist one agent event immediately while a native step is active."""

        self.records.emit_event(
            run,
            event_record.event_type,
            event_record.payload,
            role_id=role_id,
            timestamp=event_record.timestamp,
        )
        self.apply(run, task, project, role_id, event_record)

    def apply(
        self,
        run: Run,
        task: Task,
        project: Project,
        role_id: str,
        event_record: AgentEventRecord,
    ) -> None:
        payload = event_record.payload
        if event_record.event_type.startswith("signal.") and event_record.event_type not in {
            "signal.invalid",
            "signal.unknown",
            "signal.rejected",
        }:
            signal_name = event_record.event_type.removeprefix("signal.")
            role = self.roles.get(role_id)
            if role is not None and signal_name not in role.signals:
                self.records.emit_event(
                    run,
                    "signal.rejected",
                    {
                        "signal": signal_name,
                        "role_id": role_id,
                        "reason": f"Role {role_id!r} may not emit {signal_name}.",
                    },
                    role_id=role_id,
                )
                return
        if event_record.event_type == "signal.task_created":
            # Follow-up work an agent finds goes to the backlog, filed under
            # the project's triage policy like any other filed work. It never
            # joins the sprint the agent is running in (ADR-0021).
            raw_complexity = optional_string(payload.get("complexity"))
            complexity = raw_complexity if raw_complexity in TASK_COMPLEXITIES else None
            task_type = optional_string(payload.get("task_type")) or "feature"
            if task_type not in TASK_TYPES:
                self.records.emit_event(
                    run,
                    "signal.rejected",
                    {
                        "signal": "task_created",
                        "role_id": role_id,
                        "field": "task_type",
                        "reason": (
                            f"{task_type!r} is not a task type "
                            f"(expected one of: {', '.join(TASK_TYPES)}); filed as a feature."
                        ),
                    },
                    role_id=role_id,
                )
                task_type = "feature"
            filed = Mutations(
                self.store, via="engine", actor=f"agent:{role_id}", role=role_id
            ).file_task(
                project,
                title=optional_string(payload.get("title")) or "(agent-created task)",
                task_type=task_type,
                description=optional_string(payload.get("description")),
                acceptance_criteria=optional_string(payload.get("criteria")),
                complexity=complexity,
                created_by=f"agent:{role_id}",
                event_payload={"filed_from_task_id": task.id, "filed_from_run_id": run.id},
            )
            self.records.emit_event(
                run,
                "engine.task_created",
                {
                    "task_id": filed.task.id,
                    "title": filed.task.title,
                    "task_type": filed.task.task_type,
                    "created_by": filed.task.created_by,
                    "sprint_id": filed.task.sprint_id,
                    "status": filed.task.status,
                },
            )
            return

        if event_record.event_type == "signal.blocker":
            message = optional_string(payload.get("message"))
            if message:
                task.status = "blocked"
                task.blocked_reason = message
                self.tasks.save(task)
                self.leases.release(task, project)
                self.records.emit_attention_needed(run, task.id, "task_blocked")
