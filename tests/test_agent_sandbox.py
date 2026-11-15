"""The shipped roles' tool sets, and what a project may pass to its agents (ADR-0023)."""

from __future__ import annotations

import os
from unittest.mock import patch
import unittest

from foreman.roles import default_roles_dir, load_roles
from foreman.orchestrator import ForemanOrchestrator
from foreman.runner.base import AgentRunConfig
from foreman.settings import HOST_LEVEL_SETTINGS, ProjectSettings, SettingsError
from foreman.store import ForemanStore

from engine_support import OrchestratorTestCase, ScriptedNativeRunner

READING_ONLY = ("Read", "Grep", "Glob")
WRITING = {"Bash", "Write", "Edit", "NotebookEdit"}


class ShippedRoleToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.roles = load_roles(default_roles_dir())

    def test_the_reviewers_that_read_can_do_nothing_else(self) -> None:
        for role_id in ("code_reviewer", "security_reviewer"):
            self.assertEqual(self.roles[role_id].agent.tools.allowed, READING_ONLY, role_id)

    def test_no_reviewer_can_write_or_run_commands(self) -> None:
        for role_id, role in self.roles.items():
            if not role.completion.output.extract_decision:
                continue
            tools = role.agent.tools
            usable = set(tools.allowed) - set(tools.disallowed) if tools.allowed else None
            if usable is not None:
                self.assertFalse(usable & WRITING, role_id)
            else:
                self.assertTrue(WRITING <= set(tools.disallowed), role_id)


class PassthroughSettingTests(unittest.TestCase):
    def test_it_is_host_level_and_empty_by_default(self) -> None:
        self.assertIn("agent_env_passthrough", HOST_LEVEL_SETTINGS)
        self.assertEqual(ProjectSettings.from_raw({}).agent_env_passthrough, ())

    def test_it_takes_names_as_a_list_or_comma_separated(self) -> None:
        self.assertEqual(
            ProjectSettings.from_raw({"agent_env_passthrough": ["A", "B_2", "A"]}).agent_env_passthrough,
            ("A", "B_2"),
        )
        self.assertEqual(
            ProjectSettings.from_raw({"agent_env_passthrough": "A, B_2"}).agent_env_passthrough,
            ("A", "B_2"),
        )

    def test_it_refuses_what_is_not_a_variable_name(self) -> None:
        for bad in (["A=B"], ["2A"], ["A B"], 7):
            with self.assertRaises(SettingsError):
                ProjectSettings.from_raw({"agent_env_passthrough": bad})


class EngineSandboxTests(OrchestratorTestCase):
    def test_the_runner_is_given_the_roles_allowlist_and_the_projects_variables(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            project.settings["agent_env_passthrough"] = ["DATABASE_URL", "NOT_SET_HERE"]
            store.save_project(project)
            configs: list[AgentRunConfig] = []

            def developer(config: AgentRunConfig):
                configs.append(config)
                return self._native_developer_success(config)

            def reviewer(config: AgentRunConfig):
                configs.append(config)
                return self._native_reviewer_approve(config)

            runner = ScriptedNativeRunner({1: developer, 2: reviewer})
            with patch.dict(os.environ, {"DATABASE_URL": "postgres://test"}):
                ForemanOrchestrator(
                    store, roles=self.roles, workflows=self.workflows,
                    agent_runners={"claude_code": runner},
                ).run_project(project.id)

            developer_config, reviewer_config = configs
            self.assertEqual(developer_config.allowed_tools, ())
            self.assertEqual(reviewer_config.allowed_tools, READING_ONLY)
            self.assertEqual(developer_config.env["DATABASE_URL"], "postgres://test")
            self.assertNotIn("NOT_SET_HERE", developer_config.env)
            policies = [
                e.payload for e in store.list_events(task_id=task.id)
                if e.event_type == "engine.role_policy"
            ]
            self.assertEqual(
                [p["allowed_tools"] for p in policies], [[], list(READING_ONLY)]
            )


if __name__ == "__main__":
    unittest.main()
