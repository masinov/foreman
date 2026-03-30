"""Codex JSON-RPC backend for Foreman."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
import json
from pathlib import Path
import shlex
import subprocess
import time
from typing import Any

from .base import AgentEvent, AgentRunConfig, AgentRunner, InfrastructureError
from .signals import extract_signal_events

_WRITE_TOOL_NAMES = {"Write", "Edit", "NotebookEdit"}


class CodexRunner(AgentRunner):
    """Execute Codex through the app-server JSON-RPC protocol."""

    def __init__(
        self,
        executable: str = "codex",
        *,
        popen_factory: Any = subprocess.Popen,
        clock: Any = time.monotonic,
    ) -> None:
        self.executable = executable
        self._popen_factory = popen_factory
        self._clock = clock

    def build_command(self) -> list[str]:
        """Build the Codex app-server command."""

        return [self.executable, "app-server", "--listen", "stdio://"]

    def run(self, config: AgentRunConfig) -> Iterator[AgentEvent]:
        """Run one Codex turn and yield normalized agent events."""

        client = _JsonRpcClient(
            self.build_command(),
            cwd=config.working_dir,
            popen_factory=self._popen_factory,
        )
        start_time = self._clock()
        thread_id: str | None = None
        token_count = 0
        saw_terminal_event = False
        message_buffers: dict[str, list[str]] = {}

        try:
            thread_method, thread_params = _build_thread_request(config)
            thread_result = client.call(thread_method, thread_params)
            thread = thread_result.get("thread")
            if not isinstance(thread, dict):
                raise InfrastructureError("Codex thread start response did not include thread metadata.")
            thread_id = _optional_string(thread.get("id"))
            if not thread_id:
                raise InfrastructureError("Codex thread start response did not include a thread id.")

            turn_params = {
                "threadId": thread_id,
                "input": [{"type": "text", "text": config.prompt}],
            }
            effort = _optional_string(
                config.extra_flags.get("effort", config.extra_flags.get("reasoning_effort"))
            )
            if effort:
                turn_params["effort"] = effort
            turn_result = client.call("turn/start", turn_params)
            turn = turn_result.get("turn")
            if not isinstance(turn, dict):
                raise InfrastructureError("Codex turn start response did not include turn metadata.")
            turn_id = _optional_string(turn.get("id"))
            if not turn_id:
                raise InfrastructureError("Codex turn start response did not include a turn id.")

            yield AgentEvent(
                "agent.started",
                payload={
                    "command": shlex.join(client.command),
                    "cwd": str(config.working_dir),
                    "session_id": thread_id,
                },
            )

            while True:
                message = client.next_message()
                if not isinstance(message, dict):
                    continue

                request_id = message.get("id")
                method = _optional_string(message.get("method"))
                if method is None:
                    continue

                if request_id is not None:
                    response = _approval_response(method, message.get("params"), config)
                    if response is not None:
                        client.respond(request_id, response)
                    else:
                        client.respond(request_id, {})
                    continue

                params = message.get("params")
                if not isinstance(params, dict):
                    continue
                if params.get("threadId") not in {None, thread_id}:
                    continue

                if method == "item/agentMessage/delta":
                    item_id = _optional_string(params.get("itemId"))
                    delta = _optional_string(params.get("delta"))
                    if item_id and delta:
                        message_buffers.setdefault(item_id, []).append(delta)
                elif method == "thread/tokenUsage/updated":
                    total = params.get("tokenUsage")
                    if isinstance(total, dict):
                        total_usage = total.get("total")
                        if isinstance(total_usage, dict):
                            token_count = _coerce_int(
                                total_usage.get("totalTokens"),
                                default=token_count,
                            )
                            yield AgentEvent(
                                "agent.cost_update",
                                payload={
                                    "cumulative_usd": 0.0,
                                    "cumulative_tokens": token_count,
                                },
                            )
                elif method in {"item/started", "item/completed"}:
                    item = params.get("item")
                    if isinstance(item, dict):
                        yield from self._parse_item_event(
                            method,
                            item,
                            message_buffers=message_buffers,
                            working_dir=config.working_dir,
                        )
                elif method == "turn/completed":
                    completed_turn = params.get("turn")
                    if not isinstance(completed_turn, dict):
                        raise InfrastructureError("Codex completed turn notification was malformed.")
                    duration_ms = int((self._clock() - start_time) * 1000)
                    status = _optional_string(completed_turn.get("status")) or "completed"
                    if status == "completed":
                        yield AgentEvent(
                            "agent.completed",
                            payload={
                                "session_id": thread_id,
                                "cost_usd": 0.0,
                                "duration_ms": duration_ms,
                                "token_count": token_count,
                            },
                        )
                    else:
                        error_payload = completed_turn.get("error")
                        error_message = _turn_error_message(error_payload)
                        yield AgentEvent(
                            "agent.error",
                            payload={
                                "session_id": thread_id,
                                "cost_usd": 0.0,
                                "duration_ms": duration_ms,
                                "token_count": token_count,
                                "error": error_message,
                            },
                        )
                    saw_terminal_event = True
                    return
                elif method == "error":
                    detail = _turn_error_message(params.get("error"))
                    raise InfrastructureError(detail)

                gate_event = self._check_gates(
                    client,
                    config,
                    start_time=start_time,
                )
                if gate_event is not None:
                    yield gate_event
                    return
        except OSError as exc:
            raise InfrastructureError(f"Failed to launch Codex app server: {exc}") from exc
        except RuntimeError as exc:
            raise InfrastructureError(str(exc)) from exc
        finally:
            client.close()

        if not saw_terminal_event:
            raise InfrastructureError("Codex turn ended without a terminal result notification.")

    def _parse_item_event(
        self,
        method: str,
        item: dict[str, Any],
        *,
        message_buffers: dict[str, list[str]],
        working_dir: Path,
    ) -> tuple[AgentEvent, ...]:
        item_type = _optional_string(item.get("type")) or "unknown"
        item_id = _optional_string(item.get("id")) or ""

        if item_type == "agentMessage" and method == "item/completed":
            text = _optional_string(item.get("text"))
            if not text and item_id:
                text = "".join(message_buffers.pop(item_id, []))
            elif item_id:
                message_buffers.pop(item_id, None)
            if not text:
                return ()
            cleaned_text, signal_events = extract_signal_events(text)
            events: list[AgentEvent] = []
            if cleaned_text:
                payload = {"text": cleaned_text}
                phase = _optional_string(item.get("phase"))
                if phase:
                    payload["phase"] = phase
                events.append(AgentEvent("agent.message", payload=payload))
            events.extend(signal_events)
            return tuple(events)

        if item_type == "commandExecution" and method == "item/started":
            return (
                AgentEvent(
                    "agent.command",
                    payload={
                        "command": _optional_string(item.get("command")) or "",
                        "cwd": _optional_string(item.get("cwd")) or str(working_dir),
                    },
                ),
            )

        if item_type == "fileChange" and method == "item/completed":
            changes = item.get("changes")
            if not isinstance(changes, list):
                return ()
            events = []
            for change in changes:
                if not isinstance(change, dict):
                    continue
                path = _optional_string(change.get("path"))
                if not path:
                    continue
                events.append(
                    AgentEvent(
                        "agent.file_change",
                        payload={
                            "tool": "codex.fileChange",
                            "path": path,
                        },
                    )
                )
            return tuple(events)

        if method == "item/completed":
            return (
                AgentEvent(
                    "agent.tool_use",
                    payload={"tool": item_type, "input": item},
                ),
            )
        return ()

    def _check_gates(
        self,
        client: "_JsonRpcClient",
        config: AgentRunConfig,
        *,
        start_time: float,
    ) -> AgentEvent | None:
        elapsed_seconds = self._clock() - start_time
        if config.timeout_seconds > 0 and elapsed_seconds > config.timeout_seconds:
            client.kill()
            return AgentEvent(
                "agent.killed",
                payload={
                    "reason": "Run exceeded time limit.",
                    "gate_type": "time",
                },
            )
        return None


class _JsonRpcClient:
    """Minimal JSON-RPC client for the Codex app server."""

    def __init__(
        self,
        command: list[str],
        *,
        cwd: Path,
        popen_factory: Any,
    ) -> None:
        self.command = list(command)
        try:
            self.proc = popen_factory(
                self.command,
                cwd=str(cwd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise InfrastructureError(f"Failed to launch Codex app server: {exc}") from exc
        self._next_id = 1
        self._pending_messages: deque[dict[str, Any]] = deque()
        self.call("initialize", {"clientInfo": {"name": "foreman", "version": "0.1.0"}})

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        while True:
            message = self._read_message()
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise RuntimeError(f"Codex RPC error for {method}: {message['error']}")
                result = message.get("result")
                if isinstance(result, dict):
                    return result
                return {}
            self._pending_messages.append(message)

    def respond(self, request_id: Any, result: dict[str, Any]) -> None:
        self._write_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        )

    def next_message(self) -> dict[str, Any]:
        if self._pending_messages:
            return self._pending_messages.popleft()
        return self._read_message()

    def kill(self) -> None:
        _kill_process(self.proc)

    def close(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _write_json(self, payload: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()

    def _read_message(self) -> dict[str, Any]:
        assert self.proc.stdout is not None
        while True:
            line = self.proc.stdout.readline()
            if not line:
                stderr = ""
                if self.proc.stderr is not None:
                    stderr = self.proc.stderr.read().strip()
                if self.proc.poll() not in {None, 0}:
                    detail = stderr or f"Codex app server exited with code {self.proc.returncode}."
                    raise InfrastructureError(detail)
                raise InfrastructureError("Codex app server closed unexpectedly.")
            stripped = line.strip()
            if not stripped:
                continue
            try:
                message = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise InfrastructureError(f"Codex app server emitted invalid JSON: {stripped}") from exc
            if isinstance(message, dict):
                return message
            raise InfrastructureError("Codex app server emitted a non-object JSON-RPC message.")


def _build_thread_request(config: AgentRunConfig) -> tuple[str, dict[str, Any]]:
    approval_policy = _optional_string(config.extra_flags.get("approval_policy")) or "on-request"
    sandbox = _optional_string(config.extra_flags.get("sandbox")) or _sandbox_mode_for(config)
    params: dict[str, Any] = {
        "cwd": str(config.working_dir),
        "approvalPolicy": approval_policy,
        "sandbox": sandbox,
    }
    if config.model:
        params["model"] = config.model
    developer_instructions = _optional_string(config.extra_flags.get("developer_instructions"))
    if developer_instructions:
        params["developerInstructions"] = developer_instructions
    personality = _optional_string(config.extra_flags.get("personality"))
    if personality:
        params["personality"] = personality
    model_provider = _optional_string(config.extra_flags.get("model_provider"))
    if model_provider:
        params["modelProvider"] = model_provider
    service_tier = _optional_string(config.extra_flags.get("service_tier"))
    if service_tier:
        params["serviceTier"] = service_tier
    if config.session_id:
        params["threadId"] = config.session_id
        return ("thread/resume", params)
    return ("thread/start", params)


def _sandbox_mode_for(config: AgentRunConfig) -> str:
    if config.permission_mode == "bypassPermissions":
        return "workspace-write"
    return "read-only"


def _approval_response(
    method: str,
    params: Any,
    config: AgentRunConfig,
) -> dict[str, Any] | None:
    if not isinstance(params, dict):
        return None

    if method == "item/commandExecution/requestApproval":
        allowed = "Bash" not in config.disallowed_tools
        available_decisions = params.get("availableDecisions")
        cancel_decision = "cancel"
        if isinstance(available_decisions, list) and "decline" in available_decisions:
            cancel_decision = "decline"
        return {"decision": "accept" if allowed else cancel_decision}

    if method == "item/fileChange/requestApproval":
        allowed = not any(tool in config.disallowed_tools for tool in _WRITE_TOOL_NAMES)
        available_decisions = params.get("availableDecisions")
        cancel_decision = "cancel"
        if isinstance(available_decisions, list) and "decline" in available_decisions:
            cancel_decision = "decline"
        return {"decision": "accept" if allowed else cancel_decision}

    if method == "item/permissions/requestApproval":
        allowed = config.permission_mode == "bypassPermissions"
        permissions = params.get("permissions")
        if not isinstance(permissions, dict):
            permissions = {}
        return {
            "permissions": permissions if allowed else {},
            "scope": "turn",
        }

    return None


def _turn_error_message(error_payload: Any) -> str:
    if isinstance(error_payload, dict):
        message = _optional_string(error_payload.get("message"))
        detail = _optional_string(error_payload.get("additionalDetails"))
        if message and detail:
            return f"{message}\n{detail}"
        if message:
            return message
        if detail:
            return detail
    if isinstance(error_payload, str):
        return error_payload
    return "Codex turn failed."


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _coerce_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def _kill_process(proc: Any) -> None:
    try:
        proc.kill()
    except OSError:
        pass
