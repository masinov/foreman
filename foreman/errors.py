"""Shared exception types for Foreman."""

from __future__ import annotations


class ForemanError(Exception):
    """Base exception for Foreman runtime failures."""


class EngineCommandInterrupt(BaseException):
    """Raised inside the orchestrator to stop the running step for a command.

    A ``BaseException`` for the same reason as
    :class:`~foreman.runner.process.EngineShutdown`: the orchestrator's
    defensive ``except Exception`` fallbacks turn an exception into a failed
    agent outcome, and an operator's `pause` or `stop_task` is not an agent
    failure. It propagates through the same guarded-step path a shutdown takes
    — the run is settled as ``killed`` and the task keeps its resume point —
    and the resident engine settles the command once the stack has unwound.

    It lives here rather than in ``foreman.serve`` because the orchestrator
    must catch it and ``foreman.serve`` imports the orchestrator.
    """

    def __init__(self, command: object, *, task_id: str | None = None) -> None:
        name = getattr(command, "command", command)
        super().__init__(f"Engine command {name!r} stopped the running step.")
        self.command = command
        self.task_id = task_id
