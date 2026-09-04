"""Shared runner protocol definitions for Foreman."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
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


def run_with_retry(
    runner: AgentRunner,
    config: AgentRunConfig,
    *,
    max_retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[AgentEvent]:
    """Run one native agent with infrastructure retries."""

    for attempt in range(max_retries + 1):
        try:
            yield from runner.run(config)
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
            if attempt == max_retries:
                yield AgentEvent(
                    "agent.error",
                    payload={
                        "error": str(exc),
                        "retries_exhausted": True,
                    },
                )
                return

            backoff = (2**attempt) * 5
            yield AgentEvent(
                "agent.infra_error",
                payload={
                    "error": str(exc),
                    "retry_in_seconds": backoff,
                    "attempt": attempt + 1,
                },
            )
            sleep(backoff)
