"""Tests for the Foreman runner module."""

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from foreman.runner.base import (
    AgentEvent,
    AgentRunConfig,
    AgentRunner,
    RunnerError,
)
from foreman.runner.claude_code import ClaudeCodeRunner
from foreman.runner.signals import (
    event_from_signal,
    extract_signals,
    parse_signal,
)


class SignalParsingTests(unittest.TestCase):
    """Tests for signal parsing utilities."""

    def test_parse_signal_valid(self) -> None:
        """Parse a valid FOREMAN_SIGNAL line."""
        line = "Some output\nFOREMAN_SIGNAL: {\"type\": \"status\", \"value\": \"working\"}"
        result = parse_signal(line)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "status")
        self.assertEqual(result["value"], "working")

    def test_parse_signal_invalid_json(self) -> None:
        """Return None for malformed JSON in signal."""
        line = "FOREMAN_SIGNAL: {not valid json}"
        result = parse_signal(line)
        self.assertIsNone(result)

    def test_parse_signal_no_match(self) -> None:
        """Return None when no signal pattern is present."""
        line = "Regular output without signal"
        result = parse_signal(line)
        self.assertIsNone(result)

    def test_extract_signals_multiple(self) -> None:
        """Extract multiple signals from text."""
        text = """
FOREMAN_SIGNAL: {"type": "progress", "percent": 50}
Some other output
FOREMAN_SIGNAL: {"type": "progress", "percent": 100}
"""
        signals = extract_signals(text)
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0]["percent"], 50)
        self.assertEqual(signals[1]["percent"], 100)

    def test_event_from_signal(self) -> None:
        """Create AgentEvent from parsed signal."""
        signal = {"type": "checkpoint", "name": "phase1", "status": "done"}
        event = event_from_signal(signal)
        self.assertEqual(event.event_type, "signal.checkpoint")
        self.assertEqual(event.payload["name"], "phase1")
        self.assertEqual(event.payload["status"], "done")
        self.assertNotIn("type", event.payload)


class AgentRunConfigTests(unittest.TestCase):
    """Tests for AgentRunConfig dataclass."""

    def test_defaults(self) -> None:
        """Default configuration values."""
        config = AgentRunConfig(backend="claude_code")
        self.assertEqual(config.backend, "claude_code")
        self.assertIsNone(config.model)
        self.assertEqual(config.prompt, "")
        self.assertEqual(config.permission_mode, "auto")
        self.assertEqual(config.timeout_seconds, 3600)
        self.assertEqual(config.max_cost_usd, 10.0)

    def test_full_config(self) -> None:
        """Full configuration with all fields."""
        config = AgentRunConfig(
            backend="claude_code",
            model="claude-sonnet-4-6",
            prompt="Write a function",
            working_dir=Path("/tmp/test"),
            session_id="sess-123",
            permission_mode="ask",
            disallowed_tools=["Bash"],
            extra_flags={"verbose": True},
            timeout_seconds=600,
            max_cost_usd=5.0,
        )
        self.assertEqual(config.model, "claude-sonnet-4-6")
        self.assertEqual(config.session_id, "sess-123")
        self.assertEqual(config.disallowed_tools, ["Bash"])


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


class ClaudeCodeRunnerTests(unittest.TestCase):
    """Tests for ClaudeCodeRunner."""

    def setUp(self) -> None:
        self.runner = ClaudeCodeRunner()
        self.config = AgentRunConfig(
            backend="claude_code",
            prompt="Test prompt",
            working_dir=Path("/tmp"),
        )

    def test_unsupported_backend_raises(self) -> None:
        """Runner raises error for unsupported backend."""
        config = AgentRunConfig(backend="unknown", prompt="test")
        with self.assertRaises(RunnerError) as ctx:
            list(self.runner.run(config))
        self.assertIn("Unsupported backend", str(ctx.exception))

    def test_build_command_basic(self) -> None:
        """Build basic command without extras."""
        cmd = self.runner._build_command(self.config)
        self.assertEqual(cmd[0], "claude")
        self.assertIn("--print", cmd)
        self.assertIn("--verbose", cmd)
        self.assertIn("stream-json", cmd)
        self.assertIn("Test prompt", cmd)

    def test_build_command_with_model(self) -> None:
        """Build command with model selection."""
        config = AgentRunConfig(
            backend="claude_code",
            model="claude-opus-4-6",
            prompt="test",
        )
        cmd = self.runner._build_command(config)
        self.assertIn("--model", cmd)
        self.assertIn("claude-opus-4-6", cmd)

    def test_build_command_with_session(self) -> None:
        """Build command with session resume."""
        config = AgentRunConfig(
            backend="claude_code",
            prompt="test",
            session_id="sess-abc123",
        )
        cmd = self.runner._build_command(config)
        self.assertIn("--resume", cmd)
        self.assertIn("sess-abc123", cmd)

    def test_build_command_with_disallowed_tools(self) -> None:
        """Build command with disallowed tools."""
        config = AgentRunConfig(
            backend="claude_code",
            prompt="test",
            disallowed_tools=["Bash", "Write"],
        )
        cmd = self.runner._build_command(config)
        self.assertIn("--disallowed-tool", cmd)
        self.assertIn("Bash", cmd)
        self.assertIn("Write", cmd)

    def test_parse_assistant_text_message(self) -> None:
        """Parse assistant message with text content."""
        data = {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "Hello, world!"}]
            },
        }
        event = self.runner._parse_assistant_event(data)
        self.assertEqual(event.event_type, "agent.message")
        self.assertEqual(event.payload["text"], "Hello, world!")

    def test_parse_assistant_bash_tool(self) -> None:
        """Parse assistant message with Bash tool use."""
        data = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "ls -la", "description": "List files"},
                    }
                ]
            },
        }
        event = self.runner._parse_assistant_event(data)
        self.assertEqual(event.event_type, "agent.command")
        self.assertEqual(event.payload["command"], "ls -la")
        self.assertEqual(event.payload["description"], "List files")

    def test_parse_assistant_file_tool(self) -> None:
        """Parse assistant message with file tool use."""
        data = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Write",
                        "input": {"file_path": "/tmp/test.py", "content": "print(1)"},
                    }
                ]
            },
        }
        event = self.runner._parse_assistant_event(data)
        self.assertEqual(event.event_type, "agent.file_change")
        self.assertEqual(event.payload["tool"], "Write")
        self.assertEqual(event.payload["path"], "/tmp/test.py")

    def test_parse_result_success(self) -> None:
        """Parse successful result event."""
        data = {
            "type": "result",
            "is_error": False,
            "total_cost_usd": 0.05,
            "duration_ms": 5000,
        }
        event = self.runner._parse_result_event(data)
        self.assertEqual(event.event_type, "agent.completed")
        self.assertEqual(event.payload["cost_usd"], 0.05)
        self.assertEqual(event.payload["duration_ms"], 5000)

    def test_parse_result_error(self) -> None:
        """Parse error result event."""
        data = {
            "type": "result",
            "is_error": True,
            "error": "Something went wrong",
            "total_cost_usd": 0.02,
        }
        event = self.runner._parse_result_event(data)
        self.assertEqual(event.event_type, "agent.error")
        self.assertEqual(event.payload["error"], "Something went wrong")


if __name__ == "__main__":
    unittest.main()
