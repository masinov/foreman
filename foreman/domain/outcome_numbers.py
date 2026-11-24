"""How well a project's agents do, computed from what the engine recorded (ADR-0034).

``outcome_numbers`` is a pure function over the tasks of one project (or one
of its sprints), their runs and their events. It answers: how many tasks
merged, how many passed first time, what sent work back, how often a person
was asked or stepped in unasked, what a merged task cost, and the same per
agent role and model. Nothing here reads the database.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from statistics import median
from typing import Any

from .models import Event, Run, Task

#: The events the numbers are computed from. The store reads only these.
STEP_STARTED = "workflow.step_started"
TRANSITION = "workflow.transition"
PAUSED = "workflow.paused"
RESUMED = "workflow.resumed"
MERGED = "engine.merge"
CLOSED_BY_HAND = "human.task_completed"

#: What a person does to a started task without a gate asking for it.
INTERVENTION_EVENTS: tuple[str, ...] = (
    "human.message",
    "human.task_edited",
    "human.task_blocked",
    "human.task_unblocked",
    "human.task_cancelled",
    CLOSED_BY_HAND,
    "human.task_reopened",
    "human.task_unplanned",
)

OUTCOME_EVENT_TYPES: tuple[str, ...] = (
    STEP_STARTED,
    TRANSITION,
    PAUSED,
    RESUMED,
    MERGED,
    *INTERVENTION_EVENTS,
)

#: Why work went back to the step that builds it.
SEND_BACK_CAUSES: tuple[str, ...] = ("tests", "review", "person", "merge_conflict", "other")

_CAUSE_OF_BUILTIN: dict[str, str] = {
    "_builtin:run_tests": "tests",
    "_builtin:human_gate": "person",
    "_builtin:merge": "merge_conflict",
}

#: Backends whose runs are an agent's, not the engine's or a person's records.
AGENT_BACKENDS: frozenset[str] = frozenset({"claude_code", "codex"})

_FAILED_RUN_STATUSES = frozenset({"failed", "killed"})


@dataclass(frozen=True, slots=True)
class Tokens:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_creation: int = 0


@dataclass(frozen=True, slots=True)
class TaskCounts:
    started: int
    merged: int
    passed_first_time: int
    passed_first_time_conflicts_aside: int
    closed_by_hand: int
    cancelled: int
    not_finished: int


@dataclass(frozen=True, slots=True)
class PersonNumbers:
    decisions_asked: int
    decisions_waiting: int
    median_wait_seconds: float | None
    interventions: int
    interventions_by_kind: dict[str, int]


@dataclass(frozen=True, slots=True)
class CostNumbers:
    total_usd: float
    per_merged_task_usd: float | None
    not_merged_usd: float
    tokens: Tokens
    tokens_per_merged_task: Tokens | None


@dataclass(frozen=True, slots=True)
class RoleModelNumbers:
    role: str
    model: str | None
    runs: int
    failed_runs: int
    cost_usd: float
    tokens: Tokens
    duration_seconds: float
    send_backs_caused: int
    tasks_built_merged: int
    tasks_built_passed_first_time: int


@dataclass(frozen=True, slots=True)
class OutcomeNumbers:
    tasks: TaskCounts
    send_backs: dict[str, int]
    send_backs_by_reviewer: dict[str, int]
    people: PersonNumbers
    cost: CostNumbers
    median_minutes_to_merge: float | None
    by_role_and_model: list[RoleModelNumbers] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _when(text: str | None) -> datetime | None:
    if not text:
        return None
    # The store writes both ``...Z`` and ``...+00:00``; Python before 3.11
    # reads only the second.
    value = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _seconds(start: str | None, end: str | None) -> float | None:
    a, b = _when(start), _when(end)
    if a is None or b is None:
        return None
    return max((b - a).total_seconds(), 0.0)


def _send_back_cause(event: Event) -> str:
    role = event.role_id or ""
    if role in _CAUSE_OF_BUILTIN:
        return _CAUSE_OF_BUILTIN[role]
    if role and not role.startswith("_builtin:"):
        return "review"
    return "other"


def _tokens(runs: Iterable[Run]) -> Tokens:
    total = [0, 0, 0, 0]
    for run in runs:
        usage = run.token_usage
        total[0] += usage.input
        total[1] += usage.output
        total[2] += usage.cache_read
        total[3] += usage.cache_creation
    return Tokens(*total)


def _per(tokens: Tokens, count: int) -> Tokens | None:
    if count <= 0:
        return None
    return Tokens(
        input=round(tokens.input / count),
        output=round(tokens.output / count),
        cache_read=round(tokens.cache_read / count),
        cache_creation=round(tokens.cache_creation / count),
    )


def _is_agent_run(run: Run) -> bool:
    return run.agent_backend in AGENT_BACKENDS and not run.role_id.startswith("_builtin:")


#: Task statuses in which nothing is waiting any more.
_SETTLED = frozenset({"done", "cancelled"})


class _TaskStory:
    """One task's events in order, read once."""

    def __init__(self, task: Task, events: Sequence[Event]) -> None:
        self.task = task
        ordered = sorted(events, key=lambda e: e.timestamp)
        started = [e for e in ordered if e.event_type == STEP_STARTED]
        self.first_started_at: str | None = started[0].timestamp if started else None
        self.entry_step: str | None = (
            str(started[0].payload.get("step") or "") or None if started else None
        )
        self.merged_at: str | None = next(
            (e.timestamp for e in ordered if e.event_type == MERGED), None
        )
        self.closed_by_hand = any(e.event_type == CLOSED_BY_HAND for e in ordered)
        self.send_backs: list[Event] = [
            e
            for e in ordered
            if e.event_type == TRANSITION
            and self.entry_step is not None
            and e.payload.get("to_step") == self.entry_step
            and e.payload.get("from_step") != self.entry_step
        ]
        self.interventions: list[Event] = [
            e
            for e in ordered
            if e.event_type in INTERVENTION_EVENTS
            and self.first_started_at is not None
            and e.timestamp >= self.first_started_at
        ]
        # A decision is asked at each gate pause and answered by the resume
        # that follows. One still waits only if it is the last and the task
        # is still open: a task closed or cancelled at a gate was settled
        # without an answer there, and is neither waiting nor timed.
        self.decisions_asked = 0
        self.waits: list[float] = []
        pending: str | None = None
        for e in ordered:
            if e.event_type == PAUSED and e.payload.get("reason") == "human_gate":
                self.decisions_asked += 1
                pending = e.timestamp
            elif e.event_type == RESUMED and pending is not None:
                self.waits.append(_seconds(pending, e.timestamp))
                pending = None
        self.decision_waiting = pending is not None and task.status not in _SETTLED

    def passed_first_time(self, *, conflicts_aside: bool = False) -> bool:
        """Merged with no send-back (leaving merge conflicts aside if asked)."""

        return self.merged and all(
            conflicts_aside and _send_back_cause(e) == "merge_conflict"
            for e in self.send_backs
        )

    @property
    def started(self) -> bool:
        return self.first_started_at is not None

    @property
    def merged(self) -> bool:
        return self.merged_at is not None


def outcome_numbers(
    tasks: Sequence[Task], runs: Sequence[Run], events: Sequence[Event]
) -> OutcomeNumbers:
    """The outcome numbers of *tasks*, from their *runs* and *events* (ADR-0034)."""

    events_by_task: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        # A sprint's or the project's own records belong to no task (ADR-0037).
        if event.task_id is not None:
            events_by_task[event.task_id].append(event)
    runs_by_task: dict[str, list[Run]] = defaultdict(list)
    for run in runs:
        runs_by_task[run.task_id].append(run)

    stories = [_TaskStory(task, events_by_task.get(task.id, ())) for task in tasks]
    stories = [story for story in stories if story.started]
    counted = {story.task.id for story in stories}
    merged = [story for story in stories if story.merged]

    task_counts = TaskCounts(
        started=len(stories),
        merged=len(merged),
        passed_first_time=sum(1 for s in merged if s.passed_first_time()),
        passed_first_time_conflicts_aside=sum(
            1 for s in merged if s.passed_first_time(conflicts_aside=True)
        ),
        closed_by_hand=sum(1 for s in stories if not s.merged and s.closed_by_hand),
        cancelled=sum(1 for s in stories if not s.merged and s.task.status == "cancelled"),
        not_finished=sum(
            1
            for s in stories
            if not s.merged and not s.closed_by_hand and s.task.status != "cancelled"
        ),
    )

    run_by_id = {run.id: run for run in runs}
    send_backs = {cause: 0 for cause in SEND_BACK_CAUSES}
    by_reviewer: dict[str, int] = defaultdict(int)
    caused: dict[tuple[str, str | None], int] = defaultdict(int)
    for story in stories:
        for event in story.send_backs:
            cause = _send_back_cause(event)
            send_backs[cause] += 1
            if cause == "review" and event.role_id:
                by_reviewer[event.role_id] += 1
                cause_run = run_by_id.get(event.run_id)
                caused[(event.role_id, cause_run.model if cause_run else None)] += 1

    decided = [w for s in stories for w in s.waits]
    by_kind: dict[str, int] = defaultdict(int)
    for story in stories:
        for event in story.interventions:
            by_kind[event.event_type.removeprefix("human.")] += 1
    people = PersonNumbers(
        decisions_asked=sum(s.decisions_asked for s in stories),
        decisions_waiting=sum(1 for s in stories if s.decision_waiting),
        median_wait_seconds=round(median(decided), 1) if decided else None,
        interventions=sum(by_kind.values()),
        interventions_by_kind=dict(sorted(by_kind.items())),
    )

    counted_runs = [run for run in runs if run.task_id in counted]
    merged_ids = {story.task.id for story in merged}
    merged_runs = [run for run in counted_runs if run.task_id in merged_ids]
    total_usd = sum(run.cost_usd for run in counted_runs)
    merged_usd = sum(run.cost_usd for run in merged_runs)
    merged_tokens = _tokens(merged_runs)
    cost = CostNumbers(
        total_usd=round(total_usd, 4),
        per_merged_task_usd=round(merged_usd / len(merged), 4) if merged else None,
        not_merged_usd=round(total_usd - merged_usd, 4),
        tokens=_tokens(counted_runs),
        tokens_per_merged_task=_per(merged_tokens, len(merged)),
    )

    to_merge = [
        seconds
        for story in merged
        if (seconds := _seconds(story.first_started_at, story.merged_at)) is not None
    ]

    return OutcomeNumbers(
        tasks=task_counts,
        send_backs=send_backs,
        send_backs_by_reviewer=dict(sorted(by_reviewer.items())),
        people=people,
        cost=cost,
        median_minutes_to_merge=round(median(to_merge) / 60, 1) if to_merge else None,
        by_role_and_model=_by_role_and_model(
            stories, runs_by_task, counted_runs, caused
        ),
    )


def _by_role_and_model(
    stories: Sequence[_TaskStory],
    runs_by_task: dict[str, list[Run]],
    counted_runs: Sequence[Run],
    caused: dict[tuple[str, str | None], int],
) -> list[RoleModelNumbers]:
    groups: dict[tuple[str, str | None], list[Run]] = defaultdict(list)
    for run in counted_runs:
        if _is_agent_run(run):
            groups[(run.role_id, run.model)].append(run)

    built_merged: dict[tuple[str, str | None], int] = defaultdict(int)
    built_first: dict[tuple[str, str | None], int] = defaultdict(int)
    for story in stories:
        if not story.merged:
            continue
        builder = next(
            (
                run
                for run in sorted(
                    runs_by_task.get(story.task.id, ()),
                    key=lambda r: r.started_at or r.created_at,
                )
                if _is_agent_run(run) and run.workflow_step == story.entry_step and run.model
            ),
            None,
        )
        if builder is None:
            continue
        key = (builder.role_id, builder.model)
        built_merged[key] += 1
        if story.passed_first_time():
            built_first[key] += 1

    rows = [
        RoleModelNumbers(
            role=role,
            model=model,
            runs=len(group),
            failed_runs=sum(
                1
                for run in group
                if run.status in _FAILED_RUN_STATUSES or run.outcome == "error"
            ),
            cost_usd=round(sum(run.cost_usd for run in group), 4),
            tokens=_tokens(group),
            duration_seconds=round(sum((run.duration_ms or 0) for run in group) / 1000, 1),
            send_backs_caused=caused.get((role, model), 0),
            tasks_built_merged=built_merged.get((role, model), 0),
            tasks_built_passed_first_time=built_first.get((role, model), 0),
        )
        for (role, model), group in groups.items()
    ]
    rows.sort(key=lambda row: (row.role, -row.runs, row.model or ""))
    return rows
