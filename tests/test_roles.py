"""Tests for declarative role loading and prompt rendering."""

from __future__ import annotations

from pathlib import Path
import tempfile
import textwrap
import unittest

from foreman.roles import (
    PromptRenderError,
    RoleLoadError,
    default_roles_dir,
    load_roles,
)


class RoleLoaderTests(unittest.TestCase):
    """Verify Foreman's role loader behavior."""

    def create_directory(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def test_loads_shipped_roles(self) -> None:
        roles = load_roles(default_roles_dir())

        self.assertEqual(
            set(roles),
            {"architect", "code_reviewer", "developer", "security_reviewer"},
        )
        self.assertTrue(roles["developer"].agent.session_persistence)
        self.assertEqual(roles["code_reviewer"].completion.max_cost_usd, 2.0)
        self.assertTrue(roles["architect"].completion.output.extract_json)

    def test_render_prompt_injects_completion_marker_and_signal_docs(self) -> None:
        developer = load_roles(default_roles_dir())["developer"]

        prompt = developer.render_prompt(
            {
                "task_title": "Add store loader",
                "task_type": "feature",
                "branch_name": "feat/example",
                "task_description": "Read config from disk.",
                "acceptance_criteria": "Loader reads TOML and tests pass.",
                "sprint_context": "Sprint 1",
                "project_status": "On track",
                "repo_instructions": "Follow AGENTS.md",
                "spec_path": "docs/specs/engine-design-v3.md",
                "previous_feedback": "Address the reviewer note.",
            }
        )

        self.assertIn("## Task: Add store loader", prompt)
        self.assertIn("Branch: feat/example", prompt)
        self.assertIn("`TASK_COMPLETE`", prompt)
        self.assertIn("FOREMAN_SIGNAL:", prompt)
        self.assertIn("Address the reviewer note.", prompt)

    def test_duplicate_role_ids_are_rejected(self) -> None:
        roles_dir = self.create_directory()
        role_template = textwrap.dedent(
            """
            [role]
            id = "duplicate"
            name = "Duplicate"
            description = "Used for duplicate-id validation"

            [agent]
            backend = "claude_code"
            model = ""
            session_persistence = false
            permission_mode = "bypassPermissions"

            [agent.tools]
            allowed = []
            disallowed = []

            [prompt]
            template = "Hello {task_title}"

            [completion]
            marker = "TASK_COMPLETE"
            timeout_minutes = 5
            max_cost_usd = 1.0
            """
        ).strip()
        (roles_dir / "one.toml").write_text(role_template, encoding="utf-8")
        (roles_dir / "two.toml").write_text(role_template, encoding="utf-8")

        with self.assertRaises(RoleLoadError):
            load_roles(roles_dir)

    def test_render_prompt_wraps_invalid_templates(self) -> None:
        roles_dir = self.create_directory()
        invalid_role = textwrap.dedent(
            """
            [role]
            id = "invalid_template"
            name = "Invalid Template"
            description = "Used for render failure validation"

            [agent]
            backend = "claude_code"
            model = ""
            session_persistence = false
            permission_mode = "bypassPermissions"

            [agent.tools]
            allowed = []
            disallowed = []

            [prompt]
            template = "Hello {task_title!z}"

            [completion]
            marker = "TASK_COMPLETE"
            timeout_minutes = 5
            max_cost_usd = 1.0
            """
        ).strip()
        role_path = roles_dir / "invalid.toml"
        role_path.write_text(invalid_role, encoding="utf-8")
        role = load_roles(roles_dir)["invalid_template"]

        with self.assertRaises(PromptRenderError):
            role.render_prompt({"task_title": "Broken"})


if __name__ == "__main__":
    unittest.main()
