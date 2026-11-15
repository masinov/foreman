"""Unit coverage for runner environment resolution."""

from __future__ import annotations

import os
from unittest.mock import patch
import unittest

from foreman.runner import PreflightError
from foreman.runner.env import agent_environment, passthrough_env, resolve_env


class ResolveEnvTests(unittest.TestCase):
    def test_literal_values_are_preserved(self) -> None:
        self.assertEqual(
            resolve_env({"ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic"}),
            {"ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic"},
        )

    def test_required_env_value_is_read_from_host_environment(self) -> None:
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "secret"}, clear=False):
            self.assertEqual(
                resolve_env({"ANTHROPIC_AUTH_TOKEN": "env:MINIMAX_API_KEY"}),
                {"ANTHROPIC_AUTH_TOKEN": "secret"},
            )

    def test_env_value_uses_literal_fallback_when_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                resolve_env({"CLAUDE_CONFIG_DIR": "env:FOREMAN_MINIMAX_CONFIG_DIR?~/.foreman/claude-minimax"}),
                {"CLAUDE_CONFIG_DIR": os.path.expanduser("~/.foreman/claude-minimax")},
            )

    def test_missing_required_env_raises_preflight_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PreflightError) as exc:
                resolve_env({"ANTHROPIC_AUTH_TOKEN": "env:MINIMAX_API_KEY"})
        self.assertIn("MINIMAX_API_KEY", str(exc.exception))

    def test_path_suffix_values_are_expanded(self) -> None:
        self.assertEqual(
            resolve_env({"SOME_PATH": "~/foreman/minimax"})["SOME_PATH"],
            os.path.expanduser("~/foreman/minimax"),
        )


class AgentEnvironmentTests(unittest.TestCase):
    """What an agent process is started with (ADR-0023)."""

    HOST = {
        "PATH": "/usr/bin",
        "HOME": "/home/op",
        "LANG": "en_GB.UTF-8",
        "LC_ALL": "C",
        "XDG_CONFIG_HOME": "/home/op/.config",
        "ANTHROPIC_API_KEY": "model-key",
        "CLAUDE_CONFIG_DIR": "/home/op/.claude",
        "OPENAI_API_KEY": "other-model-key",
        "FOREMAN_DASHBOARD_TOKEN": "dashboard-secret",
        "FOREMAN_DB": "/srv/foreman.db",
        "GITHUB_TOKEN": "forge-secret",
        "AWS_SECRET_ACCESS_KEY": "cloud-secret",
        "SSH_AUTH_SOCK": "/run/agent.sock",
        "DATABASE_URL": "postgres://prod",
    }

    def test_the_engines_secrets_stay_with_the_engine(self) -> None:
        environment = agent_environment(host=self.HOST)

        for name in (
            "FOREMAN_DASHBOARD_TOKEN", "FOREMAN_DB", "GITHUB_TOKEN",
            "AWS_SECRET_ACCESS_KEY", "SSH_AUTH_SOCK", "DATABASE_URL",
        ):
            self.assertNotIn(name, environment)

    def test_what_a_cli_needs_to_run_and_sign_in_is_kept(self) -> None:
        environment = agent_environment(host=self.HOST)

        for name in (
            "PATH", "HOME", "LANG", "LC_ALL", "XDG_CONFIG_HOME",
            "ANTHROPIC_API_KEY", "CLAUDE_CONFIG_DIR", "OPENAI_API_KEY",
        ):
            self.assertEqual(environment[name], self.HOST[name])

    def test_what_the_role_sets_is_added_and_wins(self) -> None:
        environment = agent_environment(
            {"ANTHROPIC_API_KEY": "role-key", "EXTRA": "1"}, host=self.HOST
        )

        self.assertEqual(environment["ANTHROPIC_API_KEY"], "role-key")
        self.assertEqual(environment["EXTRA"], "1")

    def test_a_project_passes_named_variables_through(self) -> None:
        self.assertEqual(
            passthrough_env(("DATABASE_URL", "NOT_SET_HERE"), host=self.HOST),
            {"DATABASE_URL": "postgres://prod"},
        )


if __name__ == "__main__":
    unittest.main()
