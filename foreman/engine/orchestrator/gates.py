"""A person's decision at a human gate, and running on from it (ADR-0011).
"""

from __future__ import annotations

from pathlib import Path

from ...mutations import MutationError
from ...mutations.gates import find_gate_stop, record_gate_decision
from ...repo.context import (
    build_project_context,
)
from ..branch_sync import (
    context_mirror_dirs,
)
from ..errors import (
    OrchestratorError,
)
from ..results import (
    HumanGateResumeResult,
)
from .base import OrchestratorBase, generate_branch_name


class HumanGateResume(OrchestratorBase):
    """Resuming a task from a human gate."""

    def resume_human_gate(
        self,
        task_id: str,
        *,
        outcome: str,
        note: str | None = None,
        defer: bool = False,
        seen_version: str | None = None,
    ) -> HumanGateResumeResult:
        """Apply one human-gate decision and continue execution when possible.

        With ``defer`` the decision is recorded and the task is left
        ``in_progress`` at the step the decision leads to, for the project's
        engine to continue. That is what every caller outside an engine must
        use: the CLI and the dashboard decide, the engine (which holds the
        project lock and the task lease) executes. ADR-0011.
        """

        try:
            stop = find_gate_stop(
                self.store, task_id, outcome, self._load_workflow_for_project
            )
        except MutationError as exc:
            raise OrchestratorError(str(exc)) from exc
        project, workflow = stop.project, stop.workflow
        next_step = stop.next_step

        deferred = False
        if not next_step.role.startswith("_builtin:"):
            next_role = self.roles.get(next_step.role)
            if next_role is None:
                raise OrchestratorError(
                    f"Workflow {workflow.id!r} references unknown role {next_step.role!r}."
                )
            native_backend_available = (
                next_role.agent.backend in self.agent_runners
                and Path(project.repo_path).is_dir()
            )
            deferred = (
                self.agent_executor is None
                and not native_backend_available
            )
        deferred = deferred or defer
        record = record_gate_decision(
            self.store,
            self.records,
            stop,
            outcome=outcome,
            note=note,
            deferred=deferred,
            save=self.tasks.save,
            seen_version=seen_version,
        )
        current_task, carried_output = record.task, record.carried_output

        if deferred:
            refreshed = self.store.get_task(current_task.id)
            if refreshed is None:
                raise OrchestratorError(
                    f"Task {current_task.id!r} disappeared during deferred resume."
                )
            return HumanGateResumeResult(
                task=refreshed,
                decision=outcome,
                paused_step=stop.paused_step,
                next_step=next_step.id,
                deferred=True,
                carried_output=carried_output,
                note=note,
                version=record.version,
                version_named=record.version_named,
            )

        # Every task gets its own branch and worktree from the engine, in both
        # selection modes (ADR-0012). In autonomous mode the agent chooses what
        # to work on, not where: without a worktree it would run in the
        # operator's checkout and commit to whatever is checked out there.
        current_task.branch_name = current_task.branch_name or generate_branch_name(
            current_task
        )
        self.task_worktrees.ensure(project, current_task)

        self.runner.run_from_step(
            project,
            workflow,
            current_task,
            step=next_step.id,
            carried_output=carried_output,
        )
        refreshed = self.store.get_task(current_task.id)
        if refreshed is None:
            raise OrchestratorError(
                f"Task {current_task.id!r} disappeared during human-gate resume."
            )
        latest_run = self.store.get_latest_run(refreshed.id)
        if latest_run is not None:
            self.runner.write_runtime_context(
                latest_run,
                project,
                context_projection=build_project_context(
                    self.store,
                    project,
                    current_task=refreshed,
                    carried_output=refreshed.workflow_carried_output,
                    mirror_dirs=context_mirror_dirs(project, refreshed),
                ),
            )
        return HumanGateResumeResult(
            task=refreshed,
            decision=outcome,
            paused_step=stop.paused_step,
            next_step=next_step.id,
            deferred=False,
            carried_output=carried_output,
            note=note,
            version=record.version,
            version_named=record.version_named,
        )
