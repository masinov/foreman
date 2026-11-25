"""Claude Code stream-json backend for Foreman."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
import json
import os
import re
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
    NoTurnError,
    PreflightError,
    QuotaExhaustedError,
)
from .env import agent_environment
from .process import DEFAULT_TICK_SECONDS, ManagedProcess, popen_kwargs
from .signals import extract_signal_events

_FILE_TOOLS = {"Read", "Write", "Edit", "NotebookEdit"}

#: A step is one headless turn: when the agent's message ends, the process
#: exits and the step is over. Claude Code moves a command that outlives its
#: timeout to the background and lets the agent end its turn to "wait" for
#: it, which in a step means the work is abandoned and the completion marker
#: never comes. So background commands are off and the default timeout is
#: long enough for a project's test suite. A role's own ``[agent.env]`` wins.
#:
#: Every command also runs with standard input on ``/dev/null``, through
#: ``NO_STDIN_PREFIX``. Claude Code gives a command that holds a heredoc a
#: socket as its input, so a read in it waited until the timeout (FOR-53's
#: 18-minute stall; checked live on 2026-11-25 with Claude Code 2.1.332).
NO_STDIN_PREFIX = Path(__file__).resolve().parent.parent / "data" / "shell" / "no-stdin.sh"
HEADLESS_STEP_ENV: dict[str, str] = {
    "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
    "BASH_DEFAULT_TIMEOUT_MS": "1200000",
    "BASH_MAX_TIMEOUT_MS": "1800000",
    "CLAUDE_CODE_SHELL_PREFIX": str(NO_STDIN_PREFIX),
}

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
# The result line ends a run: completed, failed, or stopped at its budget.
_TERMINAL_EVENT_TYPES = frozenset({"agent.completed", "agent.error", "agent.killed"})
#: Internal to this module: the parser's word for a result that read no prompt.
#: ``run`` raises on it; it is never yielded, so it is not an agent event.
_NO_TURN = "runner.no_turn"
# How long a process may take to exit after its stream has finished.
TERMINAL_EXIT_GRACE_SECONDS = 5.0
#: Error texts the CLI returns when the account's usage window is spent.
#: Used only when the CLI sent no rate-limit notice at all. The phrases are
#: the CLI's own; a bare "quota" or "rate limit" also appears in errors from
#: tools the agent called, which are not about this account's usage.
_QUOTA_ERROR_PATTERN = re.compile(
    r"hit your (?:\w+ ){0,2}limit|usage limit reached|out of (?:extra )?usage",
    re.IGNORECASE,
)
#: Rate-limit statuses under which the backend still serves requests.
_RATE_LIMIT_OK_STATUSES = frozenset({"", "allowed", "allowed_warning"})


def _check_shell_prefix(prefix: str) -> None:
    """Refuse to start when the shell prefix cannot run.

    Claude Code runs every command through it, so a missing or
    non-executable prefix would fail every command of the step. An install
    that dropped the file's executable bit is the likely cause. A role that
    sets the prefix to an empty string runs commands without one.
    """

    if not prefix:
        return
    path = Path(prefix)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise PreflightError(
            f"Claude Code preflight failed: the shell prefix `{prefix}` is missing or not executable."
        )



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
        if config.no_tools:
            # An empty list is the CLI's way of saying no tool at all. A deny
            # list cannot say it: it misses every tool it does not name.
            command.extend(["--tools", ""])
        elif config.allowed_tools:
            # The role's whole tool set: nothing outside it exists for the
            # agent, whatever else the CLI ships or a later version adds.
            command.extend(["--tools", ",".join(config.allowed_tools)])
        if config.disallowed_tools:
            command.extend(
                ["--disallowed-tools", ",".join(config.disallowed_tools)]
            )
        if config.max_cost_usd > 0:
            # Cost is only reported in the final result line, so nothing on
            # this side can stop spend while the agent works. The CLI can.
            # It counts a resumed session from where the session left off, so
            # the limit it is given is this run's limit on top of that.
            carried = config.session_cost_baseline_usd if config.session_id else 0.0
            command.extend(
                ["--max-budget-usd", f"{config.max_cost_usd + max(carried, 0.0):.2f}"]
            )
        flags = dict(config.extra_flags)
        if flags.pop("strict_mcp_config", True) is not False:
            # Only the MCP servers a role names with ``mcp_config``; never the
            # ones the engine's user has connected for themselves. Seen on
            # 2026-11-15: a reviewer limited to Read, Grep and Glob still had
            # the operator's document and drive connectors. A role opts out
            # with ``strict_mcp_config = false`` under ``[agent.flags]``.
            command.append("--strict-mcp-config")
        command.extend(_extra_flag_args(flags))
        return command

    def run(self, config: AgentRunConfig) -> Iterator[AgentEvent]:
        """Run Claude Code and yield normalized agent events.

        Output is read on a pump thread. While the child is silent the loop
        wakes every ``tick_seconds`` to enforce the time and cost gates and to
        yield an ``agent.tick`` so the orchestrator can heartbeat its lease.
        Whatever ends the generator, the child's process group is terminated.
        """

        self._preflight()
        env = {**HEADLESS_STEP_ENV, **config.env}
        _check_shell_prefix(env["CLAUDE_CODE_SHELL_PREFIX"])
        command = self.build_command(config)
        try:
            proc = self._popen_factory(
                command,
                **popen_kwargs(
                    cwd=config.working_dir,
                    env=agent_environment(env),
                    inherit_env=False,
                ),
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
            session_cost = _SessionCost(
                config.session_cost_baseline_usd if config.session_id else 0.0
            )
            saw_terminal_event = False
            saw_assistant_text = False
            quota_notice: dict[str, Any] | None = None

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
                        if event.payload.get("source") == "rate_limit":
                            # The CLI said the account may go on. Remember it,
                            # so a later error is not read as a quota stop
                            # because of how it is worded.
                            quota_notice = {"status": "allowed"}
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
                    session_cost=session_cost,
                )
                if any(
                    event.event_type == "agent.message"
                    and event.payload.get("phase") == "assistant"
                    for event in parsed_events
                ):
                    saw_assistant_text = True
                # A line carrying the run's terminal event is the end of the
                # run: its cost is already spent and its outcome is decided,
                # so no gate may turn it into a kill.
                line_is_terminal = any(
                    event.event_type in _TERMINAL_EVENT_TYPES for event in parsed_events
                )
                for event in parsed_events:
                    if event.event_type == "agent.cost_update":
                        last_cost_usd = _coerce_float(
                            event.payload.get("cumulative_usd"),
                            default=last_cost_usd,
                        )
                    if event.event_type == "agent.rate_limit":
                        quota_notice = dict(event.payload)
                    if event.event_type == "agent.error" and _is_quota_error(
                        event.payload, quota_notice
                    ):
                        # The account's usage window is spent. This is not a
                        # task failure: raise it as a quota condition carrying
                        # the reset time and what was already charged.
                        raise QuotaExhaustedError(
                            _optional_string(event.payload.get("error"))
                            or "Claude Code refused the request: usage quota exhausted.",
                            retry_after=_retry_after_from_notice(quota_notice),
                            payload={
                                key: event.payload[key]
                                for key in ("session_id", "cost_usd", "duration_ms", "token_count")
                                if key in event.payload
                            },
                        )
                    if event.event_type == _NO_TURN:
                        raise NoTurnError(
                            "Claude Code returned without running a turn; "
                            "the prompt was not read."
                        )
                    if event.event_type in _TERMINAL_EVENT_TYPES:
                        saw_terminal_event = True
                    yield event

                    if line_is_terminal:
                        continue
                    gate_event = self._check_gates(
                        managed,
                        config,
                        start_time=start_time,
                        last_cost_usd=last_cost_usd,
                    )
                    if gate_event is not None:
                        yield gate_event
                        return

                if saw_terminal_event:
                    # Nothing after the result matters. A process that lingers
                    # must not hold the step open or reach the time gate.
                    break

            # Bounded: the stream is finished, so give the process a moment to
            # exit on its own; ``close`` in the ``finally`` stops whatever is
            # left of it and its process group.
            managed.wait(timeout=TERMINAL_EXIT_GRACE_SECONDS)
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
        session_cost: _SessionCost | None = None,
    ) -> tuple[AgentEvent, ...]:
        timestamp_events: list[AgentEvent] = []
        session_cost = session_cost or _SessionCost()

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
            cost_event = _build_cost_update_event(event, session_cost)
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
            cost_event = _build_cost_update_event(event, session_cost)
            if cost_event is not None:
                timestamp_events.append(cost_event)

            reported_cost = event.get("total_cost_usd", event.get("cost_usd"))
            payload = {
                "session_id": _optional_string(event.get("session_id")),
                "cost_usd": session_cost.run_cost(reported_cost),
                "duration_ms": _coerce_int(event.get("duration_ms")),
                "token_count": _extract_total_tokens(event),
            }
            if reported_cost is not None:
                payload["session_cost_usd"] = _coerce_float(reported_cost, default=0.0)
            if (
                not result_text
                and not bool(event.get("is_error"))
                and event.get("num_turns") == 0
                and "max_budget" not in str(event.get("subtype") or "")
            ):
                # The CLI came back without reading the prompt. That is not
                # an answer from the agent; ``run`` raises on it.
                timestamp_events.append(AgentEvent(_NO_TURN, payload=payload))
                return tuple(timestamp_events)
            token_usage = _extract_token_usage(event)
            if token_usage is not None:
                payload["token_usage"] = token_usage
            if "max_budget" in str(event.get("subtype") or ""):
                # The CLI stopped the run at --max-budget-usd. That is the
                # cost gate firing, with the real cost attached.
                timestamp_events.append(
                    AgentEvent(
                        "agent.killed",
                        payload={
                            **payload,
                            "reason": (
                                f"Run exceeded cost limit (${payload['cost_usd']:.2f} spent)."
                            ),
                            "gate_type": "cost",
                        },
                    )
                )
            elif bool(event.get("is_error")):
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

        cost_event = _build_cost_update_event(event, session_cost)
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


def _is_quota_error(payload: dict[str, Any], notice: dict[str, Any] | None) -> bool:
    """Return True when an error result means the usage quota is spent.

    The CLI's rate-limit notice is the fact: when one arrived, its status
    decides, and an error that follows an "allowed" notice is an ordinary
    error however it is worded. The error text is consulted only when no
    notice was seen.
    """

    if notice is not None:
        return str(notice.get("status", "")) not in _RATE_LIMIT_OK_STATUSES
    error_text = _optional_string(payload.get("error")) or ""
    return bool(_QUOTA_ERROR_PATTERN.search(error_text))


def _retry_after_from_notice(notice: dict[str, Any] | None) -> str | None:
    """Return the quota reset time from a rate-limit notice as ISO 8601 UTC."""

    if notice is None:
        return None
    epoch = _coerce_int(notice.get("resets_at"))
    if epoch is None or epoch <= 0:
        return None
    return (
        datetime.fromtimestamp(epoch, timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


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


class _SessionCost:
    """Turns the CLI's running total for a session into this run's own cost.

    Claude Code carries a session's cost across ``--resume``: the total it
    reports includes every earlier run of the session. ``baseline`` is what
    the session had counted before this run. A total below the baseline means
    the CLI's count started over (older versions did not carry it), so the
    total is then this run's own.
    """

    def __init__(self, baseline: float = 0.0) -> None:
        self.baseline = max(float(baseline or 0.0), 0.0)

    def run_cost(self, reported: Any) -> float:
        total = _coerce_float(reported, default=0.0)
        if reported is None:
            return total
        if total + 1e-9 < self.baseline:
            self.baseline = 0.0
        return max(total - self.baseline, 0.0)


def _build_cost_update_event(
    event: dict[str, Any], session_cost: _SessionCost | None = None
) -> AgentEvent | None:
    cost = event.get("total_cost_usd", event.get("cost_usd"))
    has_token_info = _has_token_data(event)
    if cost is None and not has_token_info:
        return None
    tokens = _extract_total_tokens(event) if has_token_info else 0
    payload = {
        "cumulative_usd": (session_cost or _SessionCost()).run_cost(cost),
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


def _extract_token_usage(event: dict[str, Any]) -> dict[str, int] | None:
    """Return the input / output / cache split of a result line's usage."""

    usage = event.get("usage")
    if not isinstance(usage, dict):
        return None
    return {
        "input": _coerce_int(usage.get("input_tokens"), default=0) or 0,
        "output": _coerce_int(usage.get("output_tokens"), default=0) or 0,
        "cache_read": _coerce_int(usage.get("cache_read_input_tokens"), default=0) or 0,
        "cache_creation": _coerce_int(usage.get("cache_creation_input_tokens"), default=0) or 0,
    }


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
