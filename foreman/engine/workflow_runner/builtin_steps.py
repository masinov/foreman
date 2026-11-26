"""A human gate and a built-in step, and the events they leave.
"""

from __future__ import annotations

import time

from ...definitions.workflows import WorkflowStep
from ...domain.errors import EngineCommandInterrupt
from ...domain.models import HumanGateDecision, Project, Run, Task, utc_now_text
from ...domain.outcomes import (
    APPROVE,
    BLOCKED,
    ERROR,
    normalize_agent_outcome,
)
from ...domain.policy import PolicyMatrix, describe_resolution
from ...history.records import new_id
from ..branch_sync import task_working_dir
from ..builtins.base import BuiltinEventRecord
from ..document_changes import note_document_changes
from ..gates import gate_policy_decision
from ...history.logs import get_logger
from .base import WorkflowRunnerBase

_LOGGER = get_logger("orchestrator")


class BuiltinSteps(WorkflowRunnerBase):
    """Human gates and built-in steps."""

    def _run_human_gate_step(
        self,
        project: Project,
        task: Task,
        step_def: WorkflowStep,
        *,
        step: str,
        visit_count: int,
        carried_output: str | None,
    ) -> tuple[Run, str, str] | None:
        """Run a human-gate step. Returns None when the task now waits for a person.

        Policy may decide the gate on its own (``auto``), in which case the
        step has an outcome like any other.
        """

        run = self.records.create_running_run(
            task,
            role_id=step_def.role,
            workflow_step=step,
            agent_backend="builtin",
        )
        self.records.emit_event(
            run,
            "workflow.step_started",
            {"step": step, "visit_count": visit_count},
        )
        self._emit_policy_resolved(run, project, task)
        gate_policy = gate_policy_decision(project, task, step_def)
        if gate_policy == "auto":
            outcome, detail = self._auto_approve_gate(
                run, project, task, step_def
            )
        else:
            result = self.builtin_executor.execute(
                step_def.role,
                project=project,
                task=task,
                step_id=step,
                carried_output=carried_output,
                store=self.store,
                event_recorder=lambda event_record: self.persist_builtin_event(run, event_record),
                working_dir=task_working_dir(project, task),
            )
            self.tasks.save(task)
            self.records.complete_run(
                run,
                status="completed",
                outcome=result.outcome,
                detail=result.detail,
            )
            self.emit_builtin_events(run, result.events)
            self.records.emit_event(
                run,
                "workflow.paused",
                {
                    "step": step,
                    "reason": "human_gate",
                    "policy": step_def.policy,
                    # What the project asked to be told about; the
                    # delivery worker acts on this persisted decision.
                    "notify": self.records.notification_policy(project, task),
                },
            )
            # A task waiting for a person is not being worked on. Left
            # held, the lease made the engine wait out its remaining
            # lifetime before it could act on the decision.
            self.leases.release(task, project)
            return None
        return run, outcome, detail

    def _run_builtin_step(
        self,
        project: Project,
        task: Task,
        step_def: WorkflowStep,
        *,
        step: str,
        visit_count: int,
        carried_output: str | None,
    ) -> tuple[Run, str, str]:
        """Run a built-in step (tests, merge, mark done) and record its run."""

        run = self.records.create_running_run(
            task,
            role_id=step_def.role,
            workflow_step=step,
            agent_backend="builtin",
        )
        self.records.emit_event(
            run,
            "workflow.step_started",
            {"step": step, "visit_count": visit_count},
        )
        self._emit_policy_resolved(run, project, task)
        builtin_started = time.monotonic()
        try:
            result = self.builtin_executor.execute(
                step_def.role,
                project=project,
                task=task,
                step_id=step,
                carried_output=carried_output,
                store=self.store,
                # Saved as they happen, so each record carries its own time:
                # the tests' start is when they started, and their output can
                # be followed while they run.
                event_recorder=lambda event_record: self.persist_builtin_event(run, event_record),
                evidence_builder=self.build_completion_evidence,
                working_dir=task_working_dir(project, task),
                # A user's Stop, or an engine command, may cut a test run.
                interrupt_poll=lambda: self._poll_commands(task.id),
            )
        except EngineCommandInterrupt as exc:
            # Settled as an agent step is (``execute_guarded``): killed, the
            # task resumable at this step, and the interrupt goes on up.
            self.records.emit_event(
                run, "agent.killed", {"reason": str(exc), "gate_type": "command"}
            )
            self.records.complete_run(
                run,
                status="killed",
                outcome=ERROR,
                detail=str(exc),
                duration_ms=int((time.monotonic() - builtin_started) * 1000),
            )
            self.leases.release(task, project)
            raise
        self.tasks.save(task)
        self.records.complete_run(
            run,
            status="completed",
            outcome=result.outcome,
            detail=result.detail,
            # A test run or a merge takes real time; recording 0 made
            # every built-in step look instantaneous.
            duration_ms=int((time.monotonic() - builtin_started) * 1000),
        )
        self.emit_builtin_events(run, result.events)
        if step_def.role == "_builtin:merge" and result.outcome == "success":
            self._note_document_changes(project, task, result.events)
        # A builtin that blocks (e.g. the merge/mark_done completion
        # guard rejecting weak evidence) sets the task to blocked itself
        # and never routes through ``_create_system_run``; raise the one
        # attention-needed turn here so supervision still fires.
        if result.outcome == BLOCKED:
            self.records.emit_attention_needed(
                run,
                task.id,
                self.records.attention_trigger_for_block(task),
            )
        outcome = normalize_agent_outcome(result.outcome)
        detail = result.detail
        return run, outcome, detail

    def _note_document_changes(self, project: Project, task: Task, events) -> None:
        """Tell the unfinished tasks that rest on a document this merge changed.

        The merge is done whatever happens here, so a failure is logged and
        does not fail the step.
        """

        merge = next((event for event in events if event.event_type == "engine.merge"), None)
        if merge is None:
            return
        try:
            note_document_changes(
                self.records,
                self.store,
                project,
                task,
                from_sha=merge.payload.get("target_before"),
                sha=merge.payload.get("sha"),
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Could not note the documents the merge of %s changed", task.id)

    def _emit_policy_resolved(self, run: Run, project: Project, task: Task) -> None:
        """Record the resolved policy matrix once, on the task's first step.

        The audit trail should answer why a person was (or was not) asked, not
        only that they were, so every decision is written with the layer that
        produced it. Written once per task: resuming a paused task does not
        re-resolve anything a reader has not already seen.
        """

        if self.store.has_event(task_id=task.id, event_type="policy.resolved"):
            return
        resolved = PolicyMatrix.for_project(project).resolve_task(task)
        self.records.emit_event(
            run,
            "policy.resolved",
            {
                "task_type": task.task_type,
                "decisions": describe_resolution(resolved),
            },
        )

    def _auto_approve_gate(
        self,
        run: Run,
        project: Project,
        task: Task,
        step: WorkflowStep,
    ) -> tuple[str, str]:
        """Approve a policy-governed gate on the engine's behalf, with an audit record."""

        detail = f"Auto-approved by policy ({step.policy}=auto)."
        self.records.emit_event(
            run,
            "workflow.gate_auto_approved",
            {"step": step.id, "policy": step.policy},
        )
        self.records.complete_run(run, status="completed", outcome=APPROVE, detail=detail)
        self.store.save_human_gate_decision(
            HumanGateDecision(
                id=new_id("hg"),
                task_id=task.id,
                project_id=project.id,
                workflow_step=step.id,
                decision="approve",
                note=detail,
                decided_by=f"policy:{step.policy}",
                decided_at=utc_now_text(),
                run_id=run.id,
            )
        )
        return (APPROVE, detail)

    def emit_builtin_events(
        self,
        run: Run,
        events: tuple[BuiltinEventRecord, ...],
    ) -> None:
        for event_record in events:
            payload = dict(event_record.payload)
            payload["schema_version"] = event_record.schema_version
            self.records.emit_event(run, event_record.event_type, payload)

    def persist_builtin_event(
        self,
        run: Run,
        event_record: BuiltinEventRecord,
    ) -> None:
        """Persist one builtin event immediately while the builtin step is active."""

        payload = dict(event_record.payload)
        payload["schema_version"] = event_record.schema_version
        self.records.emit_event(run, event_record.event_type, payload)
