"""Which model a step runs on, and reading a reviewer's decision."""

from __future__ import annotations
from dataclasses import replace
import unittest
from foreman.engine.output_contract import extract_completion_output, extract_decision_output
from foreman.models import Project, Task
from foreman.orchestrator import ForemanOrchestrator
from foreman.roles import default_roles_dir, load_roles



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

    def test_branch1_override_pinned_when_absent_from_ladder(self) -> None:
        task = self._task(executor_overrides={"models": {"develop": "PINNED"}})
        role = self._role(ladder=("A", "B"))
        for visit in (1, 2, 3):
            self.assertEqual(
                self._resolve(
                    task=task, role=role, project=self._project(),
                    step_id="develop", visit_count=visit,
                ),
                "PINNED",
            )

    def test_branch1_override_in_ladder_resumes_escalation(self) -> None:
        task = self._task(executor_overrides={"models": {"develop": "B"}})
        role = self._role(ladder=("A", "B", "C"))
        results = [
            self._resolve(
                task=task, role=role, project=self._project(),
                step_id="develop", visit_count=v,
            )
            for v in (1, 2, 3)
        ]
        self.assertEqual(results, ["B", "C", "C"])

    def test_branch2_ladder_indexed_by_visit(self) -> None:
        role = self._role(ladder=("A", "B", "C"))
        task = self._task()
        self.assertEqual(
            [
                self._resolve(
                    task=task, role=role, project=self._project(),
                    step_id="develop", visit_count=v,
                )
                for v in (1, 2, 3, 4)
            ],
            ["A", "B", "C", "C"],
        )

    def test_branch2_ladder_start_from_complexity_and_override(self) -> None:
        role = self._role(ladder=("A", "B", "C"))
        # complexity large → start index 1
        self.assertEqual(
            self._resolve(
                task=self._task(complexity="large"), role=role,
                project=self._project(), step_id="develop", visit_count=1,
            ),
            "B",
        )
        # explicit ladder_start override wins over complexity
        self.assertEqual(
            self._resolve(
                task=self._task(complexity="large", executor_overrides={"ladder_start": 2}),
                role=role, project=self._project(), step_id="develop", visit_count=1,
            ),
            "C",
        )

    def test_branch3_role_model(self) -> None:
        self.assertEqual(
            self._resolve(
                task=self._task(), role=self._role(model="role-model"),
                project=self._project(), step_id="develop", visit_count=1,
            ),
            "role-model",
        )

    def test_branch4_project_default(self) -> None:
        self.assertEqual(
            self._resolve(
                task=self._task(), role=self._role(),
                project=self._project(default_model="proj-default"),
                step_id="develop", visit_count=1,
            ),
            "proj-default",
        )

    def test_branch5_none_when_nothing_configured(self) -> None:
        self.assertIsNone(
            self._resolve(
                task=self._task(), role=self._role(),
                project=self._project(), step_id="develop", visit_count=1,
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
            "Completed the slice.\n\n**TASK_COMPLETE**",
        )

        self.assertEqual(outcome, "done")
        self.assertEqual(detail, "Completed the slice.")


if __name__ == "__main__":
    unittest.main()
