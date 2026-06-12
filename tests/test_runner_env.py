"""Unit coverage for runner environment resolution."""

from __future__ import annotations

import os
from unittest.mock import patch
import unittest

from foreman.runner import PreflightError
from foreman.runner.env import resolve_env


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


if __name__ == "__main__":
    unittest.main()
