"""Tests for the Foreman runner module."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from foreman.runner.base import (
    AgentEvent,
    AgentRunConfig,
    InfrastructureError,
    run_with_retry,
)
from foreman.runner.claude_code import ClaudeCodeRunner
from foreman.runner.codex import CodexRunner
from foreman.runner.signals import extract_signal_events


class SignalParsingTests(unittest.TestCase):
    """Tests for signal parsing utilities."""

    def test_extract_signal_events_empty_text(self) -> None:
        """Return empty tuple for empty text."""
        cleaned, events = extract_signal_events("")
        self.assertEqual(cleaned, "")
        self.assertEqual(events, ())

    def test_extract_signal_events_no_signals(self) -> None:
        """Return original text when no signals present."""
        text = "Regular output without signals"
        cleaned, events = extract_signal_events(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(events, ())

    def test_extract_signal_events_single_signal(self) -> None:
        """Extract a single FOREMAN_SIGNAL from text."""
        text = 'Some output\nFOREMAN_SIGNAL: {"type": "progress", "percent": 50}'
        cleaned, events = extract_signal_events(text)
        self.assertIn("Some output", cleaned)
        self.assertNotIn("FOREMAN_SIGNAL", cleaned)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "signal.progress")
        self.assertEqual(events[0].payload["percent"], 50)

    def test_extract_signal_events_multiple_signals(self) -> None:
        """Extract multiple signals from text."""
        text = """
FOREMAN_SIGNAL: {"type": "progress", "percent": 50}
Some other output
FOREMAN_SIGNAL: {"type": "progress", "percent": 100}
"""
        cleaned, events = extract_signal_events(text)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].payload["percent"], 50)
        self.assertEqual(events[1].payload["percent"], 100)

    def test_extract_signal_events_invalid_json(self) -> None:
        """Skip signals with invalid JSON."""
        text = "FOREMAN_SIGNAL: {not valid json}"
        cleaned, events = extract_signal_events(text)
        self.assertNotIn("FOREMAN_SIGNAL", cleaned)
        self.assertEqual(events, ())

    def test_extract_signal_events_unknown_type(self) -> None:
        """Skip signals with unknown type."""
        text = 'FOREMAN_SIGNAL: {"type": "unknown_type", "value": 1}'
        cleaned, events = extract_signal_events(text)
        self.assertNotIn("FOREMAN_SIGNAL", cleaned)
        self.assertEqual(events, ())


class AgentRunConfigTests(unittest.TestCase):
    """Tests for AgentRunConfig dataclass."""

    def test_defaults(self) -> None:
        """Default configuration values."""
        config = AgentRunConfig(
            backend="claude_code",
            model=None,
            prompt="",
            working_dir=Path("/tmp"),
            session_id=None,
            permission_mode="auto",
        )
        self.assertEqual(config.backend, "claude_code")
        self.assertIsNone(config.model)
        self.assertEqual(config.prompt, "")
        self.assertEqual(config.permission_mode, "auto")
        self.assertEqual(config.timeout_seconds, 0)
        self.assertEqual(config.max_cost_usd, 0.0)

    def test_full_config(self) -> None:
        """Full configuration with all fields."""
        config = AgentRunConfig(
            backend="claude_code",
            model="claude-sonnet-4-6",
            prompt="Write a function",
            working_dir=Path("/tmp/test"),
            session_id="sess-123",
            permission_mode="ask",
            disallowed_tools=("Bash",),
            extra_flags={"verbose": True},
            timeout_seconds=600,
            max_cost_usd=5.0,
        )
        self.assertEqual(config.model, "claude-sonnet-4-6")
        self.assertEqual(config.session_id, "sess-123")
        self.assertEqual(config.disallowed_tools, ("Bash",))


class AgentEventTests(unittest.TestCase):
    """Tests for AgentEvent dataclass."""

    def test_event_defaults(self) -> None:
        """Event has auto-generated timestamp."""
        event = AgentEvent(event_type="agent.message")
        self.assertEqual(event.event_type, "agent.message")
        self.assertIsNotNone(event.timestamp)
        self.assertEqual(event.payload, {})

    def test_event_with_payload(self) -> None:
        """Event with custom payload."""
        event = AgentEvent(
            event_type="agent.completed",
            payload={"cost_usd": 0.05, "tokens": 100},
        )
        self.assertEqual(event.payload["cost_usd"], 0.05)


class RunWithRetryTests(unittest.TestCase):
    """Tests for run_with_retry helper."""

    def test_success_on_first_try(self) -> None:
        """Return events immediately on success."""
        runner = MagicMock()
        runner.run.return_value = iter([
            AgentEvent("agent.completed", payload={"cost_usd": 0.01}),
        ])
        config = AgentRunConfig(
            backend="claude_code",
            prompt="test",
            working_dir=Path("/tmp"),
            session_id=None,
            permission_mode="auto",
            model=None,
        )

        events = list(run_with_retry(runner, config, max_retries=0))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "agent.completed")

    def test_retries_on_infrastructure_error(self) -> None:
        """Retry on infrastructure errors."""
        runner = MagicMock()
        call_count = [0]

        def mock_run(config):
            call_count[0] += 1
            if call_count[0] < 3:
                raise InfrastructureError("Transient error")
            yield AgentEvent("agent.completed", payload={})

        runner.run = mock_run
        config = AgentRunConfig(
            backend="claude_code",
            prompt="test",
            working_dir=Path("/tmp"),
            session_id=None,
            permission_mode="auto",
            model=None,
        )

        sleep_calls = []
        events = list(run_with_retry(
            runner,
            config,
            max_retries=3,
            sleep=lambda s: sleep_calls.append(s),
        ))

        self.assertEqual(len(events), 3)  # 2 infra_error + 1 completed
        self.assertEqual(events[-1].event_type, "agent.completed")
        self.assertEqual(len(sleep_calls), 2)  # 2 retries


class ClaudeCodeRunnerTests(unittest.TestCase):
    """Tests for ClaudeCodeRunner."""

    def setUp(self) -> None:
        self.runner = ClaudeCodeRunner()
        self.config = AgentRunConfig(
            backend="claude_code",
            prompt="Test prompt",
            working_dir=Path("/tmp"),
            session_id=None,
            permission_mode="auto",
            model=None,
        )

    def test_build_command_basic(self) -> None:
        """Build basic command without extras."""
        cmd = self.runner.build_command(self.config)
        self.assertEqual(cmd[0], "claude")
        self.assertIn("--print", cmd)
        self.assertIn("--output-format", cmd)
        self.assertIn("stream-json", cmd)

    def test_build_command_with_model(self) -> None:
        """Build command with model selection."""
        config = AgentRunConfig(
            backend="claude_code",
            model="claude-opus-4-6",
            prompt="test",
            working_dir=Path("/tmp"),
            session_id=None,
            permission_mode="auto",
        )
        cmd = self.runner.build_command(config)
        self.assertIn("--model", cmd)
        self.assertIn("claude-opus-4-6", cmd)

    def test_build_command_with_session(self) -> None:
        """Build command with session resume."""
        config = AgentRunConfig(
            backend="claude_code",
            prompt="test",
            working_dir=Path("/tmp"),
            session_id="sess-abc123",
            permission_mode="auto",
            model=None,
        )
        cmd = self.runner.build_command(config)
        self.assertIn("--resume", cmd)
        self.assertIn("sess-abc123", cmd)

    def test_build_command_with_disallowed_tools(self) -> None:
        """Build command with disallowed tools."""
        config = AgentRunConfig(
            backend="claude_code",
            prompt="test",
            working_dir=Path("/tmp"),
            session_id=None,
            permission_mode="auto",
            model=None,
            disallowed_tools=("Bash", "Write"),
        )
        cmd = self.runner.build_command(config)
        self.assertIn("--disallowed-tools", cmd)
        self.assertIn("Bash,Write", cmd)


class CodexRunnerTests(unittest.TestCase):
    """Tests for CodexRunner."""

    def setUp(self) -> None:
        self.runner = CodexRunner()
        self.config = AgentRunConfig(
            backend="codex",
            prompt="Test prompt",
            working_dir=Path("/tmp"),
            session_id=None,
            permission_mode="auto",
            model=None,
        )

    def test_build_command_basic(self) -> None:
        """Build basic command without extras."""
        cmd = self.runner.build_command(self.config)
        self.assertEqual(cmd[0], "codex")
        self.assertIn("--json-rpc", cmd)
        self.assertIn("--quiet", cmd)

    def test_build_command_with_model(self) -> None:
        """Build command with model selection."""
        config = AgentRunConfig(
            backend="codex",
            model="o3",
            prompt="test",
            working_dir=Path("/tmp"),
            session_id=None,
            permission_mode="auto",
        )
        cmd = self.runner.build_command(config)
        self.assertIn("--model", cmd)
        self.assertIn("o3", cmd)

    def test_build_command_with_session(self) -> None:
        """Build command with session resume."""
        config = AgentRunConfig(
            backend="codex",
            prompt="test",
            working_dir=Path("/tmp"),
            session_id="sess-abc123",
            permission_mode="auto",
            model=None,
        )
        cmd = self.runner.build_command(config)
        self.assertIn("--session", cmd)
        self.assertIn("sess-abc123", cmd)

    def test_parse_text_delta_notification(self) -> None:
        """Parse text_delta notification."""
        notification = {
            "method": "text_delta",
            "params": {"text": "Hello, world!"},
        }
        events = self.runner._parse_notification(
            notification,
            working_dir=Path("/tmp"),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "agent.message")
        self.assertEqual(events[0].payload["text"], "Hello, world!")

    def test_parse_tool_call_bash(self) -> None:
        """Parse Bash tool call notification."""
        notification = {
            "method": "tool_call",
            "params": {
                "name": "Bash",
                "arguments": {"command": "ls -la", "cwd": "/tmp"},
            },
        }
        events = self.runner._parse_notification(
            notification,
            working_dir=Path("/tmp"),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "agent.command")
        self.assertEqual(events[0].payload["command"], "ls -la")

    def test_parse_tool_call_file_write(self) -> None:
        """Parse file write tool call notification."""
        notification = {
            "method": "tool_call",
            "params": {
                "name": "Write",
                "arguments": {"file_path": "/tmp/test.py", "content": "print(1)"},
            },
        }
        events = self.runner._parse_notification(
            notification,
            working_dir=Path("/tmp"),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "agent.file_change")
        self.assertEqual(events[0].payload["tool"], "Write")
        self.assertEqual(events[0].payload["path"], "/tmp/test.py")

    def test_parse_cost_update_notification(self) -> None:
        """Parse cost update notification."""
        notification = {
            "method": "cost_update",
            "params": {"cost_usd": 0.05, "tokens": 100},
        }
        events = self.runner._parse_notification(
            notification,
            working_dir=Path("/tmp"),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "agent.cost_update")
        self.assertEqual(events[0].payload["cumulative_usd"], 0.05)

    def test_parse_approval_request_notification(self) -> None:
        """Parse approval request notification."""
        notification = {
            "method": "approval_request",
            "params": {
                "type": "tool",
                "tool": "Bash",
                "command": "rm -rf /",
                "message": "Dangerous command detected",
            },
        }
        events = self.runner._parse_notification(
            notification,
            working_dir=Path("/tmp"),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "agent.approval_request")
        self.assertEqual(events[0].payload["tool"], "Bash")

    def test_parse_successful_response(self) -> None:
        """Parse successful JSON-RPC response."""
        response = {
            "result": {
                "text": "Task completed!",
                "session_id": "sess-123",
                "cost_usd": 0.05,
                "duration_ms": 5000,
            }
        }
        events = self.runner._parse_response(response)
        self.assertTrue(any(e.event_type == "agent.completed" for e in events))
        completed = next(e for e in events if e.event_type == "agent.completed")
        self.assertEqual(completed.payload["session_id"], "sess-123")
        self.assertEqual(completed.payload["cost_usd"], 0.05)

    def test_parse_error_response(self) -> None:
        """Parse error JSON-RPC response."""
        response = {
            "error": {
                "code": -1,
                "message": "Something went wrong",
            }
        }
        events = self.runner._parse_response(response)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "agent.error")
        self.assertEqual(events[0].payload["error"], "Something went wrong")


if __name__ == "__main__":
    unittest.main()
