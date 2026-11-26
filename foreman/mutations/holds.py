"""A user's holds on work (ADR-0043): Pause, Stop and Resume; Block and
Unblock of a sprint or the workspace.

- **Pause** is soft and belongs to tasks. On a sprint or the workspace it
  is a bulk action that pauses each unfinished task there; there is no
  paused sprint. Any task can then be resumed on its own.
- **Stop** is a Pause that cuts the running step now. It is offered only
  while a step is running in what it would stop.
- **Resume** lifts pauses, on a task or on everything in a sprint or the
  workspace. It never lifts a block.
- **Block** of a sprint or the workspace holds everything under it until
  Unblock, set where it was set. A task's own Block is in ``tasks``.

What a hold holds downstream (a task's next steps, what waits for it, the
sprint's finish, the next sprint's start) is the engine's to honour.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from uuid import uuid4

from ..domain.holds import (
    PAUSABLE_TASK_STATUSES,
    PAUSE_MODES,
    WORKSPACE_SCOPE_ID,
    LevelBlock,
)
from ..domain.models import Event, Sprint, Task
from .base import MutationBase, MutationError

#: The sprints whose tasks a Pause or a Block reaches: work that may still run.
HOLDABLE_SPRINT_STATUSES: frozenset[str] = frozenset({"planned", "active"})


@dataclass(frozen=True)
class HoldChange:
    """What one Pause, Stop or Resume changed: the tasks, in sprint order."""

    tasks: tuple[Task, ...]

    @property
    def task_keys(self) -> list[str]:
        return [task.task_key or task.id for task in self.tasks]


class HoldMutations(MutationBase):
    """Pausing, stopping and resuming work, and blocking sprints and the workspace."""

    # ── Who and when ─────────────────────────────────────────────────────

    def _who(self) -> str:
        return self.actor or self.via

    def _stamp(self) -> str:
        return self._now().isoformat()

    # ── A task ───────────────────────────────────────────────────────────

    def pause_task(self, task: Task, *, mode: str = "finish_step") -> Task:
        """Pause one task: its running step finishes (``now``: is cut), then it waits."""

        if mode not in PAUSE_MODES:
            raise MutationError(f"Unknown pause mode {mode!r}.")
        self._require_holdable_task(task)
        if mode == "now" and not self._running(task):
            raise MutationError(
                f"{self._key(task)} is not running a step, so there is nothing to stop. "
                "Pause it instead."
            )
        if task.paused_at and mode != "now":
            raise MutationError(f"{self._key(task)} is already paused.")
        self.store.pause_tasks([task.id], by=self._who(), at=self._stamp(), mode=mode)
        fresh = self._fresh(task)
        self._audit(
            fresh,
            "human.task_stopped" if mode == "now" else "human.task_paused",
            step="stop" if mode == "now" else "pause",
            step_at=fresh.workflow_current_step,
        )
        return fresh

    def resume_task(self, task: Task) -> Task:
        """Lift one task's pause. Refused under a block, which only Unblock lifts."""

        above = self._block_above(task)
        if above is not None:
            raise MutationError(
                f"{self._key(task)} is under a block on the {above.scope}: "
                f"{above.reason}. Unblock the {above.scope} first."
            )
        if task.block_requested:
            raise MutationError(
                f"{self._key(task)} is being blocked; unblock it instead."
            )
        if not task.paused_at:
            raise MutationError(f"{self._key(task)} is not paused.")
        self.store.resume_tasks([task.id])
        fresh = self._fresh(task)
        self._audit(fresh, "human.task_resumed", step="resume")
        return fresh

    # ── A sprint ─────────────────────────────────────────────────────────

    def pause_sprint(self, sprint: Sprint, *, mode: str = "finish_step") -> HoldChange:
        """Pause each unfinished task of a sprint; ``now`` also cuts the running step."""

        if mode not in PAUSE_MODES:
            raise MutationError(f"Unknown pause mode {mode!r}.")
        self._require_holdable_sprint(sprint)
        tasks = self._pausable(self.store.list_tasks(sprint_id=sprint.id))
        return self._pause_many(
            tasks,
            mode=mode,
            nothing=f"Nothing in sprint '{sprint.title}' can be paused.",
            not_running=f"Nothing in sprint '{sprint.title}' is running a step. Pause it instead.",
            record=lambda change: self._sprint_event(
                sprint,
                "human.sprint_stopped" if mode == "now" else "human.sprint_paused",
                change,
            ),
        )

    def resume_sprint(self, sprint: Sprint) -> HoldChange:
        """Lift the pause of every task in a sprint. Blocks stay."""

        self._require_holdable_sprint(sprint)
        tasks = self.store.list_tasks(sprint_id=sprint.id)
        return self._resume_many(
            tasks,
            nothing=f"Nothing in sprint '{sprint.title}' is paused.",
            record=lambda change: self._sprint_event(sprint, "human.sprint_resumed", change),
        )

    def block_sprint(self, sprint: Sprint, reason: str) -> LevelBlock:
        """Hold a sprint and everything in it until it is unblocked."""

        self._require_holdable_sprint(sprint)
        clean = self._reason(reason)
        if self.store.get_sprint_block(sprint.id) is not None:
            raise MutationError(f"Sprint '{sprint.title}' is already blocked.")
        block = self.store.set_level_block(
            LevelBlock(
                scope="sprint",
                scope_id=sprint.id,
                project_id=sprint.project_id,
                reason=clean,
                set_by=self._who(),
                set_at=self._stamp(),
            )
        )
        self._sprint_event(sprint, "human.sprint_blocked", None, reason=clean)
        return block

    def unblock_sprint(self, sprint: Sprint) -> LevelBlock:
        """Lift a sprint's block. Tasks paused one by one stay paused."""

        block = self.store.get_sprint_block(sprint.id)
        if block is None:
            raise MutationError(f"Sprint '{sprint.title}' is not blocked.")
        self.store.delete_level_block("sprint", sprint.id)
        self._sprint_event(sprint, "human.sprint_unblocked", None, reason=block.reason)
        return block

    # ── The workspace ────────────────────────────────────────────────────

    def pause_all(self, *, mode: str = "finish_step") -> HoldChange:
        """Pause every unfinished task of every planned or active sprint."""

        if mode not in PAUSE_MODES:
            raise MutationError(f"Unknown pause mode {mode!r}.")
        return self._pause_many(
            self._pausable(self._workspace_tasks()),
            mode=mode,
            nothing="Nothing in the workspace can be paused.",
            not_running="Nothing in the workspace is running a step. Pause all instead.",
            record=lambda change: self._workspace_events(
                "human.workspace_stopped" if mode == "now" else "human.workspace_paused",
                change.tasks,
            ),
        )

    def resume_all(self) -> HoldChange:
        """Lift every pause in the workspace. Blocks stay."""

        return self._resume_many(
            self._workspace_tasks(),
            nothing="Nothing in the workspace is paused.",
            record=lambda change: self._workspace_events(
                "human.workspace_resumed", change.tasks
            ),
        )

    def block_all(self, reason: str) -> LevelBlock:
        """Hold every project's work until the workspace is unblocked."""

        clean = self._reason(reason)
        if self.store.get_workspace_block() is not None:
            raise MutationError("The workspace is already blocked.")
        block = self.store.set_level_block(
            LevelBlock(
                scope="workspace",
                scope_id=WORKSPACE_SCOPE_ID,
                project_id=None,
                reason=clean,
                set_by=self._who(),
                set_at=self._stamp(),
            )
        )
        self._workspace_events("human.workspace_blocked", (), reason=clean, every_project=True)
        return block

    def unblock_all(self) -> LevelBlock:
        """Lift the workspace's block. Pauses and sprint blocks stay."""

        block = self.store.get_workspace_block()
        if block is None:
            raise MutationError("The workspace is not blocked.")
        self.store.delete_level_block("workspace", WORKSPACE_SCOPE_ID)
        self._workspace_events(
            "human.workspace_unblocked", (), reason=block.reason, every_project=True
        )
        return block

    # ── Joining a paused sprint ──────────────────────────────────────────

    def join_sprint_pause(self, task: Task, *, newcomers: Iterable[str] = ()) -> Task:
        """Pause a task that has just joined a sprint whose work is all paused.

        So a sprint a user paused stays paused when work is added to it
        (ADR-0043). A sprint with no other unfinished task, or with one
        that is not paused, leaves the new task as it is. ``newcomers`` are
        the other tasks joining with it, which do not count.
        """

        joining = {task.id, *newcomers}
        others = [
            other
            for other in self._pausable(self.store.list_tasks(sprint_id=task.sprint_id))
            if other.id not in joining
        ]
        if not others or any(not other.paused_at for other in others):
            return task
        first = min(others, key=lambda other: other.paused_at or "")
        self.store.pause_tasks(
            [task.id],
            by=first.paused_by or self._who(),
            at=self._stamp(),
            mode="finish_step",
        )
        return self._fresh(task)

    # ── Shared ───────────────────────────────────────────────────────────

    def _pause_many(
        self,
        tasks: Sequence[Task],
        *,
        mode: str,
        nothing: str,
        not_running: str,
        record: Callable[[HoldChange], object],
    ) -> HoldChange:
        if mode == "now":
            if not any(self._running(task) for task in tasks):
                raise MutationError(not_running)
            targets = list(tasks)
        else:
            targets = [task for task in tasks if not task.paused_at]
        if not targets:
            raise MutationError(nothing)
        changed = set(
            self.store.pause_tasks(
                [task.id for task in targets], by=self._who(), at=self._stamp(), mode=mode
            )
        )
        change = HoldChange(tasks=tuple(self._fresh(t) for t in targets if t.id in changed))
        if not change.tasks:
            raise MutationError(nothing)
        record(change)
        return change

    def _resume_many(
        self,
        tasks: Iterable[Task],
        *,
        nothing: str,
        record: Callable[[HoldChange], object],
    ) -> HoldChange:
        targets = [task for task in tasks if task.paused_at and not task.block_requested]
        changed = set(self.store.resume_tasks([task.id for task in targets]))
        change = HoldChange(tasks=tuple(self._fresh(t) for t in targets if t.id in changed))
        if not change.tasks:
            raise MutationError(nothing)
        record(change)
        return change

    def _pausable(self, tasks: Sequence[Task]) -> list[Task]:
        return [task for task in tasks if task.status in PAUSABLE_TASK_STATUSES]

    def _workspace_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        for project in self.store.list_projects():
            for sprint in self.store.list_sprints(project.id):
                if sprint.is_backlog or sprint.status not in HOLDABLE_SPRINT_STATUSES:
                    continue
                tasks.extend(self.store.list_tasks(sprint_id=sprint.id))
        return tasks

    def _running(self, task: Task) -> bool:
        return bool(self.store.list_runs(task_id=task.id, status="running"))

    def _block_above(self, task: Task) -> LevelBlock | None:
        return self.store.get_workspace_block() or self.store.get_sprint_block(task.sprint_id)

    def _require_holdable_task(self, task: Task) -> None:
        sprint = self.store.get_sprint(task.sprint_id)
        if sprint is None or sprint.is_backlog:
            raise MutationError(
                f"{self._key(task)} is in the backlog, where nothing runs; there is "
                "nothing to pause."
            )
        if task.status not in PAUSABLE_TASK_STATUSES:
            raise MutationError(
                f"{self._key(task)} is {task.status}; only a task that is queued, "
                "under way or blocked can be paused."
            )

    def _require_holdable_sprint(self, sprint: Sprint) -> None:
        if sprint.is_backlog:
            raise MutationError("The backlog is not a sprint; nothing in it runs.")
        if sprint.status not in HOLDABLE_SPRINT_STATUSES:
            raise MutationError(
                f"Sprint '{sprint.title}' is {sprint.status}; only a planned or active "
                "sprint can be paused or blocked."
            )

    @staticmethod
    def _reason(reason: str) -> str:
        clean = (reason or "").strip()
        if not clean:
            raise MutationError("A block needs a reason.")
        return clean

    @staticmethod
    def _key(task: Task) -> str:
        return task.task_key or task.id

    def _fresh(self, task: Task) -> Task:
        fresh = self.store.get_task(task.id)
        if fresh is None:
            raise MutationError(f"Task {task.id} no longer exists.")
        return fresh

    def _sprint_event(
        self,
        sprint: Sprint,
        event_type: str,
        change: HoldChange | None,
        *,
        reason: str | None = None,
    ) -> Event:
        """Record one action on a sprint (ADR-0037), with the tasks it changed."""

        return self.store.save_event(
            Event(
                id=self._event_id(event_type),
                run_id=None,
                task_id=None,
                sprint_id=sprint.id,
                project_id=sprint.project_id,
                event_type=event_type,
                role_id=self.role,
                timestamp=self._stamp(),
                payload=self._payload(change.tasks if change else (), reason=reason),
            )
        )

    def _workspace_events(
        self,
        event_type: str,
        tasks: Sequence[Task],
        *,
        reason: str | None = None,
        every_project: bool = False,
    ) -> None:
        """Record one workspace action on each project it reached."""

        by_project: dict[str, list[Task]] = {}
        for task in tasks:
            by_project.setdefault(task.project_id, []).append(task)
        project_ids = (
            [project.id for project in self.store.list_projects()]
            if every_project
            else list(by_project)
        )
        for project_id in project_ids:
            self.store.save_event(
                Event(
                    id=self._event_id(event_type),
                    run_id=None,
                    task_id=None,
                    project_id=project_id,
                    event_type=event_type,
                    role_id=self.role,
                    timestamp=self._stamp(),
                    payload=self._payload(by_project.get(project_id, ()), reason=reason),
                )
            )

    def _payload(self, tasks: Sequence[Task], *, reason: str | None) -> dict[str, object]:
        payload: dict[str, object] = {"via": self.via, "by": self.actor}
        if tasks:
            payload["task_ids"] = [task.id for task in tasks]
            payload["task_keys"] = [self._key(task) for task in tasks]
        if reason:
            payload["reason"] = reason
        if self.proposal_id:
            payload["proposal_id"] = self.proposal_id
        return payload

    def _event_id(self, event_type: str) -> str:
        now = self._now()
        return f"evt-{event_type.split('.')[-1]}-{now.strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex[:8]}"
