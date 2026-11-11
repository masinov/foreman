"""Errors the engine raises."""

from __future__ import annotations

from ..errors import ForemanError


class OrchestratorError(ForemanError):
    """Raised when Foreman cannot execute the requested workflow slice."""


class TaskCancelledError(OrchestratorError):
    """The task was cancelled by an operator while the engine was working on it."""

    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task {task_id!r} was cancelled; the engine stopped working on it.")
        self.task_id = task_id


class LeaseLostError(OrchestratorError):
    """Raised when this engine's task lease is renewed and found to be gone.

    Another engine has taken the task over, or the lease expired while the
    agent was silent. The active agent is stopped and this engine exits
    without touching the task, which the new holder now owns.
    """


class QuotaPauseError(OrchestratorError):
    """Raised when a task must pause because the agent backend's quota ran out.

    The task keeps its resume point (``workflow_current_step`` and the carried
    output) and its ``in_progress`` status, so the next pass resumes it at the
    same step; nothing about the task itself failed. ``retry_after`` is the
    backend's reset time when it reported one.
    """

    def __init__(self, task_id: str, *, retry_after: str | None, detail: str) -> None:
        super().__init__(f"Task {task_id!r} paused until the backend quota resets: {detail}")
        self.task_id = task_id
        self.retry_after = retry_after
        self.detail = detail


class TaskExecutionError(OrchestratorError):
    """Raised when running one specific task failed.

    Carries the task identifier so a resident engine can isolate the failure:
    block that one task, raise an attention turn for it, and keep serving the
    rest of the project instead of exiting. A one-shot ``foreman run`` treats
    it like any other ``OrchestratorError``.
    """

    def __init__(self, task_id: str, cause: BaseException) -> None:
        super().__init__(f"Task {task_id!r} failed: {cause}")
        self.task_id = task_id
        self.cause = cause
