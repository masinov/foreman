"""Shared runner protocol definitions for Foreman."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
import re
import time
from typing import Any, Protocol

from ..errors import ForemanError
from ..models import utc_now_text


@dataclass(slots=True)
class AgentRunConfig:
    """Runtime configuration for one native agent invocation."""

    backend: str
    model: str | None
    prompt: str
    working_dir: Path
    session_id: str | None
    permission_mode: str
    disallowed_tools: tuple[str, ...] = ()
    extra_flags: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 0
    max_cost_usd: float = 0.0


@dataclass(slots=True)
class AgentEvent:
    """One normalized event emitted by a native runner."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now_text)


class InfrastructureError(ForemanError):
    """Raised when the agent backend fails at the process or transport layer."""


class PreflightError(InfrastructureError):
    """Raised when the agent backend is unavailable before a run can start."""


class QuotaExhaustedError(InfrastructureError):
    """Raised when the backend refuses work because a usage quota ran out.

    Unlike a transport failure this does not clear in seconds: the account's
    window resets at a known time. ``retry_after`` is that time as an ISO 8601
    UTC timestamp when the backend reported it, else ``None``. ``payload``
    carries what the backend already charged (cost, tokens, session id) so the
    run record stays accurate.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.payload = dict(payload or {})


class AgentRunner(Protocol):
    """Protocol shared by native agent backends."""

    def run(self, config: AgentRunConfig) -> Iterator[AgentEvent]:
        """Launch one native agent process and yield normalized events."""


#: What a retried attempt is told when it resumes the session the failed
#: attempt had opened. The task instructions are already in that session.
RESUME_AFTER_INFRA_ERROR_PROMPT = (
    "The previous attempt at this step was cut off by an infrastructure error "
    "before it finished. Continue the same task from where you stopped. Your "
    "instructions are earlier in this session; do not start over, and check "
    "what is already done before repeating any of it."
)

_UNKNOWN_SESSION_PATTERN = re.compile(
    r"no conversation found|session (?:id )?.{0,80}(?:not found|does not exist|unknown)"
    r"|(?:unknown|invalid) session|thread .{0,80}not found",
    re.IGNORECASE,
)


def _next_attempt_config(
    original: AgentRunConfig,
    current: AgentRunConfig,
    *,
    attempt_session_id: str | None,
    error_text: str,
    early_failures: int,
) -> tuple[AgentRunConfig, str]:
    """Choose what the attempt after an infrastructure failure runs with.

    Returns the config and how it was chosen: ``resume`` (continue the session
    the failed attempt opened), ``session_dropped`` (the session id it was
    given does not work; start a fresh one), or ``replay``.
    """

    if attempt_session_id:
        return (
            replace(
                current,
                session_id=attempt_session_id,
                prompt=RESUME_AFTER_INFRA_ERROR_PROMPT,
            ),
            "resume",
        )
    if current.session_id and (
        _UNKNOWN_SESSION_PATTERN.search(error_text) or early_failures >= 2
    ):
        # The attempt never got a session going with the id it was handed: the
        # backend said it does not know it, or it failed twice running. Asking
        # for the same id again fails the same way, so start a fresh session
        # with the full prompt.
        return replace(current, session_id=None, prompt=original.prompt), "session_dropped"
    return current, "replay"


def run_with_retry(
    runner: AgentRunner,
    config: AgentRunConfig,
    *,
    max_retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[AgentEvent]:
    """Run one native agent with infrastructure retries.

    A retry continues the session the failed attempt opened instead of
    replaying the whole prompt into it, a session id the backend does not
    accept is dropped rather than retried, and every failed attempt reports
    what it had already cost.
    """

    current = config
    early_failures = 0
    for attempt in range(max_retries + 1):
        attempt_session_id: str | None = None
        attempt_cost_usd = 0.0
        try:
            for event in runner.run(current):
                if event.event_type == "agent.session":
                    attempt_session_id = (
                        str(event.payload.get("session_id") or "") or attempt_session_id
                    )
                elif event.event_type == "agent.cost_update":
                    cumulative = event.payload.get("cumulative_usd")
                    if isinstance(cumulative, (int, float)):
                        attempt_cost_usd = float(cumulative)
                yield event
            return
        except QuotaExhaustedError as exc:
            # A quota does not come back in seconds; retrying would spend the
            # infrastructure budget against the same wall. Surface it once,
            # with the reset time, so the orchestrator can pause the task.
            yield AgentEvent(
                "agent.error",
                payload={
                    **exc.payload,
                    "error": str(exc),
                    "quota_exhausted": True,
                    "retry_after": exc.retry_after,
                },
            )
            return
        except PreflightError as exc:
            yield AgentEvent(
                "agent.error",
                payload={
                    "error": str(exc),
                    "preflight_failed": True,
                },
            )
            return
        except InfrastructureError as exc:
            spent: dict[str, Any] = {}
            if attempt_cost_usd > 0:
                spent["cost_usd"] = attempt_cost_usd
            if attempt_session_id:
                spent["session_id"] = attempt_session_id
            if attempt == max_retries:
                yield AgentEvent(
                    "agent.error",
                    payload={
                        **spent,
                        "error": str(exc),
                        "retries_exhausted": True,
                    },
                )
                return

            early_failures = 0 if attempt_session_id else early_failures + 1
            dropped_session_id = current.session_id
            current, next_mode = _next_attempt_config(
                config,
                current,
                attempt_session_id=attempt_session_id,
                error_text=str(exc),
                early_failures=early_failures,
            )
            payload: dict[str, Any] = {
                **spent,
                "error": str(exc),
                "retry_in_seconds": (2**attempt) * 5,
                "attempt": attempt + 1,
                "next_attempt": next_mode,
            }
            if next_mode == "session_dropped":
                payload["dropped_session_id"] = dropped_session_id
                early_failures = 0
            backoff = (2**attempt) * 5
            yield AgentEvent("agent.infra_error", payload=payload)
            sleep(backoff)
