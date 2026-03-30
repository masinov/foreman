"""Codex JSON-RPC backend for Foreman."""

from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
import shlex
import subprocess
import time
from typing import Any

from .base import AgentEvent, AgentRunConfig, AgentRunner, InfrastructureError
from .signals import extract_signal_events

_FILE_TOOLS = {"Read", "Write", "Edit", "NotebookEdit"}


class CodexRunner(AgentRunner):
    """Execute OpenAI Codex in JSON-RPC mode and normalize its events."""

    SUPPORTED_MODELS = ("gpt-5.4", "o3")

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

    def build_command(self, config: AgentRunConfig) -> list[str]:
        """Build the Codex CLI command for one run."""

        command = [
            self.executable,
            "--json-rpc",
            "--quiet",
        ]
        if config.session_id:
            command.extend(["--session", config.session_id])
        if config.model:
            command.extend(["--model", config.model])
        if config.disallowed_tools:
            command.extend(
                ["--disallowed-tools", ",".join(config.disallowed_tools)]
            )
        command.extend(_extra_flag_args(config.extra_flags))
        return command

    def run(self, config: AgentRunConfig) -> Iterator[AgentEvent]:
        """Run Codex and yield normalized agent events."""

        command = self.build_command(config)
        try:
            proc = self._popen_factory(
                command,
                cwd=str(config.working_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise InfrastructureError(f"Failed to launch Codex: {exc}") from exc

        assert proc.stdin is not None
        assert proc.stdout is not None
        start_time = self._clock()
        last_cost_usd = 0.0
        saw_terminal_event = False

        # Send the prompt as an RPC request
        request = {
            "jsonrpc": "2.0",
            "method": "execute",
            "params": {
                "prompt": config.prompt,
                "permission_mode": config.permission_mode,
            },
            "id": 1,
        }
        try:
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.close()
        except OSError as exc:
            try:
                proc.kill()
            except OSError:
                pass
            raise InfrastructureError(f"Failed to write prompt to Codex: {exc}") from exc

        yield AgentEvent(
            "agent.started",
            payload={
                "command": shlex.join(command),
                "cwd": str(config.working_dir),
            },
        )

        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue

            for event in self._parse_jsonrpc_line(
                line,
                working_dir=config.working_dir,
            ):
                if event.event_type == "agent.cost_update":
                    last_cost_usd = _coerce_float(
                        event.payload.get("cumulative_usd"),
                        default=last_cost_usd,
                    )
                if event.event_type in {"agent.completed", "agent.error"}:
                    saw_terminal_event = True
                yield event

                gate_event = self._check_gates(
                    proc,
                    config,
                    start_time=start_time,
                    last_cost_usd=last_cost_usd,
                )
                if gate_event is not None:
                    yield gate_event
                    return

        proc.wait()
        stderr = proc.stderr.read().strip() if proc.stderr is not None else ""
        if saw_terminal_event:
            return

        if proc.returncode != 0:
            detail = stderr or f"Codex exited with code {proc.returncode}."
            raise InfrastructureError(detail)
        raise InfrastructureError("Codex stream ended without a terminal result event.")

    def _parse_jsonrpc_line(
        self,
        line: str,
        *,
        working_dir: Path,
    ) -> tuple[AgentEvent, ...]:
        """Parse a JSON-RPC response line into agent events."""

        if line.startswith("FOREMAN_SIGNAL:"):
            _, signal_events = extract_signal_events(line)
            return signal_events

        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            return (
                AgentEvent(
                    "agent.message",
                    payload={"text": line, "phase": "stream"},
                ),
            )

        if not isinstance(response, dict):
            return ()

        # Handle JSON-RPC notifications (streaming events)
        if "method" in response:
            return self._parse_notification(response, working_dir=working_dir)

        # Handle JSON-RPC response (final result)
        if "result" in response or "error" in response:
            return self._parse_response(response)

        return (
            AgentEvent(
                "agent.tool_use",
                payload={"tool": "codex.unknown", "input": response},
            ),
        )

    def _parse_notification(
        self,
        notification: dict[str, Any],
        *,
        working_dir: Path,
    ) -> tuple[AgentEvent, ...]:
        """Parse a JSON-RPC notification into agent events."""

        method = notification.get("method", "")
        params = notification.get("params", {})

        if method == "text_delta":
            text = _optional_string(params.get("text"))
            if not text:
                return ()
            cleaned_text, signal_events = extract_signal_events(text)
            events: list[AgentEvent] = []
            if cleaned_text:
                events.append(
                    AgentEvent(
                        "agent.message",
                        payload={"text": cleaned_text, "phase": "assistant"},
                    )
                )
            events.extend(signal_events)
            return tuple(events)

        if method == "tool_call":
            tool_name = str(params.get("name", "unknown"))
            tool_input = params.get("arguments", {})
            if not isinstance(tool_input, dict):
                tool_input = {}

            if tool_name == "Bash":
                return (
                    AgentEvent(
                        "agent.command",
                        payload={
                            "command": str(tool_input.get("command", "")),
                            "cwd": str(tool_input.get("cwd", working_dir)),
                        },
                    ),
                )
            if tool_name in _FILE_TOOLS:
                return (
                    AgentEvent(
                        "agent.file_change",
                        payload={
                            "tool": tool_name,
                            "path": str(
                                tool_input.get(
                                    "file_path",
                                    tool_input.get("path", ""),
                                )
                            ),
                        },
                    ),
                )
            return (
                AgentEvent(
                    "agent.tool_use",
                    payload={"tool": tool_name, "input": tool_input},
                ),
            )

        if method == "cost_update":
            cost = _coerce_float(params.get("cost_usd"), default=0.0)
            tokens = _coerce_int(params.get("tokens"), default=0)
            return (
                AgentEvent(
                    "agent.cost_update",
                    payload={
                        "cumulative_usd": cost,
                        "cumulative_tokens": tokens,
                    },
                ),
            )

        if method == "approval_request":
            return (
                AgentEvent(
                    "agent.approval_request",
                    payload={
                        "type": params.get("type", "tool"),
                        "tool": params.get("tool"),
                        "command": params.get("command"),
                        "message": params.get("message"),
                    },
                ),
            )

        # Unknown notification type
        return (
            AgentEvent(
                "agent.tool_use",
                payload={"tool": f"codex.{method}", "input": params},
            ),
        )

    def _parse_response(self, response: dict[str, Any]) -> tuple[AgentEvent, ...]:
        """Parse a JSON-RPC final response into agent events."""

        events: list[AgentEvent] = []

        if "error" in response:
            error = response["error"]
            message = str(error.get("message", "Unknown error"))
            events.append(
                AgentEvent(
                    "agent.error",
                    payload={"error": message, "code": error.get("code")},
                )
            )
            return tuple(events)

        result = response.get("result", {})
        if not isinstance(result, dict):
            result = {}

        # Extract result text
        result_text = _optional_string(result.get("text") or result.get("result"))
        if result_text:
            cleaned_text, signal_events = extract_signal_events(result_text)
            if cleaned_text:
                events.append(
                    AgentEvent(
                        "agent.message",
                        payload={"text": cleaned_text, "phase": "result"},
                    )
                )
            events.extend(signal_events)

        # Build completion event
        payload = {
            "session_id": _optional_string(result.get("session_id")),
            "cost_usd": _coerce_float(
                result.get("cost_usd", result.get("total_cost_usd")),
                default=0.0,
            ),
            "duration_ms": _coerce_int(result.get("duration_ms")),
            "token_count": _extract_total_tokens(result),
        }

        if bool(result.get("is_error")):
            payload["error"] = result_text or "Codex returned an error."
            events.append(AgentEvent("agent.error", payload=payload))
        else:
            events.append(AgentEvent("agent.completed", payload=payload))

        return tuple(events)

    def _check_gates(
        self,
        proc: Any,
        config: AgentRunConfig,
        *,
        start_time: float,
        last_cost_usd: float,
    ) -> AgentEvent | None:
        elapsed_seconds = self._clock() - start_time
        if config.timeout_seconds > 0 and elapsed_seconds > config.timeout_seconds:
            _kill_process(proc)
            return AgentEvent(
                "agent.killed",
                payload={
                    "reason": "Run exceeded time limit.",
                    "gate_type": "time",
                },
            )

        if config.max_cost_usd > 0 and last_cost_usd > config.max_cost_usd:
            _kill_process(proc)
            return AgentEvent(
                "agent.killed",
                payload={
                    "reason": "Run exceeded cost limit.",
                    "gate_type": "cost",
                },
            )
        return None


def _extra_flag_args(flags: dict[str, Any]) -> list[str]:
    args: list[str] = []
    for key, value in flags.items():
        if value in (None, False, ""):
            continue
        flag = f"--{str(key).replace('_', '-')}"
        if value is True:
            args.append(flag)
            continue
        args.extend([flag, str(value)])
    return args


def _extract_total_tokens(result: dict[str, Any]) -> int:
    direct = _coerce_int(result.get("total_tokens"))
    if direct is not None:
        return direct
    usage = result.get("usage")
    if isinstance(usage, dict):
        usage_total = _coerce_int(usage.get("total_tokens"))
        if usage_total is not None:
            return usage_total
        input_tokens = _coerce_int(usage.get("input_tokens"), default=0) or 0
        output_tokens = _coerce_int(usage.get("output_tokens"), default=0) or 0
        return input_tokens + output_tokens
    return 0


def _kill_process(proc: Any) -> None:
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait()
    except OSError:
        pass


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: Any, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _coerce_int(value: Any, *, default: int | None = None) -> int | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default
