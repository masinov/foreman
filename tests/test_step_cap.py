"""A step can be capped with ``max_visits`` (ADR-0041 section 3)."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from foreman.definitions.workflows import WorkflowLoadError, load_workflow
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.engine.results import AgentExecutionResult
from foreman.mutations.tasks import TaskMutations
from foreman.store import ForemanStore

from engine_support import OrchestratorTestCase, ScriptedAgentExecutor

_WORKFLOW = """
[workflow]
id = "w"
name = "W"
methodology = "m"

[[steps]]
id = "develop"
role = "developer"
{extra}

[[transitions]]
from = "develop"
trigger = "completion:done"
to = "test"

[[transitions]]
from = "test"
trigger = "completion:success"
to = "merge"

[[steps]]
id = "test"
role = "_builtin:run_tests"

[[transitions]]
from = "merge"
trigger = "completion:success"
to = "done"

[[steps]]
id = "merge"
role = "_builtin:merge"

[[steps]]
id = "done"
role = "_builtin:mark_done"
"""


class ParseTests(unittest.TestCase):
    def _load(self, extra: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "w.toml"
            path.write_text(_WORKFLOW.format(extra=extra), encoding="utf-8")
            return load_workflow(path)

    def test_max_visits_is_parsed(self) -> None:
        self.assertEqual(self._load("max_visits = 3").steps[0].max_visits, 3)

    def test_a_step_without_a_cap_has_none(self) -> None:
        self.assertIsNone(self._load("").steps[0].max_visits)

    def test_only_a_positive_integer_is_accepted(self) -> None:
        for bad in ("0", "-1", "1.5", '"3"', "true"):
            with self.subTest(bad=bad), self.assertRaises(WorkflowLoadError):
                self._load(f"max_visits = {bad}")


class _CapCase(OrchestratorTestCase):
    def _start(self, *, cap: int | None, settings: dict | None = None):
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        store.initialize()
        self.addCleanup(store.close)
        project, _, task = self.seed_project(
            store, repo_path=repo_path, test_command="test -f ready.txt"
        )
        project.settings["completion_guard_enabled"] = False
        project.settings.update(settings or {})
        store.save_project(project)
        base = self.workflows["development"]
        steps = tuple(
            replace(step, max_visits=cap) if step.id == "review" else step
            for step in base.steps
        )
        self.workflow_map = {**self.workflows, "development": replace(base, steps=steps)}
        self.repo_path = repo_path
        return store, project, task

    def _developer(self, *, task, prompt, carried_output):
        tree = self.work_dir(task, self.repo_path)
        self.write_text(tree / "ready.txt", "x\n")
        self.write_text(tree / f"f{len(list(tree.glob('f*.txt')))}.txt", "x\n")
        self.commit_all(tree, "feat: work")
        return AgentExecutionResult(outcome="done", detail="Done.")

    def _run(self, store, project, reviews):
        handlers = {("developer", n): self._developer for n in range(1, 12)}
        handlers.update(
            {
                ("code_reviewer", n): (lambda outcome: lambda **_: AgentExecutionResult(
                    outcome=outcome, detail=outcome
                ))(outcome)
                for n, outcome in enumerate(reviews, 1)
            }
        )
        executor = ScriptedAgentExecutor(handlers)
        ForemanOrchestrator(
            store, roles=self.roles, workflows=self.workflow_map, agent_executor=executor
        ).run_project(project.id)

    def _reviews(self, store, task):
        return [
            r for r in store.list_runs(task_id=task.id) if r.workflow_step == "review"
            and r.role_id == "code_reviewer"
        ]


class StepCapTests(_CapCase):
    def test_a_review_capped_at_two_blocks_before_it_runs_a_third_time(self) -> None:
        store, project, task = self._start(cap=2)
        self._run(store, project, ["deny", "deny", "approve"])
        blocked = store.get_task(task.id)
        self.assertEqual(blocked.status, "blocked")
        self.assertEqual(blocked.blocked_reason, "Review ran twice, its cap: a person decides.")
        self.assertEqual(len(self._reviews(store, task)), 2)
        self.assertEqual(blocked.step_visit_counts["review"], 2)
        self.assertEqual(blocked.workflow_current_step, "review")
        events = [e.event_type for e in store.list_events(task_id=task.id)]
        self.assertIn("workflow.step_cap", events)

    def test_unblocking_runs_the_step_once_more_and_keeps_the_count(self) -> None:
        store, project, task = self._start(cap=2)
        self._run(store, project, ["deny", "deny", "deny", "deny"])
        fake = SimpleNamespace(workflows=self.workflow_map)
        with mock.patch("foreman.definitions.gate_steps.project_definitions", return_value=fake):
            TaskMutations(store, via="cli").unblock_task(store.get_task(task.id))
            resumed = store.get_task(task.id)
            self.assertEqual(resumed.status, "todo")
            self.assertEqual(resumed.workflow_current_step, "review")
            self.assertEqual(resumed.step_visit_counts["review"], 1)
            self.assertEqual(resumed.step_visit_counts["develop"], 3)
            self._run(store, project, ["deny", "deny"])
        # One more review ran (the third), then the cap held again.
        self.assertEqual(len(self._reviews(store, task)), 3)
        again = store.get_task(task.id)
        self.assertEqual(again.status, "blocked")
        self.assertIn("cap", again.blocked_reason)

    def test_reset_visits_starts_every_count_over(self) -> None:
        store, project, task = self._start(cap=2)
        self._run(store, project, ["deny", "deny"])
        fake = SimpleNamespace(workflows=self.workflow_map)
        with mock.patch("foreman.definitions.gate_steps.project_definitions", return_value=fake):
            TaskMutations(store, via="cli").unblock_task(
                store.get_task(task.id), reset_visits=True
            )
        resumed = store.get_task(task.id)
        self.assertEqual(resumed.step_visit_counts, {})
        self.assertEqual(resumed.workflow_current_step, "review")

    def test_max_step_visits_still_stops_a_step_without_a_cap(self) -> None:
        store, project, task = self._start(cap=None, settings={"max_step_visits": 2})
        self._run(store, project, ["deny"] * 6)
        blocked = store.get_task(task.id)
        self.assertEqual(blocked.status, "blocked")
        self.assertIn("Stuck in a loop", blocked.blocked_reason)
        events = [e.event_type for e in store.list_events(task_id=task.id)]
        self.assertIn("workflow.loop_limit", events)
        self.assertNotIn("workflow.step_cap", events)


if __name__ == "__main__":
    unittest.main()


class CapReviewFixTests(_CapCase):
    """Sprint 69 review of FOR-109."""

    def test_a_cap_that_blocks_a_resumed_task_keeps_its_resume_point(self) -> None:
        store, project, task = self._start(cap=2)
        waiting = store.get_task(task.id)
        waiting.workflow_current_step = "review"
        waiting.step_visit_counts = {"develop": 2, "test": 2, "review": 2}
        store.save_task(waiting)
        self._run(store, project, [])
        blocked = store.get_task(task.id)
        self.assertEqual(blocked.status, "blocked")
        self.assertIn("its cap", blocked.blocked_reason)
        self.assertEqual(blocked.workflow_current_step, "review")
        fake = SimpleNamespace(workflows=self.workflow_map)
        with mock.patch("foreman.definitions.gate_steps.project_definitions", return_value=fake):
            TaskMutations(store, via="cli").unblock_task(blocked)
        resumed = store.get_task(task.id)
        self.assertEqual(resumed.workflow_current_step, "review")
        self.assertEqual(resumed.step_visit_counts["review"], 1)

    def test_another_block_at_a_capped_step_is_not_taken_for_the_cap(self) -> None:
        from foreman.definitions.gate_steps import capped_step_block

        store, project, task = self._start(cap=2)
        other = store.get_task(task.id)
        other.status = "blocked"
        other.blocked_reason = "The run's cost limit was reached."
        other.workflow_current_step = "review"
        other.step_visit_counts = {"review": 2}
        store.save_task(other)
        fake = SimpleNamespace(workflows=self.workflow_map)
        with mock.patch("foreman.definitions.gate_steps.project_definitions", return_value=fake):
            self.assertIsNone(capped_step_block(store, project, store.get_task(task.id)))
            # Capped for real, it is the cap's; blocked again for another
            # reason afterwards, it is not.
            self._run_to_cap(store, project, task)
            capped = store.get_task(task.id)
            self.assertEqual(capped_step_block(store, project, capped), "review")
            capped.blocked_reason = "Blocked by a person."
            store.save_task(capped)
            self.assertIsNone(capped_step_block(store, project, store.get_task(task.id)))

    def _run_to_cap(self, store, project, task) -> None:
        reset = store.get_task(task.id)
        reset.status = "todo"
        reset.blocked_reason = None
        reset.workflow_current_step = None
        reset.step_visit_counts = {}
        store.save_task(reset)
        self._run(store, project, ["deny", "deny", "deny"])

    def test_model_ladder_retries_do_not_use_up_the_cap(self) -> None:
        store, project, task = self._start(cap=1)
        # The room a ladder of three models gives a step.
        with mock.patch(
            "foreman.engine.workflow_runner.transitions.Transitions._ladder_visits",
            return_value=2,
        ):
            self._run(store, project, ["deny", "deny", "approve"])
        # Capped at 1, with room for two ladder failures: three reviews ran.
        self.assertEqual(len(self._reviews(store, task)), 3)


class GateCapTests(unittest.TestCase):
    def test_a_human_gate_takes_no_max_visits(self) -> None:
        text = _WORKFLOW.format(extra="") + """
[[steps]]
id = "gate"
role = "_builtin:human_gate"
max_visits = 1
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "w.toml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(WorkflowLoadError, "human gate takes no max_visits"):
                load_workflow(path)
