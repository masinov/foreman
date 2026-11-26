"""The engine's reading of a user's holds (ADR-0043).

A hold is read, never written, here: before a task is chosen, before each
of its steps, and while a step runs, for a Stop. Holding what comes after a
held thing needs no more than that: a held task never reaches Done, so what
waits for it waits, its sprint is not finished and the next sprint does not
start.
"""

from __future__ import annotations

from ..domain.holds import Hold, LevelBlock, task_hold
from ..domain.models import Sprint, Task
from ..store import ForemanStore

__all__ = ["hold_of", "sprint_block_over"]


def hold_of(store: ForemanStore, task: Task) -> Hold | None:
    """What keeps ``task`` from starting its next step, read fresh, if anything."""

    fresh = store.get_task(task.id) or task
    return task_hold(
        fresh,
        sprint_block=store.get_sprint_block(fresh.sprint_id),
        workspace_block=store.get_workspace_block(),
    )


def sprint_block_over(store: ForemanStore, sprint: Sprint) -> LevelBlock | None:
    """The block that holds a whole sprint: the workspace's, else its own."""

    return store.get_workspace_block() or store.get_sprint_block(sprint.id)


