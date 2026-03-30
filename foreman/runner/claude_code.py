"""Claude Code stream-json backend for Foreman."""

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


class ClaudeCodeRunner(AgentRunner):
    """Execute Claude Code in stream-json mode and normalize its events."""

    def __init__(
        self,
        executable: str = "claude",
        *,
        popen_factory: Any = subprocess.Popen,
        clock: Any = time.monotonic,
    ) -> None:
        self.executable = executable
        self._popen_factory = popen_factory
        self._clock = clock

    def build_command(self, config: AgentRunConfig) -> list[str]:
        """Build the Claude CLI command for one run."""

        command = [
            self.executable,
            "--print",
            "--verbose",
            "--output-format",
            "stream-json",
            "--permission-mode",
            config.permission_mode,
        ]
        if config.session_id:
            command.extend(["--resume", config.session_id])
        if config.model:
            command.extend(["--model", config.model])
        if config.disallowed_tools:
            command.extend(
                ["--disallowed-tools", ",".join(config.disallowed_tools)]
            )
        command.extend(_extra_flag_args(config.extra_flags))
        return command

    def run(self, config: AgentRunConfig) -> Iterator[AgentEvent]:
        """Run Claude Code and yield normalized agent events."""

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
            raise InfrastructureError(f"Failed to launch Claude Code: {exc}") from exc

        assert proc.stdin is not None
        assert proc.stdout is not None
        start_time = self._clock()
        last_cost_usd = 0.0
        saw_terminal_event = False

        try:
            proc.stdin.write(config.prompt)
            proc.stdin.close()
        except OSError as exc:
            try:
                proc.kill()
            except OSError:
                pass
            raise InfrastructureError(f"Failed to write prompt to Claude Code: {exc}") from exc

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

            for event in self._parse_stream_line(
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
            detail = stderr or f"Claude Code exited with code {proc.returncode}."
            raise InfrastructureError(detail)
        raise InfrastructureError("Claude Code stream ended without a terminal result event.")

    def _parse_stream_line(
        self,
        line: str,
        *,
        working_dir: Path,
    ) -> tuple[AgentEvent, ...]:
        timestamp_events: list[AgentEvent] = []

        if line.startswith("FOREMAN_SIGNAL:"):
            _, signal_events = extract_signal_events(line)
            return signal_events

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return (
                AgentEvent(
                    "agent.message",
                    payload={"text": line, "phase": "stream"},
                ),
            )
        if not isinstance(event, dict):
            return ()

        event_type = str(event.get("type", ""))
        if event_type == "assistant":
            message = event.get("message", event)
            content = message.get("content", ())
            if not isinstance(content, list):
                return ()
            for block in content:
                if not isinstance(block, dict):
                    continue
                timestamp_events.extend(
                    self._parse_assistant_block(block, working_dir=working_dir)
                )
            cost_event = _build_cost_update_event(event)
            if cost_event is not None:
                timestamp_events.append(cost_event)
            return tuple(timestamp_events)

        if event_type == "result":
            result_text = _optional_string(event.get("result"))
            if result_text:
                cleaned_text, signal_events = extract_signal_events(result_text)
                if cleaned_text:
                    timestamp_events.append(
                        AgentEvent(
                            "agent.message",
                            payload={"text": cleaned_text, "phase": "result"},
                        )
                    )
                timestamp_events.extend(signal_events)
            cost_event = _build_cost_update_event(event)
            if cost_event is not None:
                timestamp_events.append(cost_event)

            payload = {
                "session_id": _optional_string(event.get("session_id")),
                "cost_usd": _coerce_float(
                    event.get("total_cost_usd", event.get("cost_usd")),
                    default=0.0,
                ),
                "duration_ms": _coerce_int(event.get("duration_ms")),
                "token_count": _extract_total_tokens(event),
            }
            if bool(event.get("is_error")):
                payload["error"] = result_text or "Claude Code returned an error."
                timestamp_events.append(AgentEvent("agent.error", payload=payload))
            else:
                timestamp_events.append(AgentEvent("agent.completed", payload=payload))
            return tuple(timestamp_events)

        cost_event = _build_cost_update_event(event)
        if cost_event is not None:
            return (cost_event,)
        return (
            AgentEvent(
                "agent.tool_use",
                payload={"tool": "claude.stream_event", "input": event},
            ),
        )

    def _parse_assistant_block(
        self,
        block: dict[str, Any],
        *,
        working_dir: Path,
    ) -> tuple[AgentEvent, ...]:
        block_type = str(block.get("type", ""))
        if block_type == "text":
            text = _optional_string(block.get("text"))
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

        if block_type != "tool_use":
            return ()
        tool_name = str(block.get("name", "unknown"))
        tool_input = block.get("input", {})
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


def _build_cost_update_event(event: dict[str, Any]) -> AgentEvent | None:
    cost = event.get("total_cost_usd", event.get("cost_usd"))
    has_token_info = _has_token_data(event)
    if cost is None and not has_token_info:
        return None
    tokens = _extract_total_tokens(event) if has_token_info else 0
    payload = {
        "cumulative_usd": _coerce_float(cost, default=0.0),
        "cumulative_tokens": tokens or 0,
    }
    return AgentEvent("agent.cost_update", payload=payload)


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


def _extract_total_tokens(event: dict[str, Any]) -> int:
    direct = _coerce_int(event.get("total_tokens"))
    if direct is not None:
        return direct
    usage = event.get("usage")
    if isinstance(usage, dict):
        usage_total = _coerce_int(usage.get("total_tokens"))
        if usage_total is not None:
            return usage_total
        input_tokens = _coerce_int(usage.get("input_tokens"), default=0) or 0
        output_tokens = _coerce_int(usage.get("output_tokens"), default=0) or 0
        return input_tokens + output_tokens
    return 0


def _has_token_data(event: dict[str, Any]) -> bool:
    if "total_tokens" in event:
        return True
    usage = event.get("usage")
    if not isinstance(usage, dict):
        return False
    return any(key in usage for key in ("total_tokens", "input_tokens", "output_tokens"))


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
