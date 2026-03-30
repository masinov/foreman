"""Signal parsing helpers for Foreman runners."""

from __future__ import annotations

import json

from .base import AgentEvent

SIGNAL_PREFIX = "FOREMAN_SIGNAL:"
_SIGNAL_TYPES = {
    "task_started": "signal.task_started",
    "task_created": "signal.task_created",
    "progress": "signal.progress",
    "blocker": "signal.blocker",
}


def extract_signal_events(
    text: str,
    *,
    timestamp: str | None = None,
) -> tuple[str, tuple[AgentEvent, ...]]:
    """Split structured signal lines from plain assistant text."""

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
        return None
    if not isinstance(payload, dict):
        return None

    signal_type = _SIGNAL_TYPES.get(str(payload.get("type", "")))
    if signal_type is None:
        return None

    event_payload = {
        str(key): value
        for key, value in payload.items()
        if key != "type"
    }
    if timestamp is None:
        return AgentEvent(signal_type, payload=event_payload)
    return AgentEvent(signal_type, payload=event_payload, timestamp=timestamp)
