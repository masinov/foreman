"""Shared exception types for Foreman."""

from __future__ import annotations


class ForemanError(Exception):
    """Base exception for Foreman runtime failures."""


class FencedWriteError(ForemanError):
    """A write made under a task lease that a newer lease has replaced.

    Every lease on a task carries a fencing number, one higher than the
    lease before it. A holder writes the task only while no lease with a
    higher number exists: once another engine has taken the task over, the
    old holder's writes are refused, however late they arrive.
    """


class EngineCommandInterrupt(BaseException):
    """Raised inside the orchestrator to stop the running step for a command.

    A ``BaseException`` for the same reason as
    :class:`~foreman.runner.process.EngineShutdown`: the orchestrator's
    defensive ``except Exception`` fallbacks turn an exception into a failed
    agent outcome, and an operator's `pause` or `stop_task` is not an agent
    failure. It propagates through the same guarded-step path a shutdown takes
    — the run is settled as ``killed`` and the task keeps its resume point —
    and the resident engine settles the command once the stack has unwound.

    It lives here rather than in ``foreman.engine.resident.base`` because the orchestrator
    must catch it and ``foreman.engine.resident.base`` imports the orchestrator.
    """

    def __init__(self, command: object, *, task_id: str | None = None) -> None:
        name = getattr(command, "command", command)
        super().__init__(f"Engine command {name!r} stopped the running step.")
        self.command = command
        self.task_id = task_id
