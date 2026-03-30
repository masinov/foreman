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
                "development_with_architect",
            },
        )
        development = workflows["development"]
        self.assertEqual(development.entry_step, "develop")
        self.assertEqual(len(development.steps), 5)
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


if __name__ == "__main__":
    unittest.main()
