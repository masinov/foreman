"""Regression coverage for the sprint-53 workflow order and merge gate slice.

Every shipped workflow now tests before it reviews, so reviewers see real
test results, and every workflow ends in a ``merge_approval`` gate whose
policy (project setting or per-task override) decides whether a person must
authorize the merge or the engine may approve it with an audit record.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from foreman.models import Project, Sprint, Task, validate_executor_overrides
from foreman.orchestrator import ForemanOrchestrator
from foreman.roles import default_roles_dir, load_roles
from foreman.runner import AgentRunConfig
from foreman.runner.base import AgentEvent
from foreman.settings import ProjectSettings, SettingsError
from foreman.store import ForemanStore
from foreman.workflows import WorkflowLoadError, default_workflows_dir, load_workflow, load_workflows


def _shipped_workflows():
    roles = load_roles(default_roles_dir())
    return load_workflows(
        default_workflows_dir(),
        available_role_ids=set(roles),
        role_outcomes={rid: role.completion.outcomes for rid, role in roles.items()},
    )


class ShippedWorkflowShapeTests(unittest.TestCase):
    def test_every_workflow_tests_before_it_reviews(self) -> None:
        for workflow_id, workflow in _shipped_workflows().items():
            order = [step.id for step in workflow.steps]
            review_steps = [s.id for s in workflow.steps if s.role.endswith("_reviewer")]
            self.assertTrue(review_steps, workflow_id)
            self.assertLess(order.index("test"), min(order.index(r) for r in review_steps), workflow_id)
            develop_to = [t.to_step for t in workflow.transitions if t.from_step == "develop" and t.trigger == "completion:done"]
            self.assertEqual(develop_to, ["test"], workflow_id)

    def test_every_workflow_gates_the_merge_behind_a_policy(self) -> None:
        for workflow_id, workflow in _shipped_workflows().items():
            gate = workflow.get_step("merge_approval")
            self.assertIsNotNone(gate, workflow_id)
            self.assertEqual(gate.role, "_builtin:human_gate", workflow_id)
            self.assertEqual(gate.policy, "merge_approval", workflow_id)
            into_merge = {t.from_step for t in workflow.transitions if t.to_step == "merge"}
            self.assertEqual(into_merge, {"merge_approval"}, workflow_id)
            approve = workflow.find_transition("merge_approval", "approve")
            self.assertEqual(approve.to_step, "merge", workflow_id)
            deny = workflow.find_transition("merge_approval", "deny")
            self.assertEqual((deny.to_step, deny.carry_output), ("develop", True), workflow_id)

    def test_architect_plan_gate_is_governed_by_plan_approval(self) -> None:
        workflow = _shipped_workflows()["development_with_architect"]
        self.assertEqual(workflow.get_step("human_approval").policy, "plan_approval")

    def test_policy_is_only_valid_on_human_gate_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.toml"
            path.write_text(
                """
[workflow]
id = "bad"
name = "Bad"
methodology = "development"

[[steps]]
id = "develop"
role = "developer"
policy = "merge_approval"

[[steps]]
id = "done"
role = "_builtin:mark_done"

[[transitions]]
from = "develop"
trigger = "completion:done"
to = "done"
""",
                encoding="utf-8",
            )
            with self.assertRaises(WorkflowLoadError):
                load_workflow(path)


class GatePolicySettingsTests(unittest.TestCase):
    def test_defaults_and_validation(self) -> None:
        settings = ProjectSettings.from_raw({})
        self.assertEqual(settings.merge_approval, "auto")
        self.assertEqual(settings.plan_approval, "human")
        self.assertEqual(ProjectSettings.from_raw({"merge_approval": "human"}).merge_approval, "human")
        with self.assertRaises(SettingsError):
            ProjectSettings.from_raw({"merge_approval": "sometimes"})

    def test_per_task_gate_override_is_validated(self) -> None:
        self.assertEqual(
            validate_executor_overrides({"gates": {"merge_approval": "human"}}),
            {"gates": {"merge_approval": "human"}},
        )
        with self.assertRaises(ValueError):
            validate_executor_overrides({"gates": {"merge_approval": "maybe"}})
        with self.assertRaises(ValueError):
            validate_executor_overrides({"gates": {"deploy_approval": "human"}})


class _ScriptedRunner:
    def __init__(self, behaviours) -> None:
        self._behaviours = list(behaviours)

    def run(self, config: AgentRunConfig):
        behaviour = self._behaviours.pop(0)
        yield from behaviour(config)


def _reviewer_sees_tests_then_approves(config: AgentRunConfig):
    # The reviewer prompt now embeds engine evidence that includes the test run.
    assert "Completion Evidence" in config.prompt
    yield AgentEvent("agent.started", payload={"command": "fake"})
    yield AgentEvent("agent.message", payload={"text": "Tests passed and the diff is sound.\n\nAPPROVE", "phase": "result"})
    yield AgentEvent("agent.completed", payload={"session_id": "s"})


class MergeGateFlowTests(unittest.TestCase):
    def _workspace(self) -> tuple[Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        repo = root / "repo"
        repo.mkdir()
        for args in (("init",), ("checkout", "-b", "main"), ("config", "user.email", "t@example.com"), ("config", "user.name", "T")):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
        (repo / "README.md").write_text("# r\n", encoding="utf-8")
        (repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
        return repo, root / "foreman.db"

    def _developer(self, repo: Path):
        def developer_commits(config: AgentRunConfig):
            (repo / "feature.py").write_text("def feature():\n    return 'implemented'\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "feat: implement the feature"], cwd=repo, check=True, capture_output=True)
            yield AgentEvent("agent.started", payload={"command": "fake"})
            yield AgentEvent("agent.message", payload={"text": "Implemented the feature with tests.\nTASK_COMPLETE", "phase": "result"})
            yield AgentEvent("agent.completed", payload={"session_id": "s"})

        return developer_commits

    def _seed(self, store: ForemanStore, repo: Path, *, settings: dict | None = None, overrides: dict | None = None) -> tuple[Project, Task]:
        project = Project(
            id="p1", name="Gates", repo_path=str(repo), workflow_id="development", default_branch="main",
            settings={"task_selection_mode": "directed", "test_command": "true", "default_model": "m", **(settings or {})},
        )
        store.save_project(project)
        store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        task = Task(
            id="t1", sprint_id="s1", project_id="p1", title="Implement", status="todo",
            acceptance_criteria="Implemented the feature with tests.",
            executor_overrides=dict(overrides or {}),
        )
        store.save_task(task)
        return project, task

    def _steps(self, store: ForemanStore, task_id: str) -> list[str]:
        return [r.workflow_step for r in store.list_runs(task_id=task_id) if r.role_id != "_builtin:orchestrator"]

    def test_auto_policy_records_a_decision_and_merges(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project, task = self._seed(store, repo)
            orchestrator = ForemanOrchestrator(
                store, agent_runners={"claude_code": _ScriptedRunner([self._developer(repo), _reviewer_sees_tests_then_approves])}
            )
            result = orchestrator.run_project(project.id)
            self.assertEqual(result.stop_reason, "idle", store.get_task(task.id).blocked_reason)
            self.assertEqual(store.get_task(task.id).status, "done")
            self.assertEqual(
                self._steps(store, task.id),
                ["develop", "test", "review", "merge_approval", "merge", "done"],
            )
            gate_run = next(r for r in store.list_runs(task_id=task.id) if r.workflow_step == "merge_approval")
            self.assertEqual(gate_run.outcome, "approve")
            decisions = store._connection.execute(
                "SELECT decided_by, decision, workflow_step FROM human_gate_decisions"
            ).fetchall()
            self.assertEqual([tuple(row) for row in decisions], [("policy:merge_approval", "approve", "merge_approval")])
            auto_events = [e for e in store.list_events(run_id=gate_run.id) if e.event_type == "workflow.gate_auto_approved"]
            self.assertEqual(len(auto_events), 1)

    def test_human_policy_pauses_before_merge_and_resumes_on_approval(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project, task = self._seed(store, repo, settings={"merge_approval": "human"})
            orchestrator = ForemanOrchestrator(
                store, agent_runners={"claude_code": _ScriptedRunner([self._developer(repo), _reviewer_sees_tests_then_approves])}
            )
            result = orchestrator.run_project(project.id)
            self.assertEqual(result.stop_reason, "blocked")
            paused = store.get_task(task.id)
            self.assertEqual(paused.status, "blocked")
            self.assertEqual(paused.workflow_current_step, "merge_approval")
            self.assertEqual(paused.blocked_reason, "Awaiting human approval")
            self.assertEqual(self._steps(store, task.id), ["develop", "test", "review", "merge_approval"])

            resumed = orchestrator.resume_human_gate(task.id, outcome="approve", note="verified locally")
            self.assertFalse(resumed.deferred)
            self.assertEqual(store.get_task(task.id).status, "done")
            decisions = store._connection.execute(
                "SELECT decided_by, decision FROM human_gate_decisions"
            ).fetchall()
            self.assertEqual([tuple(row) for row in decisions], [("human", "approve")])

    def test_per_task_override_requires_a_human_even_when_the_project_is_auto(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project, task = self._seed(store, repo, overrides={"gates": {"merge_approval": "human"}})
            orchestrator = ForemanOrchestrator(
                store, agent_runners={"claude_code": _ScriptedRunner([self._developer(repo), _reviewer_sees_tests_then_approves])}
            )
            result = orchestrator.run_project(project.id)
            self.assertEqual(result.stop_reason, "blocked")
            self.assertEqual(store.get_task(task.id).workflow_current_step, "merge_approval")

    def test_failing_tests_return_to_develop_before_any_review(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project, task = self._seed(store, repo, settings={"test_command": "false", "max_step_visits": 1})
            orchestrator = ForemanOrchestrator(
                store, agent_runners={"claude_code": _ScriptedRunner([self._developer(repo), self._developer(repo)])}
            )
            orchestrator.run_project(project.id)
            steps = self._steps(store, task.id)
            self.assertEqual(steps[:2], ["develop", "test"])
            self.assertNotIn("review", steps)
            self.assertEqual(store.get_task(task.id).status, "blocked")


class GateOverrideCliTests(unittest.TestCase):
    def test_task_override_gate_flag_sets_and_clears_the_policy(self) -> None:
        from foreman.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "foreman.db")
            with ForemanStore(db_path) as store:
                store.initialize()
                project = Project(id="p1", name="Gates", repo_path=tmp, workflow_id="development")
                store.save_project(project)
                store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
                store.save_task(Task(id="t1", sprint_id="s1", project_id="p1", title="T"))

            self.assertEqual(main(["task", "override", "t1", "--gate", "merge_approval=human", "--db", db_path]), 0)
            with ForemanStore(db_path) as store:
                self.assertEqual(store.get_task("t1").executor_overrides, {"gates": {"merge_approval": "human"}})

            self.assertEqual(main(["task", "override", "t1", "--gate", "merge_approval=sometimes", "--db", db_path]), 1)
            self.assertEqual(main(["task", "override", "t1", "--gate", "merge_approval=", "--db", db_path]), 0)
            with ForemanStore(db_path) as store:
                self.assertEqual(store.get_task("t1").executor_overrides, {})


if __name__ == "__main__":
    unittest.main()
