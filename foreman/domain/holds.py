"""What holds a task back from running (ADR-0043).

Two holds a user sets:

- **Pause**, soft, on a task. A sprint's or the workspace's Pause is a bulk
  action that pauses each of their unfinished tasks; there is no paused
  sprint. Resume lifts it, on the task or on any level above.
- **Block**, hard, with a reason, on a task, a sprint or the workspace.
  Nothing under a block runs until Unblock, set where it was set.

A task's own block is its ``blocked`` status, as it always was; a block on a
sprint or the workspace is a :class:`LevelBlock`. A Block of a task whose
step is running waits for the step to end (``Task.block_requested``).

:func:`task_hold` is the one answer to "may this task run, and if not, why",
for the engine, the API and the pages alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import Task

#: The fixed ``scope_id`` of the workspace's block.
WORKSPACE_SCOPE_ID = "workspace"

HoldScope = Literal["task", "sprint", "workspace"]
HoldKind = Literal["pause", "block", "blocking"]

#: A pause lets the running step finish; a Stop is a pause that cuts it.
PAUSE_MODES: tuple[str, ...] = ("finish_step", "now")

#: The statuses a Pause applies to: work that is not finished and not filed
#: but unaccepted. A task waiting for a decision (``blocked`` at a gate) can
#: be paused too; its decision is still recorded and waits for Resume.
PAUSABLE_TASK_STATUSES: frozenset[str] = frozenset({"todo", "in_progress", "blocked"})


@dataclass(slots=True, frozen=True)
class LevelBlock:
    """A block on a sprint or on the workspace."""

    scope: Literal["sprint", "workspace"]
    scope_id: str
    project_id: str | None
    reason: str
    set_by: str
    set_at: str


@dataclass(slots=True, frozen=True)
class Hold:
    """Why a task may not start its next step.

    ``scope`` is where the hold was set. ``kind`` is ``pause`` (a user's
    pause on the task), ``block`` (a block on the sprint or the workspace)
    or ``blocking`` (a Block of the task waiting for its step to end).
    ``mode`` is ``now`` only for a Stop: the running step is cut.
    """

    scope: HoldScope
    kind: HoldKind
    by: str
    at: str
    reason: str | None = None
    mode: str = "finish_step"

    @property
    def cuts_running_step(self) -> bool:
        return self.mode == "now"


def task_hold(
    task: Task,
    *,
    sprint_block: LevelBlock | None = None,
    workspace_block: LevelBlock | None = None,
) -> Hold | None:
    """The hold that keeps ``task`` from starting its next step, if any.

    A block above wins over the task's own pause in what is shown, because
    it is the one a Resume cannot lift. A Stop's cut is read on its own
    (:func:`cuts_running_step`), so a block above never hides it.
    """

    for block in (workspace_block, sprint_block):
        if block is not None:
            return Hold(
                scope=block.scope,
                kind="block",
                by=block.set_by,
                at=block.set_at,
                reason=block.reason,
            )
    if task.block_requested:
        return Hold(scope="task", kind="blocking", by="", at="", reason=task.block_requested)
    if task.paused_at:
        return Hold(
            scope="task",
            kind="pause",
            by=task.paused_by or "",
            at=task.paused_at,
            mode=task.pause_mode or "finish_step",
        )
    return None


def cuts_running_step(task: Task) -> bool:
    """True when a user stopped this task: its running step is cut now."""

    return bool(task.paused_at) and task.pause_mode == "now"
