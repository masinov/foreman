"""An agent's step: running the role and reading what its run says.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from ...definitions.roles import RoleDefinition
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
from ..model_selection import ModelSelection, resolve_step_model_selection
from ..results import AgentExecutionResult
from ..repo_facts import step_changes_payload
from ...domain.step_reads import STEP_READS_EVENT, reads_before_first_change
from ..output_contract import (
    UNREAD_APPROVAL_DETAIL,
    approved_without_reading,
    contract_retry_reason,
    with_retry_instruction,
)
from .base import WorkflowRunnerBase


@dataclass(frozen=True, slots=True)
class _Attempt:
    """What every attempt at one agent step shares."""

    role: RoleDefinition
    project: Project
    task: Task
    step: str
    carried_output: str | None
    model: str | None


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
        prompt, guidance = self._prompt_with_notes(role, project, task, carried_output, context_projection)
        model_selection = resolve_step_model_selection(
            task=task,
            role=role,
            project=project,
            step_id=step,
        )
        run = self._open_agent_run(
            role,
            project,
            task,
            step=step,
            visit_count=visit_count,
            prompt=prompt,
            guidance=guidance,
            model_selection=model_selection,
            context_projection=context_projection,
            branch_sync_event=branch_sync_event,
        )
        session_key = (role.id, role.agent.backend)
        session_id = self._step_session(role, task, session_ids, session_key)
        attempt = _Attempt(
            role=role,
            project=project,
            task=task,
            step=step,
            carried_output=carried_output,
            model=model_selection.model,
        )
        result = self._execute_and_record(attempt, run, prompt, session_id)
        run, result = self._corrective_retry(
            attempt,
            run,
            result,
            prompt=prompt,
            session_id=session_id,
            visit_count=visit_count,
            context_projection=context_projection,
        )
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
        return run, self._settled_outcome(role, project, task, run, result), result.detail

    def _prompt_with_notes(
        self,
        role: RoleDefinition,
        project: Project,
        task: Task,
        carried_output: str | None,
        context_projection: Any,
    ) -> tuple[str, list[Any]]:
        """The step's prompt, and the notes it delivers to the agent.

        Notes are for the agent doing the work. A role that does not decide
        gets the notes written since it last ran, and they are marked
        delivered once the run that carries them exists. A step that was
        killed (an interruption, a shutdown) starts again with whatever
        guidance it had been given, as well as any since. A reviewer is
        shown every note as context and is delivered none.
        """

        prompt = self.prompts.build(
            role,
            project,
            task,
            carried_output,
            context_projection=context_projection,
        )
        killed = {earlier.id for earlier in self.store.list_runs(task_id=task.id, status="killed")}
        task_events = self.store.list_events(task_id=task.id)
        if role.completion.output.extract_decision:
            notes = guidance_notes(task_events, void_runs=killed)
            return prompt_with_guidance_as_context(prompt, notes), []
        guidance = pending_guidance(task_events, void_runs=killed)
        return prompt_with_guidance(prompt, guidance), guidance

    def _open_agent_run(
        self,
        role: RoleDefinition,
        project: Project,
        task: Task,
        *,
        step: str,
        visit_count: int,
        prompt: str,
        guidance: list[Any],
        model_selection: ModelSelection,
        context_projection: Any,
        branch_sync_event: tuple[str, dict[str, Any]] | None,
    ) -> Run:
        """Create the step's run and record what it is started with."""

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
                # How far up its role's models the step is, and how many
                # failures of its own work it has had on this one.
                "moves_up": model_selection.moves_up,
                "failures": model_selection.failures,
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
        return run

    def _step_session(
        self,
        role: RoleDefinition,
        task: Task,
        session_ids: dict[tuple[str, str], str],
        session_key: tuple[str, str],
    ) -> str | None:
        """The session a role that keeps one resumes: this pass's, else the task's latest."""

        if not role.agent.session_persistence:
            return None
        session_id = session_ids.get(session_key)
        if session_id is None:
            session_id = self.store.get_latest_session_id(
                task_id=task.id,
                role_id=role.id,
                agent_backend=role.agent.backend,
            )
            if session_id:
                session_ids[session_key] = session_id
        return session_id

    def _execute_and_record(
        self,
        attempt: _Attempt,
        run: Run,
        prompt: str,
        session_id: str | None,
        *,
        reread_prompt: str | None = None,
    ) -> AgentExecutionResult:
        """Run the role once under *run* and complete the run with what it did.

        ``reread_prompt`` is the first attempt's prompt on a retry: a role
        asked to read that approves a cut diff unread again stops the task
        for a person.
        """

        role, project, task = attempt.role, attempt.project, attempt.task
        # Any sync of the branch with the default branch is done before the
        # step opens, so this is the head the agent starts from.
        head_before = self._branch_commit(project, task)
        result = self.agent_steps.execute_guarded(
            run=run,
            role=role,
            project=project,
            task=task,
            workflow_step=attempt.step,
            prompt=prompt,
            session_id=session_id,
            carried_output=attempt.carried_output,
            model=attempt.model,
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
        if reread_prompt is not None and approved_without_reading(role, reread_prompt, result):
            # Asked to read, it approved unread again. That is not a review;
            # the task stops for a person.
            result = replace(result, outcome=ERROR, detail=UNREAD_APPROVAL_DETAIL, failure_type="policy")
        head_after = self._branch_commit(project, task)
        self.records.complete_run(
            run,
            status=result.status,
            outcome=result.outcome,
            detail=result.detail,
            model=result.model or attempt.model or None,
            session_id=result.session_id,
            cost_usd=result.cost_usd,
            session_cost_usd=result.session_cost_usd,
            token_count=result.token_count,
            token_usage=result.token_usage,
            duration_ms=result.duration_ms,
            retry_count=result.retry_count,
            failure_type=result.failure_type,
            commit_sha=head_after,
            record=result.record,
        )
        self._record_step_changes(run, project, head_before, head_after)
        self._record_step_reads(run)
        return result

    def _record_step_reads(self, run: Run) -> None:
        """Record the reads the run made before its first change (ADR-0041)."""

        events = self.store.list_events(run_id=run.id)
        reads = reads_before_first_change((event.event_type, event.payload) for event in events)
        self.records.emit_event(run, STEP_READS_EVENT, reads.payload())

    def _record_step_changes(
        self, run: Run, project: Project, head_before: str | None, head_after: str | None
    ) -> None:
        """When the step moved the branch, record what it changed (ADR-0038)."""

        payload = step_changes_payload(
            project.repo_path, project.default_branch, head_before, head_after
        )
        if payload is not None:
            self.records.emit_event(run, "engine.step_changes", payload)

    def _corrective_retry(
        self,
        attempt: _Attempt,
        run: Run,
        result: AgentExecutionResult,
        *,
        prompt: str,
        session_id: str | None,
        visit_count: int,
        context_projection: Any,
    ) -> tuple[Run, AgentExecutionResult]:
        """Ask once more when the answer broke the output contract; else keep it."""

        role = attempt.role
        if result.failure_type == "quota":
            return run, result
        retry_reason = contract_retry_reason(role, result)
        if retry_reason is None and approved_without_reading(role, prompt, result):
            retry_reason = "approved_unread"
        if retry_reason is None:
            return run, result
        self.records.emit_event(
            run,
            "engine.output_contract_retry",
            {
                "step": attempt.step,
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
            attempt.task,
            role_id=role.id,
            workflow_step=attempt.step,
            agent_backend=role.agent.backend,
            model=attempt.model or None,
            branch_name=attempt.task.branch_name,
            prompt_text=retry_prompt,
        )
        self.write_runtime_context(
            retry_run,
            attempt.project,
            context_projection=context_projection,
        )
        self.records.emit_event(
            retry_run,
            "workflow.step_started",
            {
                "step": attempt.step,
                "visit_count": visit_count,
                "retry_attempt": 1,
            },
        )
        retry_result = self._execute_and_record(
            attempt, retry_run, retry_prompt, retry_session_id, reread_prompt=prompt
        )
        return retry_run, retry_result

    def _settled_outcome(
        self,
        role: RoleDefinition,
        project: Project,
        task: Task,
        run: Run,
        result: AgentExecutionResult,
    ) -> str:
        """The step's outcome in the workflow's words; a decision records its commit."""

        if not role.completion.output.extract_decision:
            return normalize_agent_outcome(result.outcome)
        outcome = normalize_reviewer_decision(result.outcome)
        # A decision is about the commit the reviewer saw. Record it, so
        # evidence can tell an approval of the head commit from an approval
        # of an earlier one.
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
        return outcome
