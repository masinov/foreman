"""Unit coverage for the native Codex runner."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from foreman.runner import AgentRunConfig, CodexRunner, InfrastructureError


class _FakeInput:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, text: str) -> None:
        self.lines.append(text)

    def flush(self) -> None:
        return None


class _FakeOutput:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def readline(self) -> str:
        if not self._lines:
            return ""
        return self._lines.pop(0)


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
        returncode: int | None = None,
        stderr: str = "",
    ) -> None:
        self.stdin = _FakeInput()
        self.stdout = _FakeOutput(lines)
        self.stderr = _FakeErrorStream(stderr)
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        if self.returncode is None:
            self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self.returncode is None:
            self.returncode = 0
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


class CodexRunnerTests(unittest.TestCase):
    def create_config(
        self,
        repo_path: Path,
        *,
        session_id: str | None = None,
        disallowed_tools: tuple[str, ...] = (),
    ) -> AgentRunConfig:
        return AgentRunConfig(
            backend="codex",
            model="gpt-5.4",
            prompt="Implement the task.",
            working_dir=repo_path,
            session_id=session_id,
            permission_mode="bypassPermissions",
            disallowed_tools=disallowed_tools,
            extra_flags={"effort": "medium"},
            timeout_seconds=60,
            max_cost_usd=10.0,
        )

    def test_build_command_uses_app_server_stdio(self) -> None:
        runner = CodexRunner()

        command = runner.build_command()

        self.assertEqual(command, ["codex", "app-server", "--listen", "stdio://"])

    def test_run_starts_thread_and_maps_rpc_notifications(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo_path = Path(temp_dir.name)
        config = self.create_config(repo_path)
        process = _FakeProcess(
            lines=[
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"userAgent": "codex-tests"}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {"id": "thread-123"},
                            "approvalPolicy": "on-request",
                            "approvalsReviewer": "user",
                            "cwd": str(repo_path),
                            "model": "gpt-5.4",
                            "modelProvider": "openai",
                            "sandbox": "workspace-write",
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {"turn": {"id": "turn-1", "status": "inProgress"}}})
                + "\n",
                json.dumps(
                    {
                        "method": "item/agentMessage/delta",
                        "params": {
                            "threadId": "thread-123",
                            "turnId": "turn-1",
                            "itemId": "msg-1",
                            "delta": (
                                "Working on the task.\n"
                                'FOREMAN_SIGNAL: {"type":"progress","message":"halfway"}\n'
                                "TASK_COMPLETE"
                            ),
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "method": "item/started",
                        "params": {
                            "threadId": "thread-123",
                            "turnId": "turn-1",
                            "item": {
                                "id": "cmd-1",
                                "type": "commandExecution",
                                "command": "pytest -q",
                                "commandActions": [],
                                "cwd": str(repo_path),
                                "status": "inProgress",
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-123",
                            "turnId": "turn-1",
                            "item": {
                                "id": "file-1",
                                "type": "fileChange",
                                "status": "completed",
                                "changes": [
                                    {"path": "README.md"},
                                    {"path": "src/app.py"},
                                ],
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "method": "thread/tokenUsage/updated",
                        "params": {
                            "threadId": "thread-123",
                            "turnId": "turn-1",
                            "tokenUsage": {
                                "last": {
                                    "cachedInputTokens": 0,
                                    "inputTokens": 10,
                                    "outputTokens": 20,
                                    "reasoningOutputTokens": 0,
                                    "totalTokens": 30,
                                },
                                "total": {
                                    "cachedInputTokens": 0,
                                    "inputTokens": 10,
                                    "outputTokens": 20,
                                    "reasoningOutputTokens": 0,
                                    "totalTokens": 30,
                                },
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-123",
                            "turnId": "turn-1",
                            "item": {
                                "id": "msg-1",
                                "type": "agentMessage",
                                "phase": "assistant",
                                "text": "",
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-123",
                            "turn": {"id": "turn-1", "status": "completed", "items": []},
                        },
                    }
                )
                + "\n",
            ]
        )
        popen = _PopenRecorder(process)
        runner = CodexRunner(popen_factory=popen, clock=lambda: 0.0)

        events = list(runner.run(config))

        self.assertEqual(popen.calls[0][0][0], ["codex", "app-server", "--listen", "stdio://"])
        self.assertEqual(popen.calls[0][1]["cwd"], str(repo_path))
        self.assertEqual(
            [event.event_type for event in events],
            [
                "agent.started",
                "agent.command",
                "agent.file_change",
                "agent.file_change",
                "agent.cost_update",
                "agent.message",
                "signal.progress",
                "agent.completed",
            ],
        )
        self.assertEqual(events[1].payload["command"], "pytest -q")
        self.assertEqual(events[2].payload, {"tool": "codex.fileChange", "path": "README.md"})
        self.assertEqual(events[4].payload["cumulative_tokens"], 30)
        self.assertEqual(events[5].payload["text"], "Working on the task.\nTASK_COMPLETE")
        self.assertEqual(events[6].payload, {"message": "halfway"})
        self.assertEqual(events[7].payload["session_id"], "thread-123")
        self.assertEqual(events[7].payload["token_count"], 30)

        requests = [
            json.loads(line)
            for line in process.stdin.lines
            if line.strip()
        ]
        self.assertEqual(
            [request["method"] for request in requests if "method" in request],
            ["initialize", "thread/start", "turn/start"],
        )
        self.assertEqual(requests[1]["params"]["sandbox"], "workspace-write")
        self.assertEqual(requests[1]["params"]["approvalPolicy"], "on-request")
        self.assertEqual(requests[2]["params"]["threadId"], "thread-123")
        self.assertEqual(requests[2]["params"]["effort"], "medium")

    def test_run_resumes_existing_thread_and_auto_denies_disallowed_commands(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo_path = Path(temp_dir.name)
        config = self.create_config(
            repo_path,
            session_id="thread-123",
            disallowed_tools=("Bash",),
        )
        process = _FakeProcess(
            lines=[
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"userAgent": "codex-tests"}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {"id": "thread-123"},
                            "approvalPolicy": "on-request",
                            "approvalsReviewer": "user",
                            "cwd": str(repo_path),
                            "model": "gpt-5.4",
                            "modelProvider": "openai",
                            "sandbox": "workspace-write",
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {"turn": {"id": "turn-2", "status": "inProgress"}}})
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "req-1",
                        "method": "item/commandExecution/requestApproval",
                        "params": {
                            "threadId": "thread-123",
                            "turnId": "turn-2",
                            "itemId": "cmd-1",
                            "reason": "Need shell access",
                            "availableDecisions": ["accept", "decline"],
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-123",
                            "turn": {
                                "id": "turn-2",
                                "status": "failed",
                                "items": [],
                                "error": {"message": "Command approval denied."},
                            },
                        },
                    }
                )
                + "\n",
            ]
        )
        runner = CodexRunner(popen_factory=_PopenRecorder(process), clock=lambda: 0.0)

        events = list(runner.run(config))

        self.assertEqual([event.event_type for event in events], ["agent.started", "agent.error"])
        self.assertEqual(events[1].payload["error"], "Command approval denied.")
        requests = [
            json.loads(line)
            for line in process.stdin.lines
            if line.strip()
        ]
        self.assertEqual(requests[1]["method"], "thread/resume")
        self.assertEqual(requests[1]["params"]["threadId"], "thread-123")
        self.assertEqual(requests[-1]["id"], "req-1")
        self.assertEqual(requests[-1]["result"], {"decision": "decline"})

    def test_run_raises_infrastructure_error_when_app_server_exits_early(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo_path = Path(temp_dir.name)
        config = self.create_config(repo_path)
        process = _FakeProcess(
            lines=[
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"userAgent": "codex-tests"}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {"id": "thread-123"},
                            "approvalPolicy": "on-request",
                            "approvalsReviewer": "user",
                            "cwd": str(repo_path),
                            "model": "gpt-5.4",
                            "modelProvider": "openai",
                            "sandbox": "workspace-write",
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {"turn": {"id": "turn-1", "status": "inProgress"}}})
                + "\n",
            ],
            returncode=2,
            stderr="app server crashed",
        )
        runner = CodexRunner(popen_factory=_PopenRecorder(process), clock=lambda: 0.0)

        with self.assertRaises(InfrastructureError) as exc:
            list(runner.run(config))

        self.assertIn("app server crashed", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
