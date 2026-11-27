"""Unit coverage for the native Codex runner."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import os
import unittest
from unittest.mock import patch

from foreman.runner import AgentRunConfig, CodexRunner, InfrastructureError, PreflightError
from foreman.runner.env import NON_INTERACTIVE_ENV
from foreman.definitions.roles import COMMAND_TOOLS
from foreman.runner.base import SandboxPolicy
from foreman.runner.codex import (
    _JsonRpcClient,
    _approval_response,
    _build_thread_request,
    check_thread_started,
)


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

    def test_json_rpc_client_passes_merged_environment_only_when_configured(self) -> None:
        process = _FakeProcess(
            lines=[
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"userAgent": "codex-tests"}}) + "\n",
            ]
        )
        popen = _PopenRecorder(process)

        client = _JsonRpcClient(
            ["codex", "app-server", "--listen", "stdio://"],
            cwd=Path("/tmp"),
            popen_factory=popen,
            env={"FOREMAN_CODEX_TEST": "enabled"},
        )
        client.close()

        env = popen.calls[0][1]["env"]
        self.assertIsInstance(env, dict)
        self.assertEqual(env["FOREMAN_CODEX_TEST"], "enabled")

    def test_the_app_server_is_started_without_the_engines_secrets(self) -> None:
        process = _FakeProcess(
            lines=[
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"userAgent": "codex-tests"}}) + "\n",
            ]
        )
        popen = _PopenRecorder(process)
        host = {"PATH": "/usr/bin", "OPENAI_API_KEY": "key", "GITHUB_TOKEN": "forge-secret"}

        with patch.dict(os.environ, host, clear=True):
            client = _JsonRpcClient(
                ["codex", "app-server", "--listen", "stdio://"],
                cwd=Path("/tmp"),
                popen_factory=popen,
                env={"EXTRA": "from the role"},
            )
            client.close()

        self.assertEqual(
            popen.calls[0][1]["env"],
            {
                "PATH": "/usr/bin",
                "OPENAI_API_KEY": "key",
                **NON_INTERACTIVE_ENV,
                "EXTRA": "from the role",
            },
        )

    def test_the_app_server_gets_no_editor_pager_or_prompt_unless_the_role_sets_one(self) -> None:
        process = _FakeProcess(
            lines=[json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"userAgent": "t"}}) + "\n"]
        )
        popen = _PopenRecorder(process)

        client = _JsonRpcClient(
            ["codex", "app-server", "--listen", "stdio://"],
            cwd=Path("/tmp"),
            popen_factory=popen,
            env={"PAGER": "less"},
        )
        client.close()

        env = popen.calls[0][1]["env"]
        for name in ("GIT_EDITOR", "EDITOR", "VISUAL"):
            self.assertEqual(env[name], "true")
        self.assertEqual(env["GIT_PAGER"], "cat")
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(env["PAGER"], "less")

    def test_a_role_with_an_allowlist_is_refused_what_is_not_on_it(self) -> None:
        from dataclasses import replace

        from foreman.runner.codex import _approval_response

        config = replace(
            self.create_config(Path("/tmp")), allowed_tools=("Read", "Grep"), disallowed_tools=()
        )
        command = _approval_response("item/commandExecution/requestApproval", {}, config)
        change = _approval_response("item/fileChange/requestApproval", {}, config)

        self.assertEqual(command, {"decision": "cancel"})
        self.assertEqual(change, {"decision": "cancel"})

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
        runner = CodexRunner(
            popen_factory=popen,
            clock=lambda: 0.0,
            which=lambda _: "/usr/bin/codex",
        )

        events = list(runner.run(config))

        self.assertEqual(popen.calls[0][0][0], ["codex", "app-server", "--listen", "stdio://"])
        self.assertEqual(popen.calls[0][1]["cwd"], str(repo_path))
        self.assertEqual(
            [event.event_type for event in events],
            [
                "agent.started",
                "agent.raw_output",
                "agent.raw_output",
                "agent.command",
                "agent.raw_output",
                "agent.file_change",
                "agent.file_change",
                "agent.raw_output",
                "agent.cost_update",
                "agent.raw_output",
                "agent.message",
                "signal.progress",
                "agent.raw_output",
                "agent.completed",
            ],
        )
        self.assertEqual(events[1].payload["stream"], "rpc")
        self.assertEqual(events[2].payload["stream"], "rpc")
        self.assertEqual(events[3].payload["command"], "pytest -q")
        self.assertEqual(events[4].payload["stream"], "rpc")
        self.assertEqual(events[5].payload, {"tool": "codex.fileChange", "path": "README.md"})
        self.assertEqual(events[7].payload["stream"], "rpc")
        self.assertEqual(events[8].payload["cumulative_tokens"], 30)
        self.assertEqual(events[9].payload["stream"], "rpc")
        self.assertEqual(events[10].payload["text"], "Working on the task.\nTASK_COMPLETE")
        self.assertEqual(events[11].payload, {"message": "halfway"})
        self.assertEqual(events[12].payload["stream"], "rpc")
        self.assertEqual(events[13].payload["session_id"], "thread-123")
        self.assertEqual(events[13].payload["token_count"], 30)

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
                            "approvalPolicy": "untrusted",
                            "approvalsReviewer": "user",
                            "cwd": str(repo_path),
                            "model": "gpt-5.4",
                            "modelProvider": "openai",
                            "sandbox": {"type": "readOnly", "networkAccess": False},
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
        runner = CodexRunner(
            popen_factory=_PopenRecorder(process),
            clock=lambda: 0.0,
            which=lambda _: "/usr/bin/codex",
        )

        events = list(runner.run(config))

        self.assertEqual(
            [event.event_type for event in events],
            ["agent.started", "agent.raw_output", "agent.raw_output", "agent.error"],
        )
        self.assertEqual(events[1].payload["stream"], "rpc")
        self.assertEqual(events[2].payload["stream"], "rpc")
        self.assertEqual(events[3].payload["error"], "Command approval denied.")
        requests = [
            json.loads(line)
            for line in process.stdin.lines
            if line.strip()
        ]
        self.assertEqual(requests[1]["method"], "thread/resume")
        self.assertEqual(requests[1]["params"]["threadId"], "thread-123")
        # A role without a command tool asks about every command, in a
        # read-only sandbox without network; Foreman declines.
        self.assertEqual(requests[1]["params"]["approvalPolicy"], "untrusted")
        self.assertEqual(requests[1]["params"]["sandbox"], "read-only")
        self.assertEqual(
            requests[1]["params"]["config"],
            {
                "sandbox_workspace_write": {"network_access": False},
                "features": {"shell_tool": False, "unified_exec": False},
            },
        )
        self.assertEqual(requests[-1]["id"], "req-1")
        self.assertEqual(requests[-1]["result"], {"decision": "decline"})

    def test_run_raises_preflight_error_when_executable_is_missing(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo_path = Path(temp_dir.name)
        config = self.create_config(repo_path)
        popen = _PopenRecorder(_FakeProcess(lines=[]))
        runner = CodexRunner(
            popen_factory=popen,
            clock=lambda: 0.0,
            which=lambda _: None,
        )

        with self.assertRaises(PreflightError) as exc:
            list(runner.run(config))

        self.assertIn("executable `codex` was not found in PATH", str(exc.exception))
        self.assertEqual(popen.calls, [])

    def test_run_raises_preflight_error_when_thread_start_response_is_malformed(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo_path = Path(temp_dir.name)
        config = self.create_config(repo_path)
        process = _FakeProcess(
            lines=[
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"userAgent": "codex-tests"}}) + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"approvalPolicy": "on-request"}}) + "\n",
            ]
        )
        runner = CodexRunner(
            popen_factory=_PopenRecorder(process),
            clock=lambda: 0.0,
            which=lambda _: "/usr/bin/codex",
        )

        with self.assertRaises(PreflightError) as exc:
            list(runner.run(config))

        self.assertIn("thread start response did not include thread metadata", str(exc.exception))

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
        runner = CodexRunner(
            popen_factory=_PopenRecorder(process),
            clock=lambda: 0.0,
            which=lambda _: "/usr/bin/codex",
        )

        with self.assertRaises(InfrastructureError) as exc:
            list(runner.run(config))

        self.assertIn("app server crashed", str(exc.exception))


class CodexSandboxTests(unittest.TestCase):
    """A sandboxed step runs in Codex's sandbox, and a role without commands asks about each."""

    def config(self, **overrides: object) -> AgentRunConfig:
        values: dict[str, object] = dict(
            backend="codex",
            model="m",
            prompt="go",
            working_dir=Path("/tmp/box"),
            session_id=None,
            permission_mode="bypassPermissions",
            sandbox=SandboxPolicy(),
        )
        values.update(overrides)
        return AgentRunConfig(**values)  # type: ignore[arg-type]

    def test_a_sandboxed_step_runs_workspace_write_without_network_and_is_never_asked(self) -> None:
        method, params = _build_thread_request(self.config())
        self.assertEqual(method, "thread/start")
        self.assertEqual(params["sandbox"], "workspace-write")
        self.assertEqual(params["approvalPolicy"], "never")
        self.assertEqual(params["config"], {"sandbox_workspace_write": {"network_access": False}})

    def test_a_role_flag_cannot_loosen_a_sandboxed_step(self) -> None:
        config = self.config(
            extra_flags={"sandbox": "danger-full-access", "approval_policy": "never"}
        )
        _, params = _build_thread_request(config)
        self.assertEqual(params["sandbox"], "workspace-write")

    def test_a_role_that_runs_no_command_asks_about_each_in_a_read_only_sandbox(self) -> None:
        config = self.config(sandbox=None, disallowed_tools=tuple(COMMAND_TOOLS))
        _, params = _build_thread_request(config)
        self.assertEqual(params["approvalPolicy"], "untrusted")
        self.assertEqual(params["sandbox"], "read-only")
        self.assertEqual(params["config"]["features"], {"shell_tool": False, "unified_exec": False})

    def test_an_ordinary_step_is_started_as_before(self) -> None:
        _, params = _build_thread_request(self.config(sandbox=None))
        self.assertEqual(params["sandbox"], "workspace-write")
        self.assertEqual(params["approvalPolicy"], "on-request")
        self.assertNotIn("config", params)

    def test_every_request_for_a_command_is_declined(self) -> None:
        for config in (
            self.config(),
            self.config(sandbox=None, disallowed_tools=tuple(COMMAND_TOOLS)),
        ):
            with self.subTest(sandbox=config.sandbox):
                answer = _approval_response(
                    "item/commandExecution/requestApproval",
                    {"availableDecisions": ["accept", "decline"]},
                    config,
                )
                self.assertEqual(answer, {"decision": "decline"})
                self.assertEqual(
                    _approval_response("item/permissions/requestApproval", {"permissions": {"network": True}}, config),
                    {"permissions": {}, "scope": "turn"},
                )

    def test_a_sandboxed_step_is_not_given_a_file_change_outside_its_sandbox(self) -> None:
        answer = _approval_response(
            "item/fileChange/requestApproval", {"availableDecisions": ["accept", "decline"]}, self.config()
        )
        self.assertEqual(answer, {"decision": "decline"})

    def test_a_thread_in_another_sandbox_than_asked_is_refused(self) -> None:
        config = self.config()
        good = {
            "approvalPolicy": "never",
            "sandbox": {"type": "workspaceWrite", "networkAccess": False},
        }
        check_thread_started(good, config)
        for bad in (
            {**good, "sandbox": {"type": "dangerFullAccess"}},
            {**good, "sandbox": {"type": "workspaceWrite", "networkAccess": True}},
            {**good, "approvalPolicy": "on-request"},
            {},
        ):
            with self.subTest(bad=bad), self.assertRaisesRegex(InfrastructureError, "did not start the thread"):
                check_thread_started(bad, config)

    def test_an_ordinary_thread_is_not_checked(self) -> None:
        check_thread_started({}, self.config(sandbox=None))


if __name__ == "__main__":
    unittest.main()
