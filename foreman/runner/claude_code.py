"""Claude Code stream-json backend for Foreman."""

from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import time
from typing import Any

from .base import (
    AgentEvent,
    AgentRunConfig,
    AgentRunner,
    InfrastructureError,
    PreflightError,
)
from .process import DEFAULT_TICK_SECONDS, ManagedProcess, popen_kwargs
from .signals import extract_signal_events

_FILE_TOOLS = {"Read", "Write", "Edit", "NotebookEdit"}

# Raw stream lines are persisted for the transcript, capped so one tool result
# (a file read, a long test log) cannot write tens of kilobytes per line.
RAW_LINE_MAX_CHARS = 8000
# Tool results are persisted as a preview; the full text stays in the raw line
# (up to the cap) and, for file edits, in git.
TOOL_RESULT_PREVIEW_CHARS = 500
# ``system`` subtypes that only report progress while the model is working.
# They drive the heartbeat and the gates but are never persisted.
_PROGRESS_SYSTEM_SUBTYPES = frozenset({"thinking_tokens"})
_NOT_JSON = object()



class ClaudeCodeRunner(AgentRunner):
    """Execute Claude Code in stream-json mode and normalize its events."""

    def __init__(
        self,
        executable: str = "claude",
        *,
        popen_factory: Any = subprocess.Popen,
        clock: Any = time.monotonic,
        which: Any = shutil.which,
        tick_seconds: float = DEFAULT_TICK_SECONDS,
    ) -> None:
        self.executable = executable
        self._popen_factory = popen_factory
        self._clock = clock
        self._which = which
        self.tick_seconds = tick_seconds

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
        """Run Claude Code and yield normalized agent events.

        Output is read on a pump thread. While the child is silent the loop
        wakes every ``tick_seconds`` to enforce the time and cost gates and to
        yield an ``agent.tick`` so the orchestrator can heartbeat its lease.
        Whatever ends the generator, the child's process group is terminated.
        """

        self._preflight()
        command = self.build_command(config)
        try:
            proc = self._popen_factory(
                command,
                **popen_kwargs(cwd=config.working_dir, env=config.env),
            )
        except OSError as exc:
            raise PreflightError(
                f"Claude Code preflight failed: unable to launch `{self.executable}`: {exc}"
            ) from exc

        managed = ManagedProcess(proc, name="claude", tick_seconds=self.tick_seconds)
        try:
            assert proc.stdin is not None
            try:
                proc.stdin.write(config.prompt)
                proc.stdin.close()
            except (OSError, ValueError) as exc:
                managed.kill()
                raise PreflightError(
                    f"Claude Code preflight failed: unable to write the initial prompt: {exc}"
                ) from exc

            start_time = self._clock()
            last_cost_usd = 0.0
            saw_terminal_event = False
            saw_assistant_text = False

            yield AgentEvent(
                "agent.started",
                payload={
                    "command": shlex.join(command),
                    "cwd": str(config.working_dir),
                },
            )

            for raw_line in managed.iter_lines():
                if raw_line is None:
                    gate_event = self._check_gates(
                        managed,
                        config,
                        start_time=start_time,
                        last_cost_usd=last_cost_usd,
                    )
                    if gate_event is not None:
                        yield gate_event
                        return
                    yield AgentEvent(
                        "agent.tick",
                        payload={"elapsed_seconds": round(self._clock() - start_time, 1)},
                    )
                    continue

                line = raw_line.strip()
                if not line:
                    continue

                decoded = _decode_stream_line(line)
                progress_events = _progress_events(decoded)
                if progress_events is not None:
                    # Progress lines (thinking-token counters, allowed
                    # rate-limit notices) arrive about twice a second while
                    # the model thinks. They keep the lease heartbeat and the
                    # gates alive but are never persisted.
                    for event in progress_events:
                        yield event
                    gate_event = self._check_gates(
                        managed,
                        config,
                        start_time=start_time,
                        last_cost_usd=last_cost_usd,
                    )
                    if gate_event is not None:
                        yield gate_event
                        return
                    continue

                yield AgentEvent("agent.raw_output", payload=_raw_output_payload(line))

                parsed_events = self._parse_stream_line(
                    line,
                    working_dir=config.working_dir,
                    emit_result_signals=not saw_assistant_text,
                    decoded=decoded,
                )
                if any(
                    event.event_type == "agent.message"
                    and event.payload.get("phase") == "assistant"
                    for event in parsed_events
                ):
                    saw_assistant_text = True
                for event in parsed_events:
                    if event.event_type == "agent.cost_update":
                        last_cost_usd = _coerce_float(
                            event.payload.get("cumulative_usd"),
                            default=last_cost_usd,
                        )
                    if event.event_type in {"agent.completed", "agent.error"}:
                        saw_terminal_event = True
                    yield event

                    gate_event = self._check_gates(
                        managed,
                        config,
                        start_time=start_time,
                        last_cost_usd=last_cost_usd,
                    )
                    if gate_event is not None:
                        yield gate_event
                        return

            managed.wait()
            stderr = managed.stderr_text()
            if stderr:
                for line in stderr.splitlines():
                    yield AgentEvent(
                        "agent.raw_output",
                        payload={"stream": "stderr", "line": line},
                    )
            if saw_terminal_event:
                return

            returncode = managed.poll()
            if returncode not in (0, None):
                detail = stderr or f"Claude Code exited with code {returncode}."
                raise InfrastructureError(detail)
            raise InfrastructureError("Claude Code stream ended without a terminal result event.")
        finally:
            managed.close()

    def _preflight(self) -> None:
        if self._which(self.executable) is None:
            raise PreflightError(
                f"Claude Code preflight failed: executable `{self.executable}` was not found in PATH."
            )

    def _parse_stream_line(
        self,
        line: str,
        *,
        working_dir: Path,
        emit_result_signals: bool = True,
        decoded: Any = None,
    ) -> tuple[AgentEvent, ...]:
        timestamp_events: list[AgentEvent] = []

        if line.startswith("FOREMAN_SIGNAL:"):
            _, signal_events = extract_signal_events(line)
            return signal_events

        event = _decode_stream_line(line) if decoded is None else decoded
        if event is _NOT_JSON:
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
                # The result repeats the final assistant text, whose signals
                # were already emitted from the assistant block; emitting them
                # again would apply every signal twice.
                if emit_result_signals:
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

        if event_type == "system":
            return _system_events(event)
        if event_type == "user":
            return _tool_result_events(event)
        if event_type == "rate_limit_event":
            return _rate_limit_events(event)

        cost_event = _build_cost_update_event(event)
        if cost_event is not None:
            return (cost_event,)
        # Anything else is kept only as the raw line; inventing a tool use for
        # an unknown message type misrepresents what the agent did.
        return ()

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
        managed: ManagedProcess,
        config: AgentRunConfig,
        *,
        start_time: float,
        last_cost_usd: float,
    ) -> AgentEvent | None:
        elapsed_seconds = self._clock() - start_time
        if config.timeout_seconds > 0 and elapsed_seconds > config.timeout_seconds:
            managed.kill()
            return AgentEvent(
                "agent.killed",
                payload={
                    "reason": "Run exceeded time limit.",
                    "gate_type": "time",
                },
            )

        if config.max_cost_usd > 0 and last_cost_usd > config.max_cost_usd:
            managed.kill()
            return AgentEvent(
                "agent.killed",
                payload={
                    "reason": "Run exceeded cost limit.",
                    "gate_type": "cost",
                },
            )
        return None


def _decode_stream_line(line: str) -> Any:
    """Return the decoded JSON value for one stream line, or ``_NOT_JSON``."""

    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return _NOT_JSON


def _progress_events(decoded: Any) -> tuple[AgentEvent, ...] | None:
    """Return tick events for a progress-only line, or ``None`` for content.

    The Claude Code CLI streams ``system``/``thinking_tokens`` counters while
    the model reasons and ``rate_limit_event`` notices as it checks quota.
    Neither carries transcript content; they only prove the child is alive.
    """

    if not isinstance(decoded, dict):
        return None
    event_type = str(decoded.get("type", ""))
    if event_type == "system":
        subtype = str(decoded.get("subtype", ""))
        if subtype in _PROGRESS_SYSTEM_SUBTYPES:
            return (
                AgentEvent(
                    "agent.tick",
                    payload={
                        "source": subtype,
                        "estimated_tokens": _coerce_int(
                            decoded.get("estimated_tokens"), default=0
                        )
                        or 0,
                    },
                ),
            )
        return None
    if event_type == "rate_limit_event":
        info = decoded.get("rate_limit_info")
        status = str(info.get("status", "")) if isinstance(info, dict) else ""
        if status in {"", "allowed"}:
            return (
                AgentEvent(
                    "agent.tick",
                    payload={"source": "rate_limit", "status": status or "unknown"},
                ),
            )
    return None


def _raw_output_payload(line: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"stream": "stdout", "line": line[:RAW_LINE_MAX_CHARS]}
    if len(line) > RAW_LINE_MAX_CHARS:
        payload["truncated"] = True
        payload["length"] = len(line)
    return payload


def _system_events(event: dict[str, Any]) -> tuple[AgentEvent, ...]:
    if str(event.get("subtype", "")) != "init":
        return ()
    tools = event.get("tools")
    payload = {
        "session_id": _optional_string(event.get("session_id")),
        "model": _optional_string(event.get("model")),
        "cwd": _optional_string(event.get("cwd")),
        "permission_mode": _optional_string(event.get("permissionMode")),
        "version": _optional_string(event.get("claude_code_version")),
        "tool_count": len(tools) if isinstance(tools, list) else 0,
    }
    return (
        AgentEvent(
            "agent.session",
            payload={key: value for key, value in payload.items() if value is not None},
        ),
    )


def _tool_result_events(event: dict[str, Any]) -> tuple[AgentEvent, ...]:
    message = event.get("message", event)
    content = message.get("content", ()) if isinstance(message, dict) else ()
    if not isinstance(content, list):
        return ()
    events: list[AgentEvent] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        text = _tool_result_text(block.get("content"))
        preview = text[:TOOL_RESULT_PREVIEW_CHARS]
        events.append(
            AgentEvent(
                "agent.tool_result",
                payload={
                    "tool_use_id": _optional_string(block.get("tool_use_id")) or "",
                    "is_error": bool(block.get("is_error")),
                    "length": len(text),
                    "preview": preview,
                    "truncated": len(text) > len(preview),
                },
            )
        )
    return tuple(events)


def _tool_result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(parts)
    return ""


def _rate_limit_events(event: dict[str, Any]) -> tuple[AgentEvent, ...]:
    info = event.get("rate_limit_info")
    if not isinstance(info, dict):
        return ()
    payload = {
        "status": str(info.get("status", "unknown")),
        "rate_limit_type": _optional_string(info.get("rateLimitType")),
        "resets_at": _coerce_int(info.get("resetsAt")),
    }
    return (
        AgentEvent(
            "agent.rate_limit",
            payload={key: value for key, value in payload.items() if value is not None},
        ),
    )


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
