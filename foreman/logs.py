"""JSON-lines process logging for the Foreman engine.

The resident engine (`foreman serve`) has no terminal to print to: its only
operational surface is the process log. This module gives every Foreman
component one line of JSON per event on stderr so a log collector can index
runs without parsing prose.

Every line carries ``ts``, ``level``, and ``event``; ``project_id``,
``task_id``, ``run_id``, and ``step`` are included whenever the caller knows
them, followed by any extra fields passed through. Callers use
:func:`log_event` rather than formatting messages themselves, so the event
name stays a stable identifier instead of a sentence.

Logging is inert until :func:`configure_json_logging` runs: the CLI turns it
on for ``foreman serve`` and for ``foreman run --json-logs``, and the library
code below can be called unconditionally from anywhere in the engine.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, IO, Mapping

DEFAULT_LOGGER_NAME = "foreman"

#: Fields that lead every line, in this order, when they are present.
LEADING_FIELDS: tuple[str, ...] = ("project_id", "task_id", "run_id", "step")

#: Longest string kept for any single field value. Agent output and error text
#: can be arbitrarily long; a process log line must stay bounded.
MAX_FIELD_CHARS = 500

#: ``LogRecord`` attributes that are never part of the emitted payload.
_RESERVED_RECORD_FIELDS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "stacklevel", "taskName", "thread",
        "threadName",
    }
)


class JsonLinesFormatter(logging.Formatter):
    """Render one ``LogRecord`` as a single-line JSON object.

    The record's message is the event name. Structured fields come from the
    ``extra`` mapping passed to the logging call; unserializable values are
    coerced to their ``repr`` so a bad field can never lose the whole line.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": _timestamp(record.created),
            "level": record.levelname,
            "event": record.getMessage(),
        }

        fields = _record_fields(record)
        for key in LEADING_FIELDS:
            if fields.get(key) is not None:
                payload[key] = _coerce(fields.pop(key))
            else:
                fields.pop(key, None)
        for key in sorted(fields):
            payload[key] = _coerce(fields[key])

        if record.exc_info:
            payload["error"] = _truncate(self.formatException(record.exc_info))

        return json.dumps(payload, default=repr, separators=(",", ":"))


def configure_json_logging(
    *,
    stream: IO[str] | None = None,
    level: int = logging.INFO,
    logger_name: str = DEFAULT_LOGGER_NAME,
) -> logging.Logger:
    """Send ``logger_name`` and its children to ``stream`` as JSON lines.

    Idempotent: calling it twice replaces the handler rather than doubling
    every line. Propagation is disabled so a host application's root handler
    cannot re-emit the same event in a different format.
    """

    logger = logging.getLogger(logger_name)
    for existing in list(logger.handlers):
        if getattr(existing, "_foreman_json", False):
            logger.removeHandler(existing)
            existing.close()

    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonLinesFormatter())
    handler.setLevel(level)
    handler._foreman_json = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a Foreman logger. ``name`` is appended to the package logger."""

    if not name:
        return logging.getLogger(DEFAULT_LOGGER_NAME)
    return logging.getLogger(f"{DEFAULT_LOGGER_NAME}.{name}")


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    project_id: str | None = None,
    task_id: str | None = None,
    run_id: str | None = None,
    step: str | None = None,
    exc_info: BaseException | bool | None = None,
    **fields: Any,
) -> None:
    """Log one structured engine event.

    ``event`` is a stable dotted identifier (``serve.pass_completed``), not a
    sentence. Extra keyword fields are emitted verbatim after the leading
    identity fields.
    """

    extra = {
        "project_id": project_id,
        "task_id": task_id,
        "run_id": run_id,
        "step": step,
        **fields,
    }
    logger.log(level, event, extra=extra, exc_info=exc_info)


def compact_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a log-safe copy of an event payload with long values truncated."""

    if not payload:
        return {}
    return {str(key): _coerce(value) for key, value in payload.items()}


def _record_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _RESERVED_RECORD_FIELDS and not key.startswith("_")
    }


def _timestamp(created: float) -> str:
    return (
        datetime.fromtimestamp(created, timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _coerce(value: Any) -> Any:
    if isinstance(value, str):
        return _truncate(value)
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_coerce(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _coerce(item) for key, item in value.items()}
    return _truncate(repr(value))


def _truncate(text: str) -> str:
    if len(text) <= MAX_FIELD_CHARS:
        return text
    return f"{text[:MAX_FIELD_CHARS]}… (+{len(text) - MAX_FIELD_CHARS} chars)"
