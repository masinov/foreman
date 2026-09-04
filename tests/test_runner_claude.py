"""Unit coverage for the native Claude Code runner."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from foreman.runner import (
    AgentRunConfig,
    ClaudeCodeRunner,
    InfrastructureError,
    PreflightError,
    QuotaExhaustedError,
    run_with_retry,
)
from foreman.runner.base import AgentEvent


class _FakeInput:
    def __init__(self) -> None:
        self.text = ""
        self.closed = False

    def write(self, text: str) -> None:
        self.text += text

    def close(self) -> None:
        self.closed = True


class _FakeOutput:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)


class _FakeErrorStream:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def read(self) -> str:
        return self.text


class _FakeProcess:
    def __init__(
        self,
        *,
        lines: list[str],
        returncode: int = 0,
        stderr: str = "",
    ) -> None:
        self.stdin = _FakeInput()
        self.stdout = _FakeOutput(lines)
        self.stderr = _FakeErrorStream(stderr)
        self.returncode = returncode
        self.killed = False

    def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class _PopenRecorder:
    def __init__(self, process: _FakeProcess) -> None:
        self.process = process
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __call__(self, *args: object, **kwargs: object) -> _FakeProcess:
        self.calls.append((args, kwargs))
        return self.process


class _FlakyRunner:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def run(self, config: AgentRunConfig):
        del config
        self.calls += 1
        if self.calls <= self.failures:
            raise InfrastructureError("provider unavailable")
        yield AgentEvent("agent.completed", payload={"session_id": "sess-1"})


class ClaudeCodeRunnerTests(unittest.TestCase):
    def create_config(self, repo_path: Path) -> AgentRunConfig:
        return AgentRunConfig(
            backend="claude_code",
            model="claude-sonnet-4-6",
            prompt="Implement the task.",
            working_dir=repo_path,
            session_id="resume-123",
            permission_mode="bypassPermissions",
            disallowed_tools=("Bash", "Write"),
            extra_flags={"effort": "medium"},
            timeout_seconds=60,
            max_cost_usd=10.0,
        )

    def test_build_command_includes_resume_model_tools_and_extra_flags(self) -> None:
        runner = ClaudeCodeRunner()
        config = self.create_config(Path("/tmp/demo"))

        command = runner.build_command(config)

        self.assertEqual(command[:6], ["claude", "--print", "--verbose", "--output-format", "stream-json", "--permission-mode"])
        self.assertIn("bypassPermissions", command)
        self.assertIn("--resume", command)
        self.assertIn("resume-123", command)
        self.assertIn("--model", command)
        self.assertIn("claude-sonnet-4-6", command)
        self.assertIn("--disallowed-tools", command)
        self.assertIn("Bash,Write", command)
        self.assertIn("--effort", command)
        self.assertIn("medium", command)

    def test_run_passes_merged_environment_only_when_configured(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo_path = Path(temp_dir.name)
        config = self.create_config(repo_path)
        config.env["ANTHROPIC_BASE_URL"] = "https://api.minimax.io/anthropic"
        config.env["ANTHROPIC_AUTH_TOKEN"] = "test-token"
        process = _FakeProcess(
            lines=[
                json.dumps(
                    {
                        "type": "result",
                        "is_error": False,
                        "session_id": "sess-123",
                        "result": "TASK_COMPLETE",
                    }
                )
                + "\n",
            ]
        )
        popen = _PopenRecorder(process)
        runner = ClaudeCodeRunner(
            popen_factory=popen,
            clock=lambda: 0.0,
            which=lambda _: "/usr/bin/claude",
        )

        list(runner.run(config))

        env = popen.calls[0][1]["env"]
        self.assertIsInstance(env, dict)
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://api.minimax.io/anthropic")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "test-token")

    def test_run_omits_environment_kwarg_when_unconfigured(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo_path = Path(temp_dir.name)
        config = self.create_config(repo_path)
        process = _FakeProcess(
            lines=[
                json.dumps(
                    {
                        "type": "result",
                        "is_error": False,
                        "session_id": "sess-123",
                        "result": "TASK_COMPLETE",
                    }
                )
                + "\n",
            ]
        )
        popen = _PopenRecorder(process)
        runner = ClaudeCodeRunner(
            popen_factory=popen,
            clock=lambda: 0.0,
            which=lambda _: "/usr/bin/claude",
        )

        list(runner.run(config))

        self.assertNotIn("env", popen.calls[0][1])

    def test_run_maps_stream_json_events_and_strips_signal_lines_from_messages(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo_path = Path(temp_dir.name)
        config = self.create_config(repo_path)
        process = _FakeProcess(
            lines=[
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Working on the task.\n"
                                        'FOREMAN_SIGNAL: {"type":"progress","message":"halfway"}\n'
                                        "TASK_COMPLETE"
                                    ),
                                },
                                {
                                    "type": "tool_use",
                                    "name": "Bash",
                                    "input": {"command": "pytest -q"},
                                },
                                {
                                    "type": "tool_use",
                                    "name": "Write",
                                    "input": {"file_path": "README.md"},
                                },
                                {
                                    "type": "tool_use",
                                    "name": "Glob",
                                    "input": {"pattern": "*.py"},
                                },
                            ]
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "type": "result",
                        "is_error": False,
                        "session_id": "sess-123",
                        "total_cost_usd": 1.25,
                        "duration_ms": 1234,
                        "usage": {"total_tokens": 321},
                        "result": "Implemented the feature.\nTASK_COMPLETE",
                    }
                )
                + "\n",
            ]
        )
        popen = _PopenRecorder(process)
        runner = ClaudeCodeRunner(
            popen_factory=popen,
            clock=lambda: 0.0,
            which=lambda _: "/usr/bin/claude",
        )

        events = list(runner.run(config))

        self.assertEqual(process.stdin.text, "Implement the task.")
        self.assertTrue(process.stdin.closed)
        self.assertEqual(popen.calls[0][1]["cwd"], str(repo_path))
        self.assertEqual(
            [event.event_type for event in events],
            [
                "agent.started",
                "agent.raw_output",
                "agent.message",
                "signal.progress",
                "agent.command",
                "agent.file_change",
                "agent.tool_use",
                "agent.raw_output",
                "agent.message",
                "agent.cost_update",
                "agent.completed",
            ],
        )
        self.assertEqual(events[1].payload["stream"], "stdout")
        self.assertIn("\"type\": \"assistant\"", events[1].payload["line"])
        self.assertEqual(events[2].payload["text"], "Working on the task.\nTASK_COMPLETE")
        self.assertEqual(events[3].payload, {"message": "halfway"})
        self.assertEqual(events[4].payload["command"], "pytest -q")
        self.assertEqual(events[5].payload, {"tool": "Write", "path": "README.md"})
        self.assertEqual(events[6].payload["tool"], "Glob")
        self.assertEqual(events[7].payload["stream"], "stdout")
        self.assertIn("\"type\": \"result\"", events[7].payload["line"])
        self.assertEqual(events[8].payload["text"], "Implemented the feature.\nTASK_COMPLETE")
        self.assertEqual(events[9].payload["cumulative_usd"], 1.25)
        self.assertEqual(events[9].payload["cumulative_tokens"], 321)
        self.assertEqual(events[10].payload["session_id"], "sess-123")
        self.assertEqual(events[10].payload["duration_ms"], 1234)
        self.assertEqual(events[10].payload["token_count"], 321)

    def _run_lines(self, lines: list[str]) -> list[AgentEvent]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        config = self.create_config(Path(temp_dir.name))
        process = _FakeProcess(lines=[line + "\n" for line in lines])
        runner = ClaudeCodeRunner(
            popen_factory=_PopenRecorder(process),
            clock=lambda: 0.0,
            which=lambda _: "/usr/bin/claude",
        )
        return list(runner.run(config))

    def test_run_turns_progress_lines_into_ticks_without_raw_output(self) -> None:
        thinking = {
            "type": "system",
            "subtype": "thinking_tokens",
            "estimated_tokens": 150,
            "estimated_tokens_delta": 50,
            "session_id": "sess-1",
        }
        allowed = {
            "type": "rate_limit_event",
            "rate_limit_info": {"status": "allowed", "rateLimitType": "five_hour"},
        }
        result = {"type": "result", "is_error": False, "session_id": "sess-1", "result": "done"}

        events = self._run_lines([json.dumps(thinking), json.dumps(allowed), json.dumps(result)])

        self.assertEqual(
            [event.event_type for event in events],
            [
                "agent.started",
                "agent.tick",
                "agent.tick",
                "agent.raw_output",
                "agent.message",
                "agent.completed",
            ],
        )
        self.assertEqual(events[1].payload, {"source": "thinking_tokens", "estimated_tokens": 150})
        self.assertEqual(events[2].payload, {"source": "rate_limit", "status": "allowed"})
        self.assertNotIn(
            "agent.tool_use",
            [event.event_type for event in events],
            "progress lines must not be reported as tool uses",
        )

    def test_run_maps_init_and_tool_result_lines_and_caps_raw_output(self) -> None:
        init = {
            "type": "system",
            "subtype": "init",
            "cwd": "/repo",
            "session_id": "sess-2",
            "tools": ["Bash", "Read", "Write"],
            "model": "claude-opus-5",
            "permissionMode": "bypassPermissions",
            "slash_commands": ["init", "compact"],
        }
        long_text = "x" * 20000
        tool_result = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": long_text,
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_2",
                        "is_error": True,
                        "content": [{"type": "text", "text": "No such file"}],
                    },
                ],
            },
        }
        unknown = {"type": "something_new", "detail": {"nested": True}}
        result = {"type": "result", "is_error": False, "session_id": "sess-2", "result": "done"}

        events = self._run_lines(
            [json.dumps(init), json.dumps(tool_result), json.dumps(unknown), json.dumps(result)]
        )

        self.assertEqual(
            [event.event_type for event in events],
            [
                "agent.started",
                "agent.raw_output",
                "agent.session",
                "agent.raw_output",
                "agent.tool_result",
                "agent.tool_result",
                "agent.raw_output",
                "agent.raw_output",
                "agent.message",
                "agent.completed",
            ],
        )
        self.assertEqual(
            events[2].payload,
            {
                "session_id": "sess-2",
                "model": "claude-opus-5",
                "cwd": "/repo",
                "permission_mode": "bypassPermissions",
                "tool_count": 3,
            },
        )
        capped = events[3].payload
        self.assertTrue(capped["truncated"])
        self.assertEqual(capped["length"], len(json.dumps(tool_result)))
        self.assertLessEqual(len(capped["line"]), 8000)
        first, second = events[4].payload, events[5].payload
        self.assertEqual(first["tool_use_id"], "toolu_1")
        self.assertFalse(first["is_error"])
        self.assertEqual(first["length"], 20000)
        self.assertEqual(len(first["preview"]), 500)
        self.assertTrue(first["truncated"])
        self.assertEqual(second["tool_use_id"], "toolu_2")
        self.assertTrue(second["is_error"])
        self.assertEqual(second["preview"], "No such file")
        self.assertFalse(second["truncated"])
        self.assertNotIn("truncated", events[6].payload)

    def test_run_persists_rate_limit_notices_that_are_not_allowed(self) -> None:
        limited = {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "rejected",
                "rateLimitType": "five_hour",
                "resetsAt": 1788528000,
            },
        }
        result = {"type": "result", "is_error": False, "session_id": "sess-3", "result": "done"}

        events = self._run_lines([json.dumps(limited), json.dumps(result)])

        self.assertEqual(
            [event.event_type for event in events][:3],
            ["agent.started", "agent.raw_output", "agent.rate_limit"],
        )
        self.assertEqual(
            events[2].payload,
            {"status": "rejected", "rate_limit_type": "five_hour", "resets_at": 1788528000},
        )

    def _collect_until_error(self, lines: list[str]) -> tuple[list[AgentEvent], BaseException]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        config = self.create_config(Path(temp_dir.name))
        process = _FakeProcess(lines=[line + "\n" for line in lines])
        runner = ClaudeCodeRunner(
            popen_factory=_PopenRecorder(process),
            clock=lambda: 0.0,
            which=lambda _: "/usr/bin/claude",
        )
        events: list[AgentEvent] = []
        try:
            for event in runner.run(config):
                events.append(event)
        except Exception as exc:  # noqa: BLE001 - the test inspects it
            return events, exc
        self.fail("runner did not raise")

    def test_quota_exhaustion_after_a_rejected_rate_limit_notice_is_raised_with_the_reset(self) -> None:
        rejected = {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "rejected",
                "rateLimitType": "five_hour",
                "resetsAt": 1788528000,
            },
        }
        result = {
            "type": "result",
            "is_error": True,
            "session_id": "sess-q",
            "total_cost_usd": 1.46,
            "duration_ms": 56049,
            "usage": {"total_tokens": 3707},
            "result": "You've hit your session limit \u00b7 resets 3:20pm (Europe/Madrid)",
        }

        events, exc = self._collect_until_error([json.dumps(rejected), json.dumps(result)])

        self.assertIsInstance(exc, QuotaExhaustedError)
        self.assertEqual(exc.retry_after, "2026-09-04T13:20:00Z")
        self.assertIn("session limit", str(exc))
        self.assertEqual(
            exc.payload,
            {"session_id": "sess-q", "cost_usd": 1.46, "duration_ms": 56049, "token_count": 3707},
        )
        self.assertIn("agent.rate_limit", [event.event_type for event in events])
        self.assertNotIn("agent.error", [event.event_type for event in events])

    def test_quota_exhaustion_is_recognized_from_the_error_text_alone(self) -> None:
        result = {
            "type": "result",
            "is_error": True,
            "session_id": "sess-q2",
            "result": "You've hit your usage limit.",
        }

        events, exc = self._collect_until_error([json.dumps(result)])

        self.assertIsInstance(exc, QuotaExhaustedError)
        self.assertIsNone(exc.retry_after)
        self.assertEqual(exc.payload["session_id"], "sess-q2")

    def test_ordinary_error_results_stay_agent_errors(self) -> None:
        events = self._run_lines(
            [json.dumps({"type": "result", "is_error": True, "session_id": "s", "result": "Tool crashed."})]
        )

        self.assertEqual(events[-1].event_type, "agent.error")
        self.assertNotIn("quota_exhausted", events[-1].payload)

    def test_run_raises_preflight_error_when_executable_is_missing(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        config = self.create_config(Path(temp_dir.name))
        popen = _PopenRecorder(_FakeProcess(lines=[]))
        runner = ClaudeCodeRunner(
            popen_factory=popen,
            clock=lambda: 0.0,
            which=lambda _: None,
        )

        with self.assertRaises(PreflightError) as exc:
            list(runner.run(config))

        self.assertIn("executable `claude` was not found in PATH", str(exc.exception))
        self.assertEqual(popen.calls, [])

    def test_run_raises_infrastructure_error_when_process_exits_without_terminal_result(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        config = self.create_config(Path(temp_dir.name))
        process = _FakeProcess(lines=[], returncode=2, stderr="provider crashed")
        runner = ClaudeCodeRunner(
            popen_factory=_PopenRecorder(process),
            clock=lambda: 0.0,
            which=lambda _: "/usr/bin/claude",
        )

        with self.assertRaises(InfrastructureError) as exc:
            list(runner.run(config))

        self.assertIn("provider crashed", str(exc.exception))

    def test_run_with_retry_emits_retry_events_and_terminal_error_after_exhaustion(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        config = self.create_config(Path(temp_dir.name))
        runner = _FlakyRunner(failures=3)

        events = list(
            run_with_retry(
                runner,
                config,
                max_retries=2,
                sleep=lambda _: None,
            )
        )

        self.assertEqual(
            [event.event_type for event in events],
            ["agent.infra_error", "agent.infra_error", "agent.error"],
        )
        self.assertEqual(events[0].payload["attempt"], 1)
        self.assertEqual(events[1].payload["attempt"], 2)
        self.assertTrue(events[2].payload["retries_exhausted"])


if __name__ == "__main__":
    unittest.main()
