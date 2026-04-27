"""Versioned event constructors and validators for Foreman audit log.

Each constructor emits a typed dict payload with a consistent `schema_version`
field so event consumers can evolve payloads without breaking older parsers.

Event schema version lifecycle:
- major version bumps indicate a breaking change (removed fields, changed types)
- minor version bumps indicate additive changes (new optional fields)
- We currently track schema_version as a string "1.0", "1.1", etc.
  For now, use the plain integer field name to match existing event payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "1.0"


# ----------------------------------------------------------------------
# Event record types
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class EventConstructor:
    """A named event with a versioned payload constructor."""

    event_type: str
    version: str = SCHEMA_VERSION


AGENT_STARTED = EventConstructor("agent.started")
AGENT_COMPLETED = EventConstructor("agent.completed")
AGENT_ERROR = EventConstructor("agent.error")
AGENT_KILLED = EventConstructor("agent.killed")
AGENT_MESSAGE = EventConstructor("agent.message")
AGENT_COST_UPDATE = EventConstructor("agent.cost_update")

WORKFLOW_STEP_COMPLETED = EventConstructor("workflow.step_completed")
WORKFLOW_TRANSITION = EventConstructor("workflow.transition")
WORKFLOW_NO_TRANSITION = EventConstructor("workflow.no_transition")

ENGINE_TEST_STARTED = EventConstructor("engine.test_started")
ENGINE_TEST_RUN = EventConstructor("engine.test_run")
ENGINE_TEST_OUTPUT = EventConstructor("engine.test_output")

ENGINE_MERGE_FAILED = EventConstructor("engine.merge_failed")
ENGINE_MERGE_BLOCKED = EventConstructor("engine.merge_blocked")
ENGINE_COMPLETION_GUARD = EventConstructor("engine.completion_guard")
ENGINE_COMPLETION_EVIDENCE = EventConstructor("engine.completion_evidence")
ENGINE_SUPERVISOR_MERGE = EventConstructor("engine.supervisor_merge")

ENGINE_CRASH_RECOVERY = EventConstructor("engine.crash_recovery")
ENGINE_BRANCH_VIOLATION = EventConstructor("engine.branch_violation")
ENGINE_TASK_CREATED = EventConstructor("engine.task_created")

SIGNAL_TASK_STARTED = EventConstructor("signal.task_started")
SIGNAL_TASK_CREATED = EventConstructor("signal.task_created")
SIGNAL_PROGRESS = EventConstructor("signal.progress")
SIGNAL_BLOCKER = EventConstructor("signal.blocker")
SIGNAL_INVALID = EventConstructor("signal.invalid")
SIGNAL_UNKNOWN = EventConstructor("signal.unknown")

GATE_COST_EXCEEDED = EventConstructor("gate.cost_exceeded")
GATE_TIME_EXCEEDED = EventConstructor("gate.time_exceeded")


# ----------------------------------------------------------------------
# Constructor helpers
# ----------------------------------------------------------------------


@dataclass
class EventPayload:
    """A constructed event payload with schema version."""

    event_type: str
    payload: dict[str, Any]
    schema_version: str = field(default=SCHEMA_VERSION)


def _build(
    constructor: EventConstructor,
    payload: dict[str, Any],
    /,
    **extra: Any,
) -> EventPayload:
    """Build a versioned event payload.

    Args:
        constructor: the EventConstructor defining event_type and schema version
        payload: event-specific fields
        extra: additional fields merged into payload (e.g. timestamp)
    """
    data = {"schema_version": constructor.version, **payload, **extra}
    return EventPayload(event_type=constructor.event_type, payload=data)


def agent_started(
    role_id: str,
    backend: str,
    model: str | None = None,
    session_id: str | None = None,
) -> EventPayload:
    return _build(AGENT_STARTED, {"role_id": role_id, "backend": backend, "model": model, "session_id": session_id})


def agent_completed(
    result: str | None = None,
    cost_usd: float = 0.0,
    token_count: int = 0,
) -> EventPayload:
    return _build(
        AGENT_COMPLETED,
        {"result": result, "cost_usd": cost_usd, "token_count": token_count},
    )


def agent_error(message: str) -> EventPayload:
    return _build(AGENT_ERROR, {"error": message})


def agent_killed(reason: str, gate_type: str | None = None) -> EventPayload:
    return _build(AGENT_KILLED, {"reason": reason, "gate_type": gate_type})


def workflow_step_completed(
    step: str,
    outcome: str,
) -> EventPayload:
    return _build(WORKFLOW_STEP_COMPLETED, {"step": step, "outcome": outcome})


def workflow_transition(
    from_step: str,
    to_step: str,
    trigger: str,
) -> EventPayload:
    return _build(
        WORKFLOW_TRANSITION,
        {"from_step": from_step, "to_step": to_step, "trigger": trigger},
    )


def workflow_no_transition(
    step: str,
    outcome: str,
) -> EventPayload:
    return _build(WORKFLOW_NO_TRANSITION, {"step": step, "outcome": outcome})


def engine_test_started(command: str) -> EventPayload:
    return _build(ENGINE_TEST_STARTED, {"command": command})


def engine_test_run(
    command: str,
    exit_code: int | None,
    passed: bool,
    stdout: str = "",
    stderr: str = "",
    output_tail: str = "",
) -> EventPayload:
    return _build(
        ENGINE_TEST_RUN,
        {
            "command": command,
            "exit_code": exit_code,
            "passed": passed,
            "stdout": stdout,
            "stderr": stderr,
            "output_tail": output_tail,
        },
    )


def engine_completion_guard(
    verdict: str,
    score: float,
    score_breakdown: str,
    changed_files: list[str],
    reasons: list[str],
) -> EventPayload:
    return _build(
        ENGINE_COMPLETION_GUARD,
        {
            "verdict": verdict,
            "score": score,
            "score_breakdown": score_breakdown,
            "changed_files": changed_files,
            "reasons": reasons,
        },
    )


def engine_completion_evidence(
    task_id: str,
    criteria_count: int,
    criteria_addressed: int,
    score: float,
    verdict: str,
    proof_status: str,
    *,
    criteria_partially_addressed: int = 0,
    changed_files: list[str] | None = None,
    builtin_test_passed: bool = False,
    failure_reasons: list[str] | None = None,
) -> EventPayload:
    return _build(
        ENGINE_COMPLETION_EVIDENCE,
        {
            "task_id": task_id,
            "criteria_count": criteria_count,
            "criteria_addressed": criteria_addressed,
            "criteria_partially_addressed": criteria_partially_addressed,
            "changed_files": changed_files or [],
            "builtin_test_passed": builtin_test_passed,
            "score": score,
            "verdict": verdict,
            "proof_status": proof_status,
            "failure_reasons": failure_reasons or [],
        },
    )


def engine_supervisor_merge(
    branch: str,
    target: str,
    task_id: str,
    evidence_score: float | None,
    evidence_verdict: str | None,
) -> EventPayload:
    return _build(
        ENGINE_SUPERVISOR_MERGE,
        {
            "branch": branch,
            "target": target,
            "task_id": task_id,
            "evidence_score": evidence_score,
            "evidence_verdict": evidence_verdict,
        },
    )


def engine_crash_recovery(
    run_id: str,
    task_id: str,
    previous_status: str,
    lease_id: str | None = None,
    holder_id: str | None = None,
    fencing_token: int | None = None,
) -> EventPayload:
    return _build(
        ENGINE_CRASH_RECOVERY,
        {
            "run_id": run_id,
            "task_id": task_id,
            "previous_status": previous_status,
            "lease_id": lease_id,
            "holder_id": holder_id,
            "fencing_token": fencing_token,
        },
    )


def engine_branch_violation(
    branch: str,
    detail: str,
) -> EventPayload:
    return _build(ENGINE_BRANCH_VIOLATION, {"branch": branch, "detail": detail})


def engine_task_created(
    task_id: str,
    title: str,
    task_type: str,
    created_by: str,
) -> EventPayload:
    return _build(
        ENGINE_TASK_CREATED,
        {
            "task_id": task_id,
            "title": title,
            "task_type": task_type,
            "created_by": created_by,
        },
    )


def gate_cost_exceeded(
    task_id: str,
    total_cost_usd: float,
    cost_limit_usd: float,
) -> EventPayload:
    return _build(
        GATE_COST_EXCEEDED,
        {
            "task_id": task_id,
            "total_cost_usd": total_cost_usd,
            "cost_limit_usd": cost_limit_usd,
        },
    )


def gate_time_exceeded(
    task_id: str,
    total_duration_ms: int,
    time_limit_ms: int,
) -> EventPayload:
    return _build(
        GATE_TIME_EXCEEDED,
        {
            "task_id": task_id,
            "total_duration_ms": total_duration_ms,
            "time_limit_ms": time_limit_ms,
        },
    )
