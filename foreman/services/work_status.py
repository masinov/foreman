"""What a sprint's work is doing now, for the status line (ADR-0043 §6).

One answer per sprint, the same on every page that shows it: the sprint
header, the project header, the top bar and a row of the workspace's
projects table. The page turns it into words; it carries no names, only
fixed states, task keys, steps and times.

``state`` is the first of these that is true:

- ``blocked``: the workspace or the sprint is blocked (``scope``, ``reason``).
- ``stopping``: a user stopped the task whose step is still running.
- ``pausing``: a user paused the task whose step is running; it finishes.
- ``stopped`` / ``paused``: every unfinished task is paused (``stopped``
  when the last pause cut a step).
- ``working``: a step of ``task_key`` is running (``paused`` counts the rest).
- ``some_paused``: nothing runs and ``paused`` tasks are paused.
- ``ready_to_finish``: every task is done or cancelled.
- ``waiting``: started, nothing running, nothing paused.
- ``not_started``: a planned sprint, or no active sprint.

``no_worker`` is true when work could run and no worker holds the project.
"""

from __future__ import annotations

from typing import Any

from ..domain.holds import LevelBlock
from ..domain.models import FINISHED_TASK_STATUSES, Sprint, Task
from ..store import ForemanStore

#: Unfinished work: what a Pause applies to and what can run.
_UNFINISHED = frozenset({"todo", "in_progress", "blocked"})


def sprint_work_status(
    store: ForemanStore,
    sprint: Sprint | None,
    *,
    workspace_block: LevelBlock | None = None,
    resident: bool | None = None,
) -> dict[str, Any]:
    """The status line of one sprint (None: the project has no active sprint)."""

    if sprint is None:
        return {"state": "not_started", "no_worker": False}
    tasks = store.list_tasks(sprint_id=sprint.id)
    running_ids = {
        run.task_id for run in store.list_runs(project_id=sprint.project_id, status="running")
    }
    if resident is None:
        resident = store.get_engine_lock(sprint.project_id) is not None
    block = workspace_block or store.get_sprint_block(sprint.id)
    status = _state(sprint, tasks, running_ids, block)
    could_run = sprint.status == "active" and status["state"] in (
        "working",
        "some_paused",
        "waiting",
        "pausing",
        "stopping",
    )
    status["no_worker"] = bool(could_run and not resident)
    return status


def _state(
    sprint: Sprint,
    tasks: list[Task],
    running_ids: set[str],
    block: LevelBlock | None,
) -> dict[str, Any]:
    unfinished = [task for task in tasks if task.status in _UNFINISHED]
    paused = [task for task in unfinished if task.paused_at]
    running = next((task for task in unfinished if task.id in running_ids), None)
    finished = bool(tasks) and all(task.status in FINISHED_TASK_STATUSES for task in tasks)

    if block is not None:
        return {
            "state": "blocked",
            "scope": block.scope,
            "reason": block.reason,
            "by": block.set_by,
            "at": block.set_at,
            "ready_to_finish": finished and sprint.status == "active",
        }
    if sprint.status == "planned":
        return {"state": "not_started", "paused": len(paused)}
    if running is not None and running.paused_at:
        return {
            "state": "stopping" if running.pause_mode == "now" else "pausing",
            "task_id": running.id,
            "task_key": running.task_key,
            "step": running.workflow_current_step,
        }
    if unfinished and len(paused) == len(unfinished):
        latest = max(paused, key=lambda task: task.paused_at or "")
        return {
            "state": "stopped" if latest.pause_mode == "now" else "paused",
            "by": latest.paused_by,
            "at": latest.paused_at,
            "paused": len(paused),
        }
    if running is not None:
        return {
            "state": "working",
            "task_id": running.id,
            "task_key": running.task_key,
            "step": running.workflow_current_step,
            "paused": len(paused),
        }
    if paused:
        return {"state": "some_paused", "paused": len(paused)}
    if finished:
        return {"state": "ready_to_finish"}
    return {"state": "waiting"}
