"""What the orchestrator is built from and what its parts share.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ...definitions.layers import project_definitions
from ...definitions.roles import RoleDefinition, default_roles_dir, load_roles
from ...definitions.workflows import (
    WorkflowDefinition,
    default_workflows_dir,
    load_workflows,
)
from ...domain.models import (
    CompletionEvidence,
    Event,
    Project,
    Task,
)
from ...history.logs import get_logger
from ...history.records import RunRecords
from ...notifications.delivery import NotificationDispatcher
from ...runner import ClaudeCodeRunner, CodexRunner
from ...runner.base import AgentRunner as NativeAgentRunner
from ...store import ForemanStore
from ..agent_step import DEFAULT_NATIVE_STEP_HEARTBEAT_SECONDS, AgentStepRunner
from ..builtins import BuiltinExecutor
from ..errors import (
    OrchestratorError,
)
from ..evidence import EvidenceBuilder
from ..leasing import TASK_LEASE_HEARTBEAT_SECONDS, TaskLeases
from ..prompts import PromptBuilder
from ..recovery import Recovery
from ..results import (
    AgentExecutor,
)
from ..retention import Retention
from ..selection import TaskSelector
from ..signals import SignalHandler
from ..sprints import SprintFlow
from ..task_worktrees import TaskWorktrees
from ..task_writes import TaskWrites
from ..workflow_runner import WorkflowRunner

_LOGGER = get_logger("orchestrator")

#: How often, at most, a running step looks for approved merges to carry out.


_BRANCH_PREFIXES = {
    "feature": "feat",
    "fix": "fix",
    "refactor": "refactor",
    "docs": "docs",
    "spike": "spike",
    "chore": "chore",
}


def generate_branch_name(task: Task) -> str:
    """Generate a stable branch name for one task."""

    prefix = _BRANCH_PREFIXES.get(task.task_type, "feat")
    return f"{prefix}/{task.id}"


class OrchestratorBase:
    """The store, the definitions, the runners and the engine's parts."""

    # Minimum interval (seconds) between task-lease renewals while a native
    # runner step is streaming. The default 30s is well under the 5-minute lease
    # duration so a long Claude/Codex stream keeps the lease alive.
    _DEFAULT_NATIVE_STEP_HEARTBEAT_SECONDS = DEFAULT_NATIVE_STEP_HEARTBEAT_SECONDS

    # Maximum heartbeat age (seconds) below which a lease is still considered
    # alive for active-run recovery. If the lease's heartbeat is older than
    # this window, recovery treats the holder as gone even if the lease is
    # technically still within its ``expires_at`` window.
    _LEASE_LIVENESS_THRESHOLD_SECONDS = 60.0

    # Well inside both the 300-second lease and the 60-second liveness window
    # above; see foreman/task_lease.py.
    _TASK_LEASE_HEARTBEAT_SECONDS = TASK_LEASE_HEARTBEAT_SECONDS

    def __init__(
        self,
        store: ForemanStore,
        *,
        roles: Mapping[str, RoleDefinition] | None = None,
        workflows: Mapping[str, WorkflowDefinition] | None = None,
        agent_executor: AgentExecutor | None = None,
        agent_runners: Mapping[str, NativeAgentRunner] | None = None,
        builtin_executor: BuiltinExecutor | None = None,
        runner_sleep: Callable[[float], None] | None = None,
        utc_now: Callable[[], datetime] | None = None,
        holder_id: str | None = None,
        native_step_heartbeat_seconds: float | None = None,
        command_poll: Callable[[str], None] | None = None,
        notifier: NotificationDispatcher | None = None,
    ) -> None:
        loaded_roles = dict(roles) if roles is not None else load_roles(default_roles_dir())
        loaded_workflows = (
            dict(workflows)
            if workflows is not None
            else load_workflows(
                default_workflows_dir(),
                available_role_ids=set(loaded_roles),
                role_outcomes={
                    role_id: role.completion.outcomes
                    for role_id, role in loaded_roles.items()
                },
            )
        )
        self.store = store
        #: Definitions handed in (tests, embedding) are used as they are;
        #: otherwise each project's own are loaded when its work starts.
        self._definitions_given = roles is not None or workflows is not None
        self.roles = loaded_roles
        self.evidence = EvidenceBuilder(self.store, self.roles)
        self.workflows = loaded_workflows
        self.agent_executor = agent_executor
        self.agent_runners = (
            dict(agent_runners)
            if agent_runners is not None
            else {
                "claude_code": ClaudeCodeRunner(),
                "codex": CodexRunner(),
            }
        )
        self.builtin_executor = builtin_executor or BuiltinExecutor()
        #: Offered every persisted event; queues the announceable ones as
        #: deliveries. Injectable so a test can watch what the engine chose to
        #: announce without a transport, and so a caller that has no business
        #: notifying anyone can pass one that does nothing.
        self.notifier = notifier if notifier is not None else NotificationDispatcher(store)
        self.records = RunRecords(store, self.notifier)
        self.runner_sleep = runner_sleep
        self.utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self.retention = Retention(store, self.records, self.utc_now)
        self.sprints = SprintFlow(store, self.records, self.utc_now)
        self.holder_id = holder_id or str(uuid4())
        if native_step_heartbeat_seconds is not None and native_step_heartbeat_seconds < 0:
            native_step_heartbeat_seconds = 0.0
        self._native_step_heartbeat_seconds = (
            native_step_heartbeat_seconds
            if native_step_heartbeat_seconds is not None
            else self._DEFAULT_NATIVE_STEP_HEARTBEAT_SECONDS
        )
        self.leases = TaskLeases(
            store, self.holder_id, heartbeat_seconds=self._TASK_LEASE_HEARTBEAT_SECONDS
        )
        # Every task write carries the number of the lease it is made under.
        self.tasks = TaskWrites(store, fencing_token_for=self.leases.fencing_token_for)
        self.agent_steps = AgentStepRunner(
            agent_executor=self.agent_executor,
            agent_runners=self.agent_runners,
            leases=self.leases,
            records=self.records,
            runner_sleep=self.runner_sleep,
            utc_now=self.utc_now,
            heartbeat_seconds=self._native_step_heartbeat_seconds,
            poll_commands=self._poll_commands,
        )
        self.recovery = Recovery(
            store,
            records=self.records,
            leases=self.leases,
            tasks=self.tasks,
            utc_now=self.utc_now,
        )
        self.selector = TaskSelector(
            store,
            leases=self.leases,
            tasks=self.tasks,
            block_task_for_error=self.block_task_for_error,
        )
        self.signals = SignalHandler(
            store,
            roles=self.roles,
            records=self.records,
            leases=self.leases,
            tasks=self.tasks,
        )
        self.task_worktrees = TaskWorktrees(store, records=self.records, tasks=self.tasks)
        self.prompts = PromptBuilder(
            store,
            evidence=self.evidence,
            tasks=self.tasks,
            build_evidence=lambda task, project: self.build_completion_evidence(task, project),
        )
        self.runner = WorkflowRunner(
            store,
            roles=self.roles,
            records=self.records,
            leases=self.leases,
            tasks=self.tasks,
            task_worktrees=self.task_worktrees,
            prompts=self.prompts,
            agent_steps=self.agent_steps,
            signals=self.signals,
            evidence=self.evidence,
            builtin_executor=self.builtin_executor,
            poll_commands=self._poll_commands,
            build_evidence=lambda task, project: self.build_completion_evidence(task, project),
        )
        #: Called with the running task id before every workflow step and on
        #: every silent-agent tick. The resident engine supplies it so an
        #: `shutdown` or `steer_task` reaches an agent that may run for
        #: an hour. It returns normally to continue and raises
        #: ``EngineCommandInterrupt`` to stop the step. A one-shot ``foreman
        #: run`` leaves it None and behaves exactly as before.
        self.command_poll = command_poll
        #: Set by a resident engine. Asked between two tasks of one pass;
        #: True ends the pass there, so the engine can act on what is waiting
        #: for it (a task someone asked to run next, a command) before the
        #: pass picks another task off the queue. Without it a request to run
        #: a task waited until the whole queue had run.
        self.yield_between_tasks: Callable[[], bool] | None = None

    def close(self) -> None:
        """Stop the background work this orchestrator started."""

        self.leases.close()

    def run_workflow_from_step(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
        *,
        step: str,
        carried_output: str | None,
    ) -> Task:
        """Run a task from one workflow step (see ``engine.workflow_runner``)."""

        return self.runner.run_from_step(
            project, workflow, task, step=step, carried_output=carried_output
        )

    def select_next_task(self, project: Project) -> Task | None:
        """Pick and lease the next runnable task (see ``engine.selection``)."""

        return self.selector.select_next_task(project)

    def use_project_definitions(self, project_id: str) -> None:
        """Run with this project's roles and workflows (ADR-0024).

        The dictionaries are changed in place: the parts of the engine that
        were handed them see the project's definitions without being rebuilt.
        A definition that does not load raises, like a broken shipped file.
        """

        if self._definitions_given:
            return
        definitions = project_definitions(self.store, project_id)
        self.roles.clear()
        self.roles.update(definitions.roles)
        self.workflows.clear()
        self.workflows.update(definitions.workflows)

    def recover_orphaned_tasks(self, project_id: str) -> None:
        """Reset tasks an earlier engine left mid-work (see ``engine.recovery``)."""

        self.recovery.recover_orphaned_tasks(project_id)

    def build_completion_evidence(
        self, task: Task, project: Project
    ) -> CompletionEvidence | None:
        """Build completion evidence for one task (see ``engine.evidence``)."""

        return self.evidence.build(task, project)

    def record_engine_event(
        self,
        *,
        project_id: str,
        event_type: str,
        payload: dict[str, Any],
        task_id: str | None = None,
        detail: str = "",
        outcome: str = "success",
        workflow_step: str = "orchestrator",
    ) -> Event:
        """Record one engine-level event: on the task's run when it names a task.

        An event about a task is kept on a system run of that task, at its
        current step. One that names no task is the project's own (ADR-0037).
        """

        task = self.store.get_task(task_id) if task_id else None
        if task is None:
            return self.records.emit_project_event(project_id, event_type, payload)
        run = self.records.create_system_run(
            task,
            workflow_step=task.workflow_current_step or workflow_step,
            outcome=outcome,
            detail=detail,
        )
        return self.records.emit_event(run, event_type, payload)

    def _load_workflow_for_project(self, project: Project) -> WorkflowDefinition:
        self.use_project_definitions(project.id)
        workflow = self.workflows.get(project.workflow_id)
        if workflow is None:
            raise OrchestratorError(
                f"Unknown workflow {project.workflow_id!r} for project {project.id!r}."
            )
        return workflow
