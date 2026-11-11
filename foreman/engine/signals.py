"""Acting on what an agent reports while it works.

Agents emit ``FOREMAN_SIGNAL`` lines: the task they chose, a task they want
created, progress, a blocker. ``SignalHandler`` persists every agent event
and applies the signals a role is allowed to send.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..git import GitError, branch_exists, run_git
from ..models import TASK_COMPLEXITIES, TASK_TYPES, Project, Run, Task
from ..roles import RoleDefinition
from ..store import ForemanStore
from .coerce import optional_string
from .leasing import TaskLeases
from .records import RunRecords, new_id
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

    def autonomous_gap_recorded(self, task: Task) -> bool:
        """True when this task's missing task_started was already recorded."""

        return any(
            event.event_type == "workflow.autonomous_contract_missing"
            for event in self.store.list_events(task_id=task.id)
        )

    def signalled_branch_problem(self, project: Project, branch: str) -> str | None:
        """Say why a branch an agent reported cannot become the task's branch."""

        if branch == project.default_branch:
            return (
                f"{branch!r} is the default branch; a task's work reaches it only "
                "through the merge step."
            )
        try:
            valid = run_git(
                project.repo_path, "check-ref-format", "--branch", branch, check=False
            )
        except (GitError, OSError) as exc:
            return f"The branch name {branch!r} could not be checked: {exc}"
        if valid.returncode != 0:
            return f"{branch!r} is not a valid branch name."
        if not branch_exists(project.repo_path, branch):
            return f"Branch {branch!r} does not exist in the repository."
        return None

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
        if event_record.event_type == "signal.task_started":
            task.title = optional_string(payload.get("title")) or task.title
            task.acceptance_criteria = (
                optional_string(payload.get("criteria")) or task.acceptance_criteria
            )
            # The type and the branch are checked before they are stored: a
            # type Foreman does not know breaks branch naming and the merge
            # guard, and the branch decides which worktree later steps use
            # and what gets merged.
            refused: dict[str, str] = {}
            task_type = optional_string(payload.get("task_type"))
            if task_type and task_type != task.task_type:
                if task_type in TASK_TYPES:
                    task.task_type = task_type
                else:
                    refused["task_type"] = (
                        f"{task_type!r} is not a task type "
                        f"(expected one of: {', '.join(TASK_TYPES)})."
                    )
            branch = optional_string(payload.get("branch"))
            if branch and branch != task.branch_name:
                problem = self.signalled_branch_problem(project, branch)
                if problem is None:
                    task.branch_name = branch
                else:
                    refused["branch"] = problem
            self.tasks.save(task, include_definition=True)
            for field_name, reason in refused.items():
                self.records.emit_event(
                    run,
                    "signal.rejected",
                    {
                        "signal": "task_started",
                        "role_id": role_id,
                        "field": field_name,
                        "reason": reason,
                    },
                    role_id=role_id,
                )
            return

        if event_record.event_type == "signal.task_created":
            sprint = self.store.get_active_sprint(project.id)
            if sprint is None:
                return
            order_index = self.store.next_task_order_index(sprint.id)
            raw_complexity = optional_string(payload.get("complexity"))
            complexity = raw_complexity if raw_complexity in TASK_COMPLEXITIES else None
            created_task = Task(
                id=new_id("task"),
                sprint_id=sprint.id,
                project_id=project.id,
                title=str(payload.get("title", "(agent-created task)")),
                task_type=str(payload.get("task_type", "feature")),
                description=optional_string(payload.get("description")),
                acceptance_criteria=optional_string(payload.get("criteria")),
                complexity=complexity,
                order_index=order_index,
                created_by=f"agent:{role_id}",
                created_at=event_record.timestamp,
            )
            self.tasks.save(created_task)
            self.records.emit_event(
                run,
                "engine.task_created",
                {
                    "task_id": created_task.id,
                    "title": created_task.title,
                    "task_type": created_task.task_type,
                    "created_by": created_task.created_by,
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
