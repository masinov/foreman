"""An agent's step: running the role and reading what its run says.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ...definitions.workflows import WorkflowStep
from ...domain.guidance import (
    GUIDANCE_DELIVERED_EVENT,
    guidance_notes,
    pending_guidance,
    prompt_with_guidance,
    prompt_with_guidance_as_context,
)
from ...domain.models import Project, Run, Task
from ...domain.outcomes import (
    ERROR,
    normalize_agent_outcome,
    normalize_reviewer_decision,
)
from ...repo.context import build_project_context
from ..branch_sync import context_mirror_dirs
from ..errors import OrchestratorError, QuotaPauseError
from ..model_selection import resolve_step_model_selection
from ..output_contract import (
    UNREAD_APPROVAL_DETAIL,
    approved_without_reading,
    contract_retry_reason,
    with_retry_instruction,
)
from .base import WorkflowRunnerBase


class AgentSteps(WorkflowRunnerBase):
    """Agent steps."""

    def _run_agent_step(
        self,
        project: Project,
        task: Task,
        step_def: WorkflowStep,
        *,
        step: str,
        visit_count: int,
        carried_output: str | None,
        branch_sync_event: tuple[str, dict[str, Any]] | None,
        session_ids: dict[tuple[str, str], str],
    ) -> tuple[Run, str, str]:
        """Run an agent step: build the prompt, run the role, record the run.

        A response that breaks the role's output contract gets one corrective
        retry. A quota stop pauses the task and raises ``QuotaPauseError``.
        """

        role = self.roles.get(step_def.role)
        if role is None:
            raise OrchestratorError(f"Unknown role {step_def.role!r}.")
        task.assigned_role = role.id
        self.tasks.save(task)

        context_projection = build_project_context(
            self.store,
            project,
            current_task=task,
            carried_output=carried_output,
            mirror_dirs=context_mirror_dirs(project, task),
        )
        prompt = self.prompts.build(
            role,
            project,
            task,
            carried_output,
            context_projection=context_projection,
        )
        # Notes are for the agent doing the work. A role that does not decide
        # gets the notes written since it last ran, and they are marked
        # delivered once the run that carries them exists. A step that was
        # killed (an interruption, a shutdown) starts again with whatever
        # guidance it had been given, as well as any since. A reviewer is
        # shown every note as context and is delivered none.
        killed = {earlier.id for earlier in self.store.list_runs(task_id=task.id, status="killed")}
        task_events = self.store.list_events(task_id=task.id)
        if role.completion.output.extract_decision:
            guidance = []
            prompt = prompt_with_guidance_as_context(
                prompt, guidance_notes(task_events, void_runs=killed)
            )
        else:
            guidance = pending_guidance(task_events, void_runs=killed)
            prompt = prompt_with_guidance(prompt, guidance)
        model_selection = resolve_step_model_selection(
            task=task,
            role=role,
            project=project,
            step_id=step,
            visit_count=visit_count,
        )
        model = model_selection.model or ""
        run = self.records.create_running_run(
            task,
            role_id=role.id,
            workflow_step=step,
            agent_backend=role.agent.backend,
            model=model_selection.model,
            branch_name=task.branch_name,
            prompt_text=prompt,
        )
        self.records.emit_event(
            run,
            "workflow.model_selected",
            {
                "step": step,
                "model": model_selection.model,
                "visit_count": visit_count,
                "source": model_selection.source,
            },
        )
        self.records.emit_event(
            run,
            "engine.role_policy",
            {
                "role_id": role.id,
                "backend": role.agent.backend,
                "permission_mode": role.agent.permission_mode,
                "allowed_tools": list(role.agent.tools.allowed),
                "disallowed_tools": list(role.agent.tools.disallowed),
                "no_tools": role.agent.tools.none,
            },
        )
        self.write_runtime_context(
            run,
            project,
            context_projection=context_projection,
        )
        self.records.emit_event(
            run,
            "agent.prompt",
            {"text": prompt},
            role_id=role.id,
        )
        if guidance:
            self.records.emit_event(
                run,
                GUIDANCE_DELIVERED_EVENT,
                {
                    "message_event_ids": [note.event_id for note in guidance],
                    "role": role.id,
                    "step": step,
                },
            )
        self.records.emit_event(
            run,
            "workflow.step_started",
            {"step": step, "visit_count": visit_count},
        )
        self._emit_policy_resolved(run, project, task)
        if branch_sync_event is not None:
            event_type, payload = branch_sync_event
            self.records.emit_event(run, event_type, payload)
        session_key = (role.id, role.agent.backend)
        session_id: str | None = None
        if role.agent.session_persistence:
            session_id = session_ids.get(session_key)
            if session_id is None:
                session_id = self.store.get_latest_session_id(
                    task_id=task.id,
                    role_id=role.id,
                    agent_backend=role.agent.backend,
                )
                if session_id:
                    session_ids[session_key] = session_id
        result = self.agent_steps.execute_guarded(
            run=run,
            role=role,
            project=project,
            task=task,
            workflow_step=step,
            prompt=prompt,
            session_id=session_id,
            carried_output=carried_output,
            model=model_selection.model,
            event_recorder=lambda event_record: self.signals.persist_agent_event(
                run,
                task,
                project,
                role.id,
                event_record,
            ),
        )
        if not result.events_streamed:
            self.signals.emit_agent_events(run, task, project, role.id, result.events)
        self.records.complete_run(
            run,
            status=result.status,
            outcome=result.outcome,
            detail=result.detail,
            model=result.model or model or None,
            session_id=result.session_id,
            cost_usd=result.cost_usd,
            session_cost_usd=result.session_cost_usd,
            token_count=result.token_count,
            token_usage=result.token_usage,
            duration_ms=result.duration_ms,
            retry_count=result.retry_count,
            failure_type=result.failure_type,
            commit_sha=self._branch_commit(project, task),
        )
        retry_reason = (
            None
            if result.failure_type == "quota"
            else contract_retry_reason(role, result)
        )
        if (
            retry_reason is None
            and result.failure_type != "quota"
            and approved_without_reading(role, prompt, result)
        ):
            retry_reason = "approved_unread"
        if retry_reason is not None:
            self.records.emit_event(
                run,
                "engine.output_contract_retry",
                {
                    "step": step,
                    "role_id": role.id,
                    "reason": retry_reason,
                    "retry_attempt": 1,
                },
            )
            retry_session_id = result.session_id or session_id
            retry_prompt = with_retry_instruction(
                prompt,
                role,
                retry_reason,
                resumes_session=bool(retry_session_id),
            )
            retry_run = self.records.create_running_run(
                task,
                role_id=role.id,
                workflow_step=step,
                agent_backend=role.agent.backend,
                model=model or None,
                branch_name=task.branch_name,
                prompt_text=retry_prompt,
            )
            self.write_runtime_context(
                retry_run,
                project,
                context_projection=context_projection,
            )
            self.records.emit_event(
                retry_run,
                "workflow.step_started",
                {
                    "step": step,
                    "visit_count": visit_count,
                    "retry_attempt": 1,
                },
            )
            retry_result = self.agent_steps.execute_guarded(
                run=retry_run,
                role=role,
                project=project,
                task=task,
                workflow_step=step,
                prompt=retry_prompt,
                session_id=retry_session_id,
                carried_output=carried_output,
                model=model_selection.model,
                event_recorder=lambda event_record: self.signals.persist_agent_event(
                    retry_run,
                    task,
                    project,
                    role.id,
                    event_record,
                ),
            )
            if not retry_result.events_streamed:
                self.signals.emit_agent_events(
                    retry_run,
                    task,
                    project,
                    role.id,
                    retry_result.events,
                )
            if approved_without_reading(role, prompt, retry_result):
                # Asked to read, it approved unread again. That is not a
                # review; the task stops for a person.
                retry_result = replace(
                    retry_result, outcome=ERROR, detail=UNREAD_APPROVAL_DETAIL
                )
            self.records.complete_run(
                retry_run,
                status=retry_result.status,
                outcome=retry_result.outcome,
                detail=retry_result.detail,
                model=retry_result.model or model or None,
                session_id=retry_result.session_id,
                cost_usd=retry_result.cost_usd,
                session_cost_usd=retry_result.session_cost_usd,
                token_count=retry_result.token_count,
                token_usage=retry_result.token_usage,
                duration_ms=retry_result.duration_ms,
                retry_count=retry_result.retry_count,
                failure_type=retry_result.failure_type,
                commit_sha=self._branch_commit(project, task),
            )
            run = retry_run
            result = retry_result
        if result.failure_type == "quota":
            self.pause_for_quota(
                project,
                task,
                run,
                step=step,
                carried_output=carried_output,
                result=result,
            )
            raise QuotaPauseError(
                task.id,
                retry_after=result.retry_after,
                detail=result.detail,
            )
        if role.agent.session_persistence and result.session_id:
            session_ids[session_key] = result.session_id
        if role.completion.output.extract_decision:
            outcome = normalize_reviewer_decision(result.outcome)
            # A decision is about the commit the reviewer saw. Record
            # it, so evidence can tell an approval of the head commit
            # from an approval of an earlier one.
            self.records.emit_event(
                run,
                "engine.review_recorded",
                {
                    "role": role.id,
                    "review_kind": role.completion.review_kind,
                    "outcome": outcome,
                    "head_sha": self.evidence.branch_head(project, task),
                },
            )
        else:
            outcome = normalize_agent_outcome(result.outcome)
        detail = result.detail
        return run, outcome, detail
