"""Writing what the engine did: runs, events and attention turns.

``RunRecords`` is the engine's only writer of runs and events. Every event
it saves is offered to the notifier, and a run that ends blocked raises one
attention turn.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..logs import compact_payload, event_log_level, get_logger, log_event
from ..models import Event, Project, Run, Task, TokenUsage, utc_now_text
from ..notifications import NotificationDispatcher, resolve_notification_policy
from ..store import ForemanStore

_LOGGER = get_logger("orchestrator")


def new_id(prefix: str) -> str:
    """Return a new identifier with a readable prefix."""

    return f"{prefix}-{uuid4().hex[:12]}"


class RunRecords:
    """Creates and completes runs and emits their events for one store."""

    def __init__(self, store: ForemanStore, notifier: NotificationDispatcher) -> None:
        self.store = store
        self.notifier = notifier

    def select_project_system_task(self, project_id: str) -> Task | None:
        """Choose a stable task for project-scoped synthetic orchestrator events."""

        active_tasks = self.store.list_tasks(
            project_id=project_id,
            statuses=("in_progress", "blocked"),
        )
        if active_tasks:
            return active_tasks[0]

        active_sprint = self.store.get_active_sprint(project_id)
        if active_sprint is not None:
            sprint_tasks = self.store.list_tasks(sprint_id=active_sprint.id)
            if sprint_tasks:
                return sprint_tasks[0]

        project_tasks = self.store.list_tasks(project_id=project_id)
        return project_tasks[0] if project_tasks else None

    def session_id_from_events(self, run: Run) -> str | None:
        """Return the backend session id announced during ``run``, if any.

        Runners emit ``agent.session`` as soon as the backend reports its
        session (Claude Code's ``init`` line); completion payloads repeat it,
        but a run that is killed or interrupted never reaches completion.
        """

        for event in reversed(self.store.list_events(run_id=run.id)):
            if event.event_type == "agent.session":
                session_id = str(event.payload.get("session_id") or "").strip()
                if session_id:
                    return session_id
        return None

    def create_running_run(
        self,
        task: Task,
        *,
        role_id: str,
        workflow_step: str,
        agent_backend: str,
        model: str | None = None,
        branch_name: str | None = None,
        prompt_text: str | None = None,
    ) -> Run:
        now = utc_now_text()
        run = Run(
            id=new_id("run"),
            task_id=task.id,
            project_id=task.project_id,
            role_id=role_id,
            workflow_step=workflow_step,
            agent_backend=agent_backend,
            status="running",
            model=model,
            branch_name=branch_name,
            prompt_text=prompt_text,
            started_at=now,
            created_at=now,
        )
        self.store.save_run(run)
        return run

    def create_system_run(
        self,
        task: Task,
        *,
        workflow_step: str,
        outcome: str,
        detail: str,
        role_id: str = "_builtin:orchestrator",
        agent_backend: str = "orchestrator",
        attention_trigger: str | None = None,
    ) -> Run:
        now = utc_now_text()
        run = Run(
            id=new_id("run"),
            task_id=task.id,
            project_id=task.project_id,
            role_id=role_id,
            workflow_step=workflow_step,
            agent_backend=agent_backend,
            status="completed",
            outcome=outcome,
            outcome_detail=detail,
            started_at=now,
            completed_at=now,
            created_at=now,
        )
        self.store.save_run(run)
        # A blocked system run means the task is transitioning to blocked: raise
        # exactly one attention-needed signal so a manager/human can intervene.
        if outcome == "blocked":
            self.emit_attention_needed(
                run, task.id, attention_trigger or "task_blocked"
            )
        return run

    def emit_attention_needed(
        self, run: Run, task_id: str | None, trigger: str
    ) -> None:
        """Emit one ``engine.attention_needed`` event for a supervision turn."""
        project = self.store.get_project(run.project_id)
        task = self.store.get_task(task_id) if task_id else None
        self.emit_event(
            run,
            "engine.attention_needed",
            {
                "trigger": trigger,
                "task_id": task_id,
                # What the project asked to be told about, persisted so a
                # later policy change cannot rewrite this moment.
                "notify": self.notification_policy(project, task),
            },
        )

    def notification_policy(self, project: Project | None, task: Task | None) -> str:
        """Resolve the notification decision for the events worth announcing."""

        return resolve_notification_policy(project, task)

    def attention_trigger_for_block(self, task: Task) -> str:
        """Pick the supervision trigger for a freshly-blocked task.

        A block driven by a failed completion-evidence proof gate is surfaced as
        ``evidence_failed`` so the digest leads with the proof verdict; any other
        block is the generic ``task_blocked``.
        """
        evidence = task.completion_evidence
        if evidence is not None and getattr(evidence, "proof_status", None) == "failed":
            return "evidence_failed"
        return "task_blocked"

    def complete_run(
        self,
        run: Run,
        *,
        status: str,
        outcome: str,
        detail: str,
        model: str | None = None,
        session_id: str | None = None,
        cost_usd: float | None = None,
        token_count: int | None = None,
        token_usage: TokenUsage | None = None,
        duration_ms: int | None = None,
        retry_count: int | None = None,
        failure_type: str | None = None,
        commit_sha: str | None = None,
    ) -> None:
        run.status = status
        run.outcome = outcome
        run.outcome_detail = detail
        if failure_type is not None:
            run.failure_type = failure_type
        run.model = model
        run.session_id = session_id
        if cost_usd is not None:
            run.cost_usd = cost_usd
        if token_count is not None:
            run.token_count = token_count
        if token_usage is not None:
            run.token_usage = token_usage
        if retry_count is not None:
            run.retry_count = retry_count
        if commit_sha is not None:
            run.commit_sha = commit_sha
        run.duration_ms = duration_ms
        run.completed_at = utc_now_text()
        self.store.save_run(run)

    def emit_event(
        self,
        run: Run,
        event_type: str,
        payload: dict[str, Any],
        *,
        role_id: str | None = None,
        timestamp: str | None = None,
    ) -> Event:
        event = Event(
            id=new_id("event"),
            run_id=run.id,
            task_id=run.task_id,
            project_id=run.project_id,
            event_type=event_type,
            timestamp=timestamp or utc_now_text(),
            role_id=role_id or run.role_id,
            payload=payload,
        )
        self.store.save_event(event)
        # Mirror every persisted event to the process log so `foreman serve`,
        # which has no terminal, can be understood from its log alone. The
        # level comes from the event family: the narrative at INFO, the agent
        # output firehose at DEBUG, so a resident engine's own lifecycle stays
        # readable. The logger is inert until the CLI configures a handler.
        log_event(
            _LOGGER,
            event.event_type,
            level=event_log_level(event.event_type),
            project_id=event.project_id,
            task_id=event.task_id,
            run_id=event.run_id,
            step=run.workflow_step,
            role_id=event.role_id,
            # Nested rather than flattened: event payloads carry their own
            # ``task_id``/``run_id`` keys whose meaning differs from the row's.
            payload=compact_payload(payload),
        )
        # Notification is a read of the persisted event, not a second source of
        # truth: whatever the audit log says happened is what a destination is
        # told. The dispatcher queues and returns; it never sends here, and it
        # never raises, so no notification setup can fail a run.
        self.notifier.consider(event)
        return event
