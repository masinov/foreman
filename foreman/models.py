"""Typed model definitions for Foreman entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

JsonDict = dict[str, Any]

ProjectMethodology = Literal["development"]
AutonomyLevel = Literal["directed", "supervised", "autonomous"]
GateStatus = Literal["pending", "accepted", "rejected", "dismissed"]
SprintStatus = Literal["planned", "active", "completed", "cancelled"]
TaskStatus = Literal["todo", "in_progress", "blocked", "done", "cancelled"]
TaskType = Literal["feature", "fix", "refactor", "docs", "spike", "chore"]
RunStatus = Literal["pending", "running", "completed", "failed", "killed", "timeout"]

SPRINT_STATUSES: tuple[SprintStatus, ...] = (
    "planned",
    "active",
    "completed",
    "cancelled",
)
TASK_STATUSES: tuple[TaskStatus, ...] = (
    "todo",
    "in_progress",
    "blocked",
    "done",
    "cancelled",
)
TASK_TYPES: tuple[TaskType, ...] = (
    "feature",
    "fix",
    "refactor",
    "docs",
    "spike",
    "chore",
)
RUN_STATUSES: tuple[RunStatus, ...] = (
    "pending",
    "running",
    "completed",
    "failed",
    "killed",
    "timeout",
)


def utc_now_text() -> str:
    """Return a stable high-resolution UTC timestamp string for persisted records."""

    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


AUTONOMY_LEVELS: tuple[AutonomyLevel, ...] = ("directed", "supervised", "autonomous")


@dataclass(slots=True)
class Project:
    """A tracked Foreman project."""

    id: str
    name: str
    repo_path: str
    workflow_id: str
    spec_path: str | None = None
    methodology: ProjectMethodology = "development"
    default_branch: str = "main"
    autonomy_level: AutonomyLevel = "supervised"
    settings: JsonDict = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_text)
    updated_at: str = field(default_factory=utc_now_text)


@dataclass(slots=True)
class Sprint:
    """A persisted sprint record."""

    id: str
    project_id: str
    title: str
    goal: str | None = None
    status: SprintStatus = "planned"
    order_index: int = 0
    created_at: str = field(default_factory=utc_now_text)
    started_at: str | None = None
    completed_at: str | None = None


@dataclass(slots=True)
class Task:
    """A persisted task record."""

    id: str
    sprint_id: str
    project_id: str
    title: str
    description: str | None = None
    status: TaskStatus = "todo"
    task_type: TaskType = "feature"
    priority: int = 0
    order_index: int = 0
    branch_name: str | None = None
    assigned_role: str | None = None
    acceptance_criteria: str | None = None
    blocked_reason: str | None = None
    created_by: str = "human"
    depends_on_task_ids: list[str] = field(default_factory=list)
    workflow_current_step: str | None = None
    workflow_carried_output: str | None = None
    step_visit_counts: dict[str, int] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_text)
    started_at: str | None = None
    completed_at: str | None = None


@dataclass(slots=True)
class Run:
    """A persisted agent run."""

    id: str
    task_id: str
    project_id: str
    role_id: str
    workflow_step: str
    agent_backend: str
    status: RunStatus = "pending"
    outcome: str | None = None
    outcome_detail: str | None = None
    model: str | None = None
    session_id: str | None = None
    branch_name: str | None = None
    prompt_text: str | None = None
    cost_usd: float = 0.0
    token_count: int = 0
    duration_ms: int | None = None
    retry_count: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str = field(default_factory=utc_now_text)


@dataclass(slots=True)
class DecisionGate:
    """A persisted decision gate raised when the agent detects a sprint ordering conflict."""

    id: str
    project_id: str
    sprint_id: str
    conflict_description: str
    suggested_order: list[str] = field(default_factory=list)
    suggested_reason: str = ""
    status: GateStatus = "pending"
    raised_at: str = field(default_factory=utc_now_text)
    resolved_at: str | None = None
    resolved_by: str | None = None


@dataclass(slots=True)
class Event:
    """A persisted structured event emitted during a run."""

    id: str
    run_id: str
    task_id: str
    project_id: str
    event_type: str
    timestamp: str = field(default_factory=utc_now_text)
    role_id: str | None = None
    payload: JsonDict = field(default_factory=dict)
