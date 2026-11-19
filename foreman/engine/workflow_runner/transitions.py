"""A step's end recorded, and the workflow followed to the next step.
"""

from __future__ import annotations

from ...definitions.workflows import WorkflowDefinition, WorkflowStep
from ...domain.models import Project, Run, Task
from ...domain.settings import ProjectSettings
from ..gates import blocked_reason_for_unhandled_outcome
from .base import WorkflowRunnerBase


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
    ) -> tuple[str | None, str | None]:
        """Move the task along its workflow. Returns the next step and what it carries.

        The next step is None when the workflow ends here: the task is done,
        or no transition handles the outcome and the task is blocked.
        """

        transition = workflow.find_transition(step, outcome)
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
