"""Tests for the Foreman runner module."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from foreman.runner.base import (
    AgentEvent,
    AgentRunConfig,
    InfrastructureError,
    PreflightError,
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

    def test_does_not_retry_preflight_error(self) -> None:
        """Preflight failures should fail fast without infrastructure retries."""
        runner = MagicMock()
        runner.run.side_effect = PreflightError("Claude Code preflight failed")
        config = AgentRunConfig(
            backend="claude_code",
            prompt="test",
            working_dir=Path("/tmp"),
            session_id=None,
            permission_mode="auto",
            model=None,
        )

        sleep_calls = []
        events = list(
            run_with_retry(
                runner,
                config,
                max_retries=3,
                sleep=lambda seconds: sleep_calls.append(seconds),
            )
        )

        self.assertEqual([event.event_type for event in events], ["agent.error"])
        self.assertTrue(events[0].payload["preflight_failed"])
        self.assertEqual(sleep_calls, [])


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


if __name__ == "__main__":
    unittest.main()
