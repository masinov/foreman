"""A step moves up its role's models only after failures of its own work (ADR-0041)."""

from __future__ import annotations

from dataclasses import replace

from foreman.domain.errors import EngineCommandInterrupt
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.engine.results import AgentExecutionResult
from foreman.store import ForemanStore

from engine_support import OrchestratorTestCase, ScriptedAgentExecutor

LADDER = ("model-A", "model-B", "model-C")


class MovesUpTests(OrchestratorTestCase):
    """What counts as a failure, what does not, and what happens past the last model."""

    def _start(self, *, ladder=LADDER, escalate_after=2, overrides=None, test_command="test -f ready.txt"):
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        store.initialize()
        self.addCleanup(store.close)
        project, _, task = self.seed_project(store, repo_path=repo_path, test_command=test_command)
        project.settings["completion_guard_enabled"] = False
        store.save_project(project)
        if overrides:
            task.executor_overrides = overrides
            store.save_task(task)
        base = self.roles["developer"]
        roles = dict(self.roles)
        roles["developer"] = replace(
            base,
            agent=replace(
                base.agent, model="", model_ladder=ladder, escalate_after=escalate_after
            ),
        )
        self.repo_path = repo_path
        return store, project, task, roles

    def _developer(self, *, ready: bool = False, result=None):
        def handler(*, task, prompt, carried_output):
            tree = self.work_dir(task, self.repo_path)
            name = "ready.txt" if ready else f"f{len(list(tree.glob('f*.txt')))}.txt"
            self.write_text(tree / name, "x\n")
            self.commit_all(tree, "feat: work")
            return result or AgentExecutionResult(outcome="done", detail="Done.")

        return handler

    def _run(self, store, project, roles, handlers):
        executor = ScriptedAgentExecutor(handlers)
        orchestrator = ForemanOrchestrator(
            store, roles=roles, workflows=self.workflows, agent_executor=executor
        )
        orchestrator.run_project(project.id)
        return executor

    @staticmethod
    def _models(store, task, step="develop"):
        return [
            run.model
            for run in store.list_runs(task_id=task.id)
            if run.workflow_step == step and run.role_id == "developer"
        ]

    @staticmethod
    def _lines(store, task):
        return [
            run.outcome_detail
            for run in store.list_runs(task_id=task.id)
            if run.role_id == "_builtin:orchestrator"
        ]

    def test_it_takes_escalate_after_test_failures_to_move_up(self) -> None:
        store, project, task, roles = self._start(escalate_after=2)
        self._run(
            store,
            project,
            roles,
            {
                ("developer", 1): self._developer(),
                ("developer", 2): self._developer(),
                ("developer", 3): self._developer(ready=True),
                ("code_reviewer", 1): lambda **_: AgentExecutionResult(outcome="approve", detail="ok"),
            },
        )
        self.assertEqual(self._models(store, task), ["model-A", "model-A", "model-B"])
        self.assertEqual(
            [line for line in self._lines(store, task) if "moves up" in line],
            ["Develop moves up to model-B · the tests failed twice"],
        )

    def test_the_task_blocks_for_a_person_past_the_last_model(self) -> None:
        store, project, task, roles = self._start(ladder=("model-A", "model-B"), escalate_after=2)
        handlers = {("developer", n): self._developer() for n in range(1, 8)}
        self._run(store, project, roles, handlers)
        self.assertEqual(
            self._models(store, task), ["model-A", "model-A", "model-B", "model-B"]
        )
        blocked = store.get_task(task.id)
        self.assertEqual(blocked.status, "blocked")
        self.assertEqual(
            blocked.blocked_reason, "Develop failed twice on model-B, the last of its models."
        )
        self.assertEqual(
            blocked.step_failures, {"develop": {"model-A": 2, "model-B": 2}}
        )

    def test_a_person_unblocking_starts_the_models_over(self) -> None:
        from foreman.mutations.tasks import TaskMutations

        store, project, task, roles = self._start(ladder=("model-A", "model-B"), escalate_after=1)
        self._run(store, project, roles, {("developer", n): self._developer() for n in range(1, 4)})
        self.assertEqual(store.get_task(task.id).status, "blocked")
        TaskMutations(store, via="cli").unblock_task(store.get_task(task.id))
        self.assertEqual(store.get_task(task.id).step_failures, {})

    def test_a_run_that_ended_without_a_result_counts_and_the_step_runs_again(self) -> None:
        store, project, task, roles = self._start(escalate_after=1)
        failed = AgentExecutionResult(outcome="error", detail="No completion after the retry.")
        self._run(
            store,
            project,
            roles,
            {
                ("developer", 1): self._developer(result=failed),
                ("developer", 2): self._developer(ready=True),
                ("code_reviewer", 1): lambda **_: AgentExecutionResult(outcome="approve", detail="ok"),
            },
        )
        self.assertEqual(self._models(store, task), ["model-A", "model-B"])
        self.assertIn(
            "Develop moves up to model-B · its run ended without a result once",
            self._lines(store, task),
        )

    def test_an_infrastructure_error_does_not_count(self) -> None:
        store, project, task, roles = self._start(escalate_after=1)
        failed = AgentExecutionResult(
            outcome="error", detail="git failed", failure_type="infrastructure"
        )
        self._run(store, project, roles, {("developer", 1): self._developer(result=failed)})
        stored = store.get_task(task.id)
        self.assertEqual(stored.step_failures, {})
        self.assertEqual(self._models(store, task), ["model-A"])
        self.assertEqual(stored.status, "blocked")

    def test_a_stop_does_not_count(self) -> None:
        store, project, task, roles = self._start(escalate_after=1)

        def stopped(**_):
            raise EngineCommandInterrupt("Stopped by a user")

        orchestrator = ForemanOrchestrator(
            store,
            roles=roles,
            workflows=self.workflows,
            agent_executor=ScriptedAgentExecutor({("developer", 1): stopped}),
        )
        try:
            orchestrator.run_project(project.id)
        except EngineCommandInterrupt:
            pass
        self.assertEqual(store.get_task(task.id).step_failures, {})

    def test_a_pinned_model_never_moves_up(self) -> None:
        store, project, task, roles = self._start(
            escalate_after=1, overrides={"models": {"develop": "model-A"}}
        )
        self._run(store, project, roles, {("developer", n): self._developer() for n in range(1, 4)})
        self.assertEqual(set(self._models(store, task)), {"model-A"})
        self.assertFalse([line for line in self._lines(store, task) if "moves up" in line])

    def test_a_step_starts_on_the_model_the_task_names(self) -> None:
        store, project, task, roles = self._start(overrides={"ladder_start": "model-B"})
        self._run(
            store,
            project,
            roles,
            {
                ("developer", 1): self._developer(ready=True),
                ("code_reviewer", 1): lambda **_: AgentExecutionResult(outcome="approve", detail="ok"),
            },
        )
        self.assertEqual(self._models(store, task), ["model-B"])

    def test_a_conflict_send_back_does_not_count(self) -> None:
        store, project, task, roles = self._start(escalate_after=1)
        orchestrator = ForemanOrchestrator(
            store, roles=roles, workflows=self.workflows, agent_executor=ScriptedAgentExecutor({})
        )
        runner = orchestrator.runner
        workflow = self.workflows["development"]
        merge = workflow.get_step("merge")
        for outcome in ("conflict", "updated", "failure"):
            self.assertIsNone(
                runner._failure_of_own_work(workflow, None, merge, "merge", outcome), outcome
            )
        gate = workflow.get_step("merge_approval")
        self.assertIsNone(runner._failure_of_own_work(workflow, None, gate, "merge_approval", "deny"))

    def test_a_review_that_sent_it_back_counts_against_the_step_it_sent_back(self) -> None:
        store, project, task, roles = self._start(escalate_after=1)
        deny = AgentExecutionResult(outcome="deny", detail="S2: criterion not met")
        self._run(
            store,
            project,
            roles,
            {
                ("developer", 1): self._developer(ready=True),
                ("code_reviewer", 1): lambda **_: deny,
                ("developer", 2): self._developer(),
                ("code_reviewer", 2): lambda **_: AgentExecutionResult(outcome="approve", detail="ok"),
            },
        )
        self.assertEqual(self._models(store, task), ["model-A", "model-B"])
        self.assertIn(
            "Develop moves up to model-B · the review sent it back once",
            self._lines(store, task),
        )
