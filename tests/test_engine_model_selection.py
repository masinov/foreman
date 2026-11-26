"""Which model a step runs on, and reading a reviewer's decision."""

from __future__ import annotations
from dataclasses import replace
import unittest
from engine_support import DEV_REPORT
from foreman.engine.output_contract import extract_completion_output, extract_decision_output
from foreman.domain.models import Project, Task
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.definitions.roles import default_roles_dir, load_roles



class ResolveStepModelTests(unittest.TestCase):
    """Unit coverage for the pure per-step model resolution function."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.roles = load_roles(default_roles_dir())

    def _role(self, *, model: str = "", ladder: tuple[str, ...] = ()):
        base = self.roles["developer"]
        return replace(base, agent=replace(base.agent, model=model, model_ladder=ladder))

    def _project(self, *, default_model: str = "") -> Project:
        return Project(
            id="p",
            name="P",
            repo_path="/x",
            workflow_id="development",
            settings={"default_model": default_model} if default_model else {},
        )

    def _task(self, **kw) -> Task:
        return Task(id="t", sprint_id="s", project_id="p", title="T", **kw)

    def _resolve(self, **kw) -> str | None:
        from foreman.engine.model_selection import resolve_step_model

        return resolve_step_model(**kw)

    def _models(self, task, role, step_id="develop"):
        from foreman.engine.model_selection import resolve_step_model_selection

        return resolve_step_model_selection(
            task=task, role=role, project=self._project(), step_id=step_id
        )

    def test_a_pinned_model_never_moves_up_even_when_in_the_ladder(self) -> None:
        role = self._role(ladder=("A", "B", "C"))
        for pinned in ("PINNED", "B"):
            task = self._task(
                executor_overrides={"models": {"develop": pinned}},
                step_failures={"develop": {pinned: 9}},
            )
            selection = self._models(task, role)
            self.assertEqual((selection.model, selection.source), (pinned, "override"))
            self.assertFalse(selection.exhausted)

    def test_visits_do_not_move_a_step_up(self) -> None:
        role = self._role(ladder=("A", "B", "C"))
        task = self._task(step_visit_counts={"develop": 7})
        self.assertEqual(self._models(task, role).model, "A")

    def test_a_step_moves_up_after_escalate_after_failures_on_a_model(self) -> None:
        role = self._role(ladder=("A", "B", "C"))
        one = self._task(step_failures={"develop": {"A": 1}})
        two = self._task(step_failures={"develop": {"A": 2}})
        both = self._task(step_failures={"develop": {"A": 2, "B": 1}})
        self.assertEqual(self._models(one, role).model, "A")
        self.assertEqual(self._models(two, role).model, "B")
        self.assertEqual(self._models(two, role).moves_up, 1)
        self.assertEqual(self._models(both, role).model, "B")
        self.assertEqual(self._models(both, role).failures, 1)

    def test_escalate_after_is_the_roles_to_set(self) -> None:
        base = self._role(ladder=("A", "B"))
        role = replace(base, agent=replace(base.agent, escalate_after=1))
        task = self._task(step_failures={"develop": {"A": 1}})
        self.assertEqual(self._models(task, role).model, "B")

    def test_failures_of_another_step_do_not_count(self) -> None:
        role = self._role(ladder=("A", "B"))
        task = self._task(step_failures={"review": {"A": 5}})
        self.assertEqual(self._models(task, role).model, "A")

    def test_past_the_last_model_the_step_is_exhausted(self) -> None:
        role = self._role(ladder=("A", "B"))
        task = self._task(step_failures={"develop": {"A": 2, "B": 2}})
        selection = self._models(task, role)
        self.assertEqual((selection.model, selection.exhausted, selection.failures), ("B", True, 2))

    def test_one_model_never_moves_up_and_is_never_exhausted(self) -> None:
        role = self._role(ladder=("A",))
        task = self._task(step_failures={"develop": {"A": 9}})
        selection = self._models(task, role)
        self.assertEqual((selection.model, selection.exhausted), ("A", False))

    def test_a_step_starts_on_the_model_the_task_names(self) -> None:
        role = self._role(ladder=("A", "B", "C"))
        task = self._task(executor_overrides={"ladder_start": "B"})
        self.assertEqual(self._models(task, role).model, "B")
        # It still moves up from there, and moves are counted from where it started.
        task = self._task(
            executor_overrides={"ladder_start": "B"}, step_failures={"develop": {"B": 2}}
        )
        selection = self._models(task, role)
        self.assertEqual((selection.model, selection.moves_up), ("C", 1))
        # A model this role does not list leaves the step on its first.
        task = self._task(executor_overrides={"ladder_start": "Z"})
        self.assertEqual(self._models(task, role).model, "A")
        # A number is still read as a position.
        task = self._task(executor_overrides={"ladder_start": 2})
        self.assertEqual(self._models(task, role).model, "C")

    def test_the_size_label_may_still_choose_the_first_model(self) -> None:
        role = self._role(ladder=("A", "B", "C"))
        self.assertEqual(self._models(self._task(complexity="large"), role).model, "B")
        task = self._task(complexity="large", executor_overrides={"ladder_start": "C"})
        self.assertEqual(self._models(task, role).model, "C")

    def test_branch3_role_model(self) -> None:
        self.assertEqual(
            self._resolve(
                task=self._task(), role=self._role(model="role-model"),
                project=self._project(), step_id="develop",
            ),
            "role-model",
        )

    def test_branch4_project_default(self) -> None:
        self.assertEqual(
            self._resolve(
                task=self._task(), role=self._role(),
                project=self._project(default_model="proj-default"),
                step_id="develop",
            ),
            "proj-default",
        )

    def test_branch5_none_when_nothing_configured(self) -> None:
        self.assertIsNone(
            self._resolve(
                task=self._task(), role=self._role(),
                project=self._project(), step_id="develop",
            )
        )


class DecisionExtractionTests(unittest.TestCase):
    """Unit coverage for reviewer decision parsing."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.roles = load_roles(default_roles_dir())
        cls.orchestrator = object.__new__(ForemanOrchestrator)

    def test_extract_decision_output_accepts_preamble_and_markdown_wrapped_verdict(self) -> None:
        outcome, detail = extract_decision_output(
            "I verified the changes.\n\nEverything checks out.\n\n**APPROVE**"
        )

        self.assertEqual(outcome, "approve")
        self.assertEqual(detail, "APPROVE")

    def test_extract_decision_output_accepts_trailing_deny_reason(self) -> None:
        outcome, detail = extract_decision_output(
            "I found one issue.\n\n- DENY: add the missing migration test"
        )

        self.assertEqual(outcome, "deny")
        self.assertEqual(detail, "add the missing migration test")

    def test_extract_decision_output_recognizes_escalate(self) -> None:
        self.assertEqual(extract_decision_output("ESCALATE")[0], "escalate")
        outcome, detail = extract_decision_output(
            "Looks risky.\n\nESCALATE: touches the auth module, needs senior review"
        )
        self.assertEqual(outcome, "escalate")
        self.assertEqual(detail, "touches the auth module, needs senior review")

    def test_extract_completion_output_accepts_markdown_wrapped_marker(self) -> None:
        role = self.roles["developer"]

        outcome, detail = extract_completion_output(
            role,
            "Completed the slice.\n\n" + DEV_REPORT + "\n**TASK_COMPLETE**",
        )

        self.assertEqual(outcome, "done")
        self.assertEqual(detail, "Completed the slice.")


if __name__ == "__main__":
    unittest.main()
