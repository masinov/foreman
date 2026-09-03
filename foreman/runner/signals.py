"""Signal parsing helpers for Foreman runners."""

from __future__ import annotations

import json
from typing import Any

from .base import AgentEvent

SIGNAL_PREFIX = "FOREMAN_SIGNAL:"
_SIGNAL_TYPES = {
    "task_started": "signal.task_started",
    "task_created": "signal.task_created",
    "progress": "signal.progress",
    "blocker": "signal.blocker",
}

# Canonical signal type names.
SIGNAL_TASK_STARTED = "signal.task_started"
SIGNAL_TASK_CREATED = "signal.task_created"
SIGNAL_PROGRESS = "signal.progress"
SIGNAL_BLOCKER = "signal.blocker"
SIGNAL_INVALID = "signal.invalid"
SIGNAL_UNKNOWN = "signal.unknown"


def extract_signal_events(
    text: str,
    *,
    timestamp: str | None = None,
) -> tuple[str, tuple[AgentEvent, ...]]:
    """Split structured signal lines from plain assistant text.

    Invalid JSON or unknown signal types are emitted as ``signal.invalid``
    or ``signal.unknown`` so they are never silently dropped.
    """

    if not text:
        return "", ()

    cleaned_lines: list[str] = []
    events: list[AgentEvent] = []
    lines = text.splitlines()
    in_fence = False
    index = 0

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if stripped.startswith(("```", "~~~")):
            # Signals quoted inside a code fence are documentation, not intent.
            in_fence = not in_fence
            cleaned_lines.append(raw_line)
            index += 1
            continue
        if in_fence or stripped.startswith(">") or not stripped.startswith(SIGNAL_PREFIX):
            cleaned_lines.append(raw_line)
            index += 1
            continue

        payload_text = stripped[len(SIGNAL_PREFIX):].strip()
        consumed = 1
        # Pretty-printed JSON: keep consuming lines while braces are open.
        while _brace_depth(payload_text) > 0 and consumed < _MAX_SIGNAL_LINES:
            next_index = index + consumed
            if next_index >= len(lines):
                break
            payload_text += "\n" + lines[next_index].strip()
            consumed += 1

        signal = _parse_signal_payload(payload_text, timestamp=timestamp)
        if signal is not None:
            events.append(signal)
        index += consumed

    cleaned_text = "\n".join(cleaned_lines).strip()
    return cleaned_text, tuple(events)


_MAX_SIGNAL_LINES = 40


def _brace_depth(text: str) -> int:
    """Return the net depth of unclosed braces, ignoring quoted strings."""

    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
    return depth


def _parse_signal_line(
    line: str,
    *,
    timestamp: str | None,
) -> AgentEvent | None:
    return _parse_signal_payload(line[len(SIGNAL_PREFIX) :].strip(), timestamp=timestamp)


def _parse_signal_payload(
    payload_text: str,
    *,
    timestamp: str | None,
) -> AgentEvent | None:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return _invalid_event(payload_text, timestamp)
    if not isinstance(payload, dict):
        return _invalid_event(payload_text, timestamp)

    signal_type = _SIGNAL_TYPES.get(str(payload.get("type", "")))
    if signal_type is None:
        return _unknown_event(str(payload.get("type", "")), payload, timestamp)

    # Validate required fields per signal type.
    validation = _validate_payload(signal_type, payload)
    if validation is not None:
        return validation

    event_payload = {
        str(key): value
        for key, value in payload.items()
        if key != "type"
    }
    if timestamp is None:
        return AgentEvent(signal_type, payload=event_payload)
    return AgentEvent(signal_type, payload=event_payload, timestamp=timestamp)


def _invalid_event(raw: str, timestamp: str | None) -> AgentEvent:
    payload = {"raw": raw, "reason": "invalid JSON"}
    if timestamp is None:
        return AgentEvent(SIGNAL_INVALID, payload=payload)
    return AgentEvent(SIGNAL_INVALID, payload=payload, timestamp=timestamp)


def _unknown_event(signal_type: str, payload: dict[str, Any], timestamp: str | None) -> AgentEvent:
    event_payload = {"type": signal_type, "reason": "unknown signal type"}
    event_payload.update(payload)
    if timestamp is None:
        return AgentEvent(SIGNAL_UNKNOWN, payload=event_payload)
    return AgentEvent(SIGNAL_UNKNOWN, payload=event_payload, timestamp=timestamp)


def _validate_payload(signal_type: str, payload: dict[str, Any]) -> AgentEvent | None:
    """Return an error event if the payload fails validation, else None."""

    if signal_type == SIGNAL_TASK_STARTED:
        error = validate_task_started_payload(payload)
        if error:
            return _invalid_event(error, None)

    elif signal_type == SIGNAL_TASK_CREATED:
        error = validate_task_created_payload(payload)
        if error:
            return _invalid_event(error, None)

    elif signal_type == SIGNAL_PROGRESS:
        error = validate_progress_payload(payload)
        if error:
            return _invalid_event(error, None)

    elif signal_type == SIGNAL_BLOCKER:
        error = validate_blocker_payload(payload)
        if error:
            return _invalid_event(error, None)

    return None


def validate_task_started_payload(payload: dict[str, Any]) -> str | None:
    """Validate signal.task_started payload.

    Required: title (non-placeholder), branch, criteria.
    Optional: task_type.
    Returns None if valid, or an error string if invalid.
    """
    title = payload.get("title")
    if not title or title == "[autonomous] new task":
        return "task_started missing required 'title'"
    branch = payload.get("branch")
    if not branch:
        return "task_started missing required 'branch'"
    criteria = payload.get("criteria")
    if not criteria:
        return "task_started missing required 'criteria'"
    task_type = payload.get("task_type")
    if task_type is not None:
        valid_types = {"feature", "fix", "refactor", "docs", "spike", "chore"}
        if task_type not in valid_types:
            return f"task_started has invalid task_type {task_type!r}"
    return None


def validate_task_created_payload(payload: dict[str, Any]) -> str | None:
    """Validate signal.task_created payload.

    Required: title, description, criteria.
    Optional: task_type.
    Returns None if valid, or an error string if invalid.
    """
    title = payload.get("title")
    if not title:
        return "task_created missing required 'title'"
    description = payload.get("description")
    if not description:
        return "task_created missing required 'description'"
    criteria = payload.get("criteria")
    if not criteria:
        return "task_created missing required 'criteria'"
    task_type = payload.get("task_type")
    if task_type is not None:
        valid_types = {"feature", "fix", "refactor", "docs", "spike", "chore"}
        if task_type not in valid_types:
            return f"task_created has invalid task_type {task_type!r}"
    return None


def validate_progress_payload(payload: dict[str, Any]) -> str | None:
    """Validate signal.progress payload.

    Required: message.
    """
    message = payload.get("message")
    if not message:
        return "progress missing required 'message'"
    return None


def validate_blocker_payload(payload: dict[str, Any]) -> str | None:
    """Validate signal.blocker payload.

    Required: message.
    """
    message = payload.get("message")
    if not message:
        return "blocker missing required 'message'"
    return None
