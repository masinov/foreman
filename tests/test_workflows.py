"""Tests for declarative workflow loading and validation."""

from __future__ import annotations

from pathlib import Path
import tempfile
import textwrap
import unittest

from foreman.roles import default_roles_dir, load_roles
from foreman.workflows import (
    WorkflowLoadError,
    default_workflows_dir,
    load_workflows,
)


class WorkflowLoaderTests(unittest.TestCase):
    """Verify Foreman's workflow loader behavior."""

    def create_directory(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def test_loads_shipped_workflows_and_resolves_transitions(self) -> None:
        role_ids = set(load_roles(default_roles_dir()))
        workflows = load_workflows(default_workflows_dir(), available_role_ids=role_ids)

        self.assertEqual(
            set(workflows),
            {
                "development",
                "development_secure",
                "development_tiered",
            },
        )
        tiered = workflows["development_tiered"]
        self.assertEqual(tiered.entry_step, "develop")
        self.assertEqual(
            [s.id for s in tiered.steps],
            ["develop", "test", "triage", "review", "merge_approval", "merge", "done"],
        )
        escalate = tiered.find_transition("triage", "escalate")
        self.assertIsNotNone(escalate)
        self.assertEqual(escalate.to_step, "review")
        development = workflows["development"]
        self.assertEqual(development.entry_step, "develop")
        self.assertEqual(len(development.steps), 6)
        self.assertEqual(len(development.gates), 2)
        deny_transition = development.find_transition("review", "deny")
        self.assertIsNotNone(deny_transition)
        self.assertEqual(deny_transition.to_step, "develop")
        self.assertTrue(deny_transition.carry_output)
        self.assertEqual(
            development.find_transition_by_trigger("merge", "completion:success").to_step,
            "done",
        )

    def test_rejects_transition_targets_that_do_not_exist(self) -> None:
        workflows_dir = self.create_directory()
        invalid_workflow = textwrap.dedent(
            """
            [workflow]
            id = "invalid_target"
            name = "Invalid Target"
            methodology = "development"

            [[steps]]
            id = "develop"
            role = "developer"

            [[transitions]]
            from = "develop"
            trigger = "completion:done"
            to = "missing_step"
            """
        ).strip()
        (workflows_dir / "invalid.toml").write_text(invalid_workflow, encoding="utf-8")

        with self.assertRaises(WorkflowLoadError):
            load_workflows(workflows_dir, available_role_ids={"developer"})

    def test_rejects_unknown_roles_when_role_set_is_provided(self) -> None:
        workflows_dir = self.create_directory()
        invalid_workflow = textwrap.dedent(
            """
            [workflow]
            id = "unknown_role"
            name = "Unknown Role"
            methodology = "development"

            [[steps]]
            id = "develop"
            role = "missing_role"
            """
        ).strip()
        (workflows_dir / "invalid.toml").write_text(invalid_workflow, encoding="utf-8")

        with self.assertRaises(WorkflowLoadError):
            load_workflows(workflows_dir, available_role_ids={"developer"})

    def test_rejects_invalid_outcome_for_triage_reviewer(self) -> None:
        workflows_dir = self.create_directory()
        # triage_reviewer may emit approve/deny/escalate, not steer.
        broken = textwrap.dedent(
            """
            [workflow]
            id = "broken_tiered"
            name = "Broken Tiered"
            methodology = "development"

            [[steps]]
            id = "develop"
            role = "developer"

            [[steps]]
            id = "triage"
            role = "triage_reviewer"

            [[steps]]
            id = "done"
            role = "_builtin:mark_done"

            [[transitions]]
            from = "develop"
            trigger = "completion:done"
            to = "triage"

            [[transitions]]
            from = "triage"
            trigger = "completion:steer"
            to = "done"
            """
        ).strip()
        (workflows_dir / "broken.toml").write_text(broken, encoding="utf-8")

        with self.assertRaises(WorkflowLoadError):
            load_workflows(
                workflows_dir,
                available_role_ids={"developer", "triage_reviewer"},
                role_outcomes={
                    "developer": ("done", "blocked", "error"),
                    "triage_reviewer": ("approve", "deny", "escalate"),
                },
            )


if __name__ == "__main__":
    unittest.main()


class SoundnessTests(unittest.TestCase):
    """A workflow is refused unless a task can get through it properly."""

    def setUp(self) -> None:
        from foreman.roles import load_roles

        self.roles = load_roles()
        self.outcomes = {role_id: role.completion.outcomes for role_id, role in self.roles.items()}

    def load(self, steps: list[tuple[str, str]], routes: list[tuple[str, str, str]]):
        from foreman.workflows import load_workflow_text

        text = '[workflow]\nid = "x"\nname = "X"\nmethodology = "development"\n'
        for step_id, role in steps:
            text += f'[[steps]]\nid = "{step_id}"\nrole = "{role}"\n'
        for source, outcome, target in routes:
            text += f'[[transitions]]\nfrom = "{source}"\ntrigger = "completion:{outcome}"\nto = "{target}"\n'
        return load_workflow_text(
            text, "x", available_role_ids=set(self.roles), role_outcomes=self.outcomes
        )

    def refused(self, message: str, steps, routes) -> None:
        with self.assertRaisesRegex(WorkflowLoadError, message):
            self.load(steps, routes)

    SOUND_STEPS = [
        ("develop", "developer"),
        ("test", "_builtin:run_tests"),
        ("merge", "_builtin:merge"),
        ("done", "_builtin:mark_done"),
    ]
    SOUND_ROUTES = [
        ("develop", "done", "test"),
        ("test", "success", "merge"),
        ("test", "failure", "develop"),
        ("merge", "success", "done"),
    ]

    def test_the_shortest_sound_workflow_loads(self) -> None:
        self.assertEqual(self.load(self.SOUND_STEPS, self.SOUND_ROUTES).entry_step, "develop")

    def test_a_step_nothing_leads_to(self) -> None:
        self.refused(
            "Step 'orphan' is never reached",
            [*self.SOUND_STEPS, ("orphan", "code_reviewer")],
            [*self.SOUND_ROUTES, ("orphan", "approve", "merge")],
        )

    def test_no_step_marks_the_task_done(self) -> None:
        self.refused(
            "No step marks the task done",
            [("develop", "developer"), ("review", "code_reviewer")],
            [("develop", "done", "review"), ("review", "approve", "develop")],
        )

    def test_a_step_a_task_can_never_leave_for_the_end(self) -> None:
        self.refused(
            "From step 'limbo' a task can never reach the end",
            [*self.SOUND_STEPS, ("limbo", "code_reviewer"), ("limbo2", "developer")],
            [*self.SOUND_ROUTES, ("merge", "failure", "limbo"), ("limbo", "deny", "limbo2"), ("limbo2", "done", "limbo")],
        )

    def test_done_without_a_merge(self) -> None:
        self.refused(
            r"reach 'done' without a successful merge \(develop -> test -> done\)",
            [("develop", "developer"), ("test", "_builtin:run_tests"), ("done", "_builtin:mark_done")],
            [("develop", "done", "test"), ("test", "success", "done"), ("test", "failure", "develop")],
        )

    def test_a_merge_without_the_tests_passing_first(self) -> None:
        self.refused(
            r"merge step 'merge' from 'develop' without the tests passing in between \(develop -> merge\)",
            [("develop", "developer"), ("merge", "_builtin:merge"), ("done", "_builtin:mark_done")],
            [("develop", "done", "merge"), ("merge", "success", "done")],
        )

    def test_a_change_after_the_tests_that_is_merged_untested(self) -> None:
        # The tests pass once, the reviewer sends it to a second developer, and
        # that developer's change goes back to review and on to the merge.
        self.refused(
            r"from 'fix' without the tests passing in between \(fix -> review -> merge\)",
            [
                ("develop", "developer"),
                ("test", "_builtin:run_tests"),
                ("review", "code_reviewer"),
                ("fix", "developer"),
                ("merge", "_builtin:merge"),
                ("done", "_builtin:mark_done"),
            ],
            [
                ("develop", "done", "test"),
                ("test", "success", "review"),
                ("review", "approve", "merge"),
                ("review", "deny", "fix"),
                ("fix", "done", "review"),
                ("merge", "success", "done"),
            ],
        )

    def test_a_first_step_that_cannot_start_a_task(self) -> None:
        self.refused(
            "A task starts at the first step, 'done'",
            [("done", "_builtin:mark_done"), *self.SOUND_STEPS[:3]],
            self.SOUND_ROUTES,
        )

    def test_every_shipped_workflow_is_sound(self) -> None:
        from foreman.workflows import load_workflows

        loaded = load_workflows(available_role_ids=set(self.roles), role_outcomes=self.outcomes)
        self.assertEqual(sorted(loaded), ["development", "development_secure", "development_tiered"])

