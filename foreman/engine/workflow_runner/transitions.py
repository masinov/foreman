"""A step's end recorded, and the workflow followed to the next step.
"""

from __future__ import annotations

from ...definitions.workflows import WorkflowDefinition, WorkflowStep
from ...domain.models import Project, Run, Task
from ...domain.outcomes import DENY, ERROR, FAILURE, KILLED, STEER
from ...domain.settings import ProjectSettings
from ..gates import blocked_reason_for_unhandled_outcome
from ..model_selection import resolve_step_model_selection
from ..step_failures import (
    NO_RESULT,
    REVIEW,
    TESTS,
    move_up_line,
    own_failure_type,
)
from .base import WorkflowRunnerBase

STEP_FAILED_EVENT = "workflow.step_failed"
STEP_MOVES_UP_EVENT = "workflow.step_moves_up"


class Transitions(WorkflowRunnerBase):
    """Transitions between steps."""

    def _record_step_completed(
        self,
        run: Run,
        project: Project,
        task: Task,
        step_def: WorkflowStep,
        step: str,
        outcome: str,
        settings: ProjectSettings,
    ) -> None:
        """Record that a step finished, and what follows from it for the task."""

        self.records.emit_event(
            run,
            "workflow.step_completed",
            {"step": step, "outcome": outcome},
        )

        # Evidence built for the reviewer's prompt predates the review. Now
        # that a decision exists, record it, so the task shows what was
        # decided rather than "no review yet" until the merge step.
        if (
            task.completion_evidence is not None
            and not step_def.role.startswith("_builtin:")
            and step_def.role in self.roles
            and self.roles[step_def.role].completion.output.extract_decision
        ):
            task.completion_evidence = self.build_completion_evidence(
                task, project
            )
            self.tasks.save(task)

    def _failure_of_own_work(
        self,
        workflow: WorkflowDefinition,
        run: Run,
        step_def: WorkflowStep,
        step: str,
        outcome: str,
    ) -> tuple[str, str] | None:
        """The step whose own work failed with this end, and how: ``(step, kind)``.

        Only three ends are a failure of a step's own work (ADR-0041): its run
        ended without a result, the review sent its work back, the tests
        failed after it. A review or the tests fail the step the workflow
        sends the work back to. Everything else is not counted: a restart or a
        Stop never gets here, and a conflict send-back, a failed merge, a
        usage wait, an infrastructure error and a person's send-back are
        not the work's fault.
        """

        builtin = step_def.role.startswith("_builtin:")
        if not builtin:
            role = self.roles.get(step_def.role)
            if role is None:
                return None
            if outcome in (ERROR, KILLED) and own_failure_type(run.failure_type):
                return step, NO_RESULT
            if role.completion.output.extract_decision and outcome in (DENY, STEER):
                target = self._agent_step_sent_back_to(workflow, step, outcome)
                return (target, REVIEW) if target else None
            return None
        if step_def.role == "_builtin:run_tests" and outcome == FAILURE:
            # No test command is a setup problem, not failing tests.
            ran = any(
                event.event_type == "engine.test_run" and event.payload.get("command")
                for event in self.store.list_events(run_id=run.id)
            )
            target = self._agent_step_sent_back_to(workflow, step, outcome)
            return (target, TESTS) if ran and target else None
        return None

    def _agent_step_sent_back_to(
        self, workflow: WorkflowDefinition, step: str, outcome: str
    ) -> str | None:
        """The agent step an end sends the work back to, or None."""

        transition = workflow.find_transition(step, outcome)
        target = workflow.get_step(transition.to_step) if transition and transition.to_step else None
        if target is None or target.role.startswith("_builtin:") or target.role not in self.roles:
            return None
        return target.id

    def _charge_failure(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
        run: Run,
        step_def: WorkflowStep,
        step: str,
        outcome: str,
    ) -> str | None:
        """Count a failure of a step's own work, and move the step up when due.

        Returns the step charged, or None when this end is not a failure of
        a step's own work. The count is per step and model, kept on the task.
        A move up is a line in the task's Activity with its reason.
        """

        failed = self._failure_of_own_work(workflow, run, step_def, step, outcome)
        if failed is None:
            return None
        target, kind = failed
        target_def = workflow.get_step(target)
        role = self.roles.get(target_def.role) if target_def is not None else None
        if role is None:
            return None
        before = resolve_step_model_selection(
            task=task, role=role, project=project, step_id=target
        )
        model = run.model if target == step else self._latest_model(task, target)
        model = model or before.model or ""
        counts = {name: dict(models) for name, models in task.step_failures.items()}
        on_model = counts.setdefault(target, {})
        on_model[model] = int(on_model.get(model, 0)) + 1
        task.step_failures = counts
        self.tasks.save(task)
        self.records.emit_event(
            run,
            STEP_FAILED_EVENT,
            {"step": target, "role_id": role.id, "model": model, "kind": kind, "count": on_model[model]},
        )
        after = resolve_step_model_selection(
            task=task, role=role, project=project, step_id=target
        )
        if after.moves_up > before.moves_up and after.model:
            kinds = [
                event.payload.get("kind", "")
                for event in self.store.list_events(task_id=task.id)
                if event.event_type == STEP_FAILED_EVENT
                and event.payload.get("step") == target
                and event.payload.get("model") == model
            ][-on_model[model]:]
            line = move_up_line(target, after.model, kinds)
            moved = self.records.create_system_run(
                task, workflow_step=target, outcome="success", detail=line
            )
            self.records.emit_event(
                moved,
                STEP_MOVES_UP_EVENT,
                {
                    "step": target,
                    "role_id": role.id,
                    "from_model": model,
                    "to_model": after.model,
                    "failures": on_model[model],
                    "escalate_after": role.agent.escalate_after,
                    "reason": line,
                },
            )
        return target

    def _latest_model(self, task: Task, step: str) -> str | None:
        """The model the step's latest agent run used."""

        for run in reversed(self.store.list_runs(task_id=task.id)):
            if run.workflow_step == step and not run.role_id.startswith("_builtin:") and run.model:
                return run.model
        return None

    def _follow_transition(
        self,
        project: Project,
        workflow: WorkflowDefinition,
        task: Task,
        run: Run,
        *,
        step: str,
        outcome: str,
        detail: str,
        failed_step: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Move the task along its workflow. Returns the next step and what it carries.

        The next step is None when the workflow ends here: the task is done,
        or no transition handles the outcome and the task is blocked. A step
        whose own run failed, and that its role gives more than one model, is
        run again when the workflow says nothing of its failure: the models
        it has are what the failure is answered with (ADR-0041).
        """

        transition = workflow.find_transition(step, outcome)
        if transition is None and failed_step == step and self._has_models_to_move_up(task, step, workflow):
            self.records.emit_event(
                run, "workflow.step_retried", {"step": step, "outcome": outcome}
            )
            task.workflow_current_step = step
            task.workflow_carried_output = detail
            self.tasks.save(task)
            return step, detail
        if transition is None:
            if task.status != "done":
                self.records.emit_event(
                    run,
                    "workflow.no_transition",
                    {"step": step, "outcome": outcome},
                )
                task.status = "blocked"
                task.blocked_reason = blocked_reason_for_unhandled_outcome(
                    workflow=workflow,
                    step=step,
                    outcome=outcome,
                    detail=detail,
                )
            task.workflow_current_step = None
            task.workflow_carried_output = None
            self.tasks.save(task)
            self.leases.release(task, project)
            return None, None

        self.records.emit_event(
            run,
            "workflow.transition",
            {
                "from_step": step,
                "to_step": transition.to_step,
                "trigger": transition.trigger,
            },
        )
        carried_output = detail if transition.carry_output else None
        if transition.trigger == "completion:conflict":
            task.step_visit_counts = {}
            self.records.emit_event(
                run,
                "workflow.step_visit_reset",
                {
                    "reason": "merge_conflict_recovery",
                    "from_step": step,
                    "to_step": transition.to_step,
                },
            )
        # The next step is recorded in the same write that leaves this one. A
        # crash before that step starts then resumes there; with the step
        # cleared first, recovery restarted the whole task and an approval
        # recorded a moment earlier was lost.
        task.workflow_current_step = transition.to_step
        task.workflow_carried_output = carried_output if transition.to_step is not None else None
        self.tasks.save(task)
        return transition.to_step, carried_output

    def _has_models_to_move_up(self, task: Task, step: str, workflow: WorkflowDefinition) -> bool:
        step_def = workflow.get_step(step)
        role = self.roles.get(step_def.role) if step_def is not None else None
        if role is None:
            return False
        pinned = (task.executor_overrides or {}).get("models")
        if isinstance(pinned, dict) and pinned.get(step):
            return False
        return len(role.agent.model_ladder) > 1
