"""Tests for the Foreman executor module."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from foreman.executor import ClaudeCodeExecutor, RunnerExecutorConfig
from foreman.models import Project, Task
from foreman.orchestrator import AgentExecutionResult
from foreman.roles import default_roles_dir, load_roles
from foreman.runner.base import AgentEvent, InfrastructureError


class RunnerExecutorConfigTests(unittest.TestCase):
    """Tests for RunnerExecutorConfig."""

    def test_defaults(self) -> None:
        """Default configuration values."""
        config = RunnerExecutorConfig()
        self.assertEqual(config.default_timeout_seconds, 3600)
        self.assertEqual(config.default_max_cost_usd, 10.0)
        self.assertEqual(config.default_permission_mode, "auto")
        self.assertTrue(config.capture_all_events)

    def test_custom_config(self) -> None:
        """Custom configuration values."""
        config = RunnerExecutorConfig(
            default_timeout_seconds=600,
            default_max_cost_usd=5.0,
            default_permission_mode="ask",
            capture_all_events=False,
        )
        self.assertEqual(config.default_timeout_seconds, 600)
        self.assertEqual(config.default_max_cost_usd, 5.0)
        self.assertEqual(config.default_permission_mode, "ask")
        self.assertFalse(config.capture_all_events)


class ClaudeCodeExecutorTests(unittest.TestCase):
    """Tests for ClaudeCodeExecutor."""

    def setUp(self) -> None:
        self.executor = ClaudeCodeExecutor()
        # Load actual shipped roles instead of creating mock ones
        self.roles = load_roles(default_roles_dir())
        self.role = self.roles["developer"]
        self.project = Project(
            id="proj-001",
            name="Test Project",
            repo_path="/tmp/test-repo",
            workflow_id="development",
        )
        self.task = Task(
            id="task-001",
            sprint_id="sprint-001",
            project_id="proj-001",
            title="Test Task",
        )

    def test_build_run_config_uses_role_model(self) -> None:
        """Config uses model from role definition."""
        config = self.executor._build_run_config(
            role=self.role,
            project=self.project,
            prompt="Test prompt",
            session_id=None,
        )
        self.assertEqual(config.backend, "claude_code")
        self.assertEqual(config.prompt, "Test prompt")
        self.assertIsNone(config.session_id)

    def test_build_run_config_uses_project_settings(self) -> None:
        """Config respects project settings for timeout and cost."""
        self.project.settings["runner_timeout_seconds"] = 600
        self.project.settings["runner_max_cost_usd"] = 5.0
        self.project.settings["runner_permission_mode"] = "ask"

        config = self.executor._build_run_config(
            role=self.role,
            project=self.project,
            prompt="Test",
            session_id="sess-123",
        )
        self.assertEqual(config.timeout_seconds, 600)
        self.assertEqual(config.max_cost_usd, 5.0)
        self.assertEqual(config.permission_mode, "ask")
        self.assertEqual(config.session_id, "sess-123")

    def test_build_run_config_uses_role_disallowed_tools(self) -> None:
        """Config includes disallowed tools from role."""
        # Developer role has no disallowed tools by default
        # Use code_reviewer which has Write disallowed
        reviewer = self.roles["code_reviewer"]
        config = self.executor._build_run_config(
            role=reviewer,
            project=self.project,
            prompt="Test",
            session_id=None,
        )
        # Code reviewer has Write in disallowed tools
        self.assertIn("Write", config.disallowed_tools)

    def test_event_to_record_preserves_fields(self) -> None:
        """Event conversion preserves all fields."""
        event = AgentEvent(
            event_type="agent.message",
            payload={"text": "Hello"},
        )
        record = self.executor._event_to_record(event)
        self.assertEqual(record.event_type, "agent.message")
        self.assertIsNotNone(record.timestamp)
        self.assertEqual(record.payload["text"], "Hello")

    @patch("foreman.executor.ClaudeCodeRunner")
    def test_execute_returns_result_on_completion(self, mock_runner_class: MagicMock) -> None:
        """Execute returns completed result when agent finishes."""
        mock_runner = MagicMock()
        mock_runner_class.return_value = mock_runner
        mock_runner.run.return_value = iter([
            AgentEvent(event_type="agent.message", payload={"text": "Working..."}),
            AgentEvent(
                event_type="agent.completed",
                payload={
                    "cost_usd": 0.05,
                    "token_count": 100,
                    "result": "Done!",
                },
            ),
        ])

        executor = ClaudeCodeExecutor()
        executor.runner = mock_runner

        result = executor.execute(
            role=self.role,
            project=self.project,
            task=self.task,
            workflow_step="develop",
            prompt="Test prompt",
            session_id=None,
            carried_output=None,
        )

        self.assertEqual(result.outcome, "done")
        self.assertEqual(result.detail, "Done!")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.cost_usd, 0.05)
        self.assertEqual(result.token_count, 100)
        self.assertEqual(len(result.events), 2)

    @patch("foreman.executor.ClaudeCodeRunner")
    def test_execute_handles_error(self, mock_runner_class: MagicMock) -> None:
        """Execute handles runner errors gracefully."""
        mock_runner = MagicMock()
        mock_runner_class.return_value = mock_runner
        mock_runner.run.side_effect = InfrastructureError("Claude CLI not found")

        executor = ClaudeCodeExecutor()
        executor.runner = mock_runner

        result = executor.execute(
            role=self.role,
            project=self.project,
            task=self.task,
            workflow_step="develop",
            prompt="Test prompt",
            session_id=None,
            carried_output=None,
        )

        self.assertEqual(result.outcome, "error")
        self.assertIn("Claude CLI not found", result.detail)
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.events[0].event_type, "agent.error")

    @patch("foreman.executor.ClaudeCodeRunner")
    def test_execute_handles_agent_error_event(self, mock_runner_class: MagicMock) -> None:
        """Execute handles agent.error events."""
        mock_runner = MagicMock()
        mock_runner_class.return_value = mock_runner
        mock_runner.run.return_value = iter([
            AgentEvent(
                event_type="agent.error",
                payload={"error": "Something went wrong"},
            ),
        ])

        executor = ClaudeCodeExecutor()
        executor.runner = mock_runner

        result = executor.execute(
            role=self.role,
            project=self.project,
            task=self.task,
            workflow_step="develop",
            prompt="Test prompt",
            session_id=None,
            carried_output=None,
        )

        self.assertEqual(result.outcome, "error")
        self.assertIn("Something went wrong", result.detail)
        self.assertEqual(result.status, "failed")

    @patch("foreman.executor.ClaudeCodeRunner")
    def test_execute_handles_signal_completion(self, mock_runner_class: MagicMock) -> None:
        """Execute respects signal.completion events."""
        mock_runner = MagicMock()
        mock_runner_class.return_value = mock_runner
        mock_runner.run.return_value = iter([
            AgentEvent(
                event_type="signal.completion",
                payload={"outcome": "approve", "detail": "Code looks good"},
            ),
        ])

        executor = ClaudeCodeExecutor()
        executor.runner = mock_runner

        result = executor.execute(
            role=self.role,
            project=self.project,
            task=self.task,
            workflow_step="review",
            prompt="Review this code",
            session_id=None,
            carried_output=None,
        )

        self.assertEqual(result.outcome, "approve")
        self.assertEqual(result.detail, "Code looks good")


if __name__ == "__main__":
    unittest.main()
