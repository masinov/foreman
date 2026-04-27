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
    completion_evidence: CompletionEvidence | None = None
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
    failure_type: str | None = None  # e.g. 'preflight', 'infrastructure', 'policy', 'gate'
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
class HumanGateDecision:
    """A durable record of one human decision at a workflow gate."""

    id: str
    task_id: str
    project_id: str
    workflow_step: str
    decision: str  # 'approve', 'deny', or 'steer'
    note: str | None = None
    decided_by: str = "human"
    decided_at: str = field(default_factory=utc_now_text)
    run_id: str | None = None


@dataclass(slots=True, frozen=True)
class CompletionEvidence:
    """Structured evidence summary for a task completion decision.

    Bundles acceptance-criteria text, branch diff context, changed files,
    agent outputs, and built-in test results so downstream review
    (human or automated) can assess whether the implementation actually
    satisfies the task intent — not just whether the developer marked
    it done or the reviewer approved it.

    New fields added for audit-ready proof object:
    - base_sha / head_sha / merge_base_sha: git positional reference
    - commit_count: commits in the branch
    - test_command / test_exit_code: structured test record
    - review_outcome / security_review_outcome: reviewer verdicts
    - criteria_checklist: per-criterion addressed status
    - proof_status: pending | passed | failed
    - failure_reasons: reasons for failure (when proof_status=failed)
    """

    task_id: str
    task_title: str
    acceptance_criteria: str
    criteria_count: int = 0
    criteria_addressed: int = 0
    criteria_partially_addressed: int = 0
    changed_files: tuple[str, ...] = ()
    diff_context_lines: int = 0
    branch_diff_stat: str = ""
    agent_outputs: tuple[str, ...] = ()
    builtin_test_result: str = ""
    builtin_test_passed: bool = False
    builtin_test_detail: str = ""
    score: float = 0.0
    score_breakdown: str = ""
    verdict: str = "unknown"
    verdict_reasons: tuple[str, ...] = ()
    built_at: str = field(default_factory=utc_now_text)
    # Git positional reference
    base_sha: str = ""
    head_sha: str = ""
    merge_base_sha: str = ""
    commit_count: int = 0
    # Structured test record
    test_command: str = ""
    test_exit_code: int | None = None
    # Review verdicts
    review_outcome: str = ""
    security_review_outcome: str = ""
    # Criteria checklist: list of {criterion, status, evidence}
    # status: "passed" | "failed" | "partial" | "unknown"
    criteria_checklist: tuple[dict[str, str], ...] = field(default_factory=tuple)
    # Proof status
    proof_status: str = "pending"
    failure_reasons: tuple[str, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        parts = [
            f"Evidence score: {self.score:.1f}/100 ({self.verdict})",
            f"Criteria: {self.criteria_addressed}/{self.criteria_count} addressed"
            + (f" + {self.criteria_partially_addressed} partial" if self.criteria_partially_addressed else ""),
            f"Score breakdown: {self.score_breakdown}" if self.score_breakdown else None,
            f"Changed files: {', '.join(self.changed_files)}" if self.changed_files else "Changed files: (none)",
            f"Branch diff: {self.branch_diff_stat}" if self.branch_diff_stat else None,
            f"Tests: {'PASSED' if self.builtin_test_passed else 'FAILED'}" if self.builtin_test_result else None,
            f"Verdict reasons: {'; '.join(self.verdict_reasons)}" if self.verdict_reasons else None,
            f"Criteria text: {self.acceptance_criteria[:300]!r}" if self.acceptance_criteria else None,
        ]
        return "\n".join(p for p in parts if p is not None)


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


LeaseStatus = Literal["active", "released", "expired"]


@dataclass(slots=True)
class Lease:
    """A persisted lease on a project resource (task, run, etc.)."""

    id: str
    project_id: str
    resource_type: str
    resource_id: str
    holder_id: str
    lease_token: str
    fencing_token: int = 1
    status: LeaseStatus = "active"
    acquired_at: str = field(default_factory=utc_now_text)
    heartbeat_at: str = field(default_factory=utc_now_text)
    expires_at: str = field(default_factory=utc_now_text)
    released_at: str | None = None
