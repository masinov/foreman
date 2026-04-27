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

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith(SIGNAL_PREFIX):
            cleaned_lines.append(raw_line)
            continue

        signal = _parse_signal_line(stripped, timestamp=timestamp)
        if signal is not None:
            events.append(signal)

    cleaned_text = "\n".join(cleaned_lines).strip()
    return cleaned_text, tuple(events)


def _parse_signal_line(
    line: str,
    *,
    timestamp: str | None,
) -> AgentEvent | None:
    payload_text = line[len(SIGNAL_PREFIX) :].strip()
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
