"""Turning SQLite rows into Foreman models, and values into JSON."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from ..models import (
    ApiToken,
    CompletionEvidence,
    DecisionGate,
    EngineCommand,
    Event,
    HumanGateDecision,
    Lease,
    MergeWaiver,
    NotificationDelivery,
    NotificationDestination,
    Project,
    Run,
    TokenUsage,
    Sprint,
    Task,
)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _json_loads(raw_value: str) -> Any:
    return json.loads(raw_value) if raw_value else None


def _load_json_dict(raw_value: str) -> dict[str, Any]:
    parsed = _json_loads(raw_value)
    if parsed in (None, ""):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _load_json_list(raw_value: str) -> list[str]:
    parsed = _json_loads(raw_value)
    if parsed in (None, ""):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _serialize_evidence(evidence: Any) -> str:
    """Serialize completion evidence (dataclass or dict) to JSON."""
    if evidence is None:
        return ""
    if isinstance(evidence, dict):
        return _json_dumps(evidence)
    try:
        from dataclasses import asdict
        if isinstance(evidence, CompletionEvidence):
            return _json_dumps(asdict(evidence))
        return _json_dumps(asdict(evidence))
    except Exception:
        return _json_dumps({"error": str(evidence)})


def derive_task_key_prefix(name: str) -> str:
    """Derive a short uppercase project key prefix from a project name.

    Multi-word names use the initials of the first words (e.g. "My Project" ->
    "MP"); single words use their first three letters ("Foreman" -> "FOR").
    Falls back to "TASK" when no alphanumerics are present.
    """

    words = re.findall(r"[A-Za-z0-9]+", name or "")
    if not words:
        return "TASK"
    if len(words) >= 2:
        initials = "".join(word[0] for word in words[:4]).upper()
        if len(initials) >= 2:
            return initials
    return words[0][:3].upper()


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        repo_path=row["repo_path"],
        workflow_id=row["workflow_id"],
        spec_path=row["spec_path"],
        methodology=row["methodology"],
        default_branch=row["default_branch"],
        autonomy_level=row["autonomy_level"] if "autonomy_level" in row.keys() else "supervised",  # type: ignore[assignment]
        settings=_load_json_dict(row["settings_json"]),
        task_key_prefix=row["task_key_prefix"] if "task_key_prefix" in row.keys() else "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_sprint(row: sqlite3.Row) -> Sprint:
    return Sprint(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        goal=row["goal"],
        status=row["status"],
        order_index=row["order_index"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def _row_to_task(row: sqlite3.Row) -> Task:
    raw_evidence = (
        row["completion_evidence_json"]
        if "completion_evidence_json" in row.keys()
        else ""
    )
    evidence_dict = _load_json_dict(raw_evidence) if raw_evidence else None
    completion_evidence: CompletionEvidence | None = (
        CompletionEvidence.from_mapping(evidence_dict)
        if isinstance(evidence_dict, dict)
        else None
    )
    return Task(
        id=row["id"],
        sprint_id=row["sprint_id"],
        project_id=row["project_id"],
        title=row["title"],
        task_key=row["task_key"] if "task_key" in row.keys() else "",
        description=row["description"],
        status=row["status"],
        task_type=row["task_type"],
        priority=row["priority"],
        order_index=row["order_index"],
        branch_name=row["branch_name"],
        worktree_path=(
            row["worktree_path"] if "worktree_path" in row.keys() else None
        ),
        assigned_role=row["assigned_role"],
        acceptance_criteria=row["acceptance_criteria"],
        blocked_reason=row["blocked_reason"],
        created_by=row["created_by"],
        depends_on_task_ids=_load_json_list(row["depends_on_task_ids"]),
        workflow_current_step=row["workflow_current_step"],
        workflow_carried_output=row["workflow_carried_output"],
        step_visit_counts=_load_json_dict(row["step_visit_counts"]),
        executor_overrides=(
            _load_json_dict(row["executor_overrides_json"])
            if "executor_overrides_json" in row.keys()
            else {}
        ),
        complexity=row["complexity"] if "complexity" in row.keys() else None,
        completion_evidence=completion_evidence,
        source_system=row["source_system"] if "source_system" in row.keys() else None,
        source_ref=row["source_ref"] if "source_ref" in row.keys() else None,
        source_url=row["source_url"] if "source_url" in row.keys() else None,
        reporter=row["reporter"] if "reporter" in row.keys() else None,
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def _token_usage_from_row(row: sqlite3.Row) -> dict[str, int]:
    """Return the summed token split of an aggregate row."""

    return TokenUsage(
        input=int(row["input_tokens"]),
        output=int(row["output_tokens"]),
        cache_read=int(row["cache_read_tokens"]),
        cache_creation=int(row["cache_creation_tokens"]),
    ).as_dict()


def _row_to_run(row: sqlite3.Row) -> Run:
    return Run(
        id=row["id"],
        task_id=row["task_id"],
        project_id=row["project_id"],
        role_id=row["role_id"],
        workflow_step=row["workflow_step"],
        agent_backend=row["agent_backend"],
        status=row["status"],
        outcome=row["outcome"],
        outcome_detail=row["outcome_detail"],
        model=row["model"],
        session_id=row["session_id"],
        branch_name=row["branch_name"],
        prompt_text=row["prompt_text"],
        cost_usd=row["cost_usd"],
        token_count=row["token_count"],
        token_usage=TokenUsage(
            input=row["input_tokens"],
            output=row["output_tokens"],
            cache_read=row["cache_read_tokens"],
            cache_creation=row["cache_creation_tokens"],
        ),
        duration_ms=row["duration_ms"],
        retry_count=row["retry_count"],
        failure_type=row["failure_type"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
    )


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        run_id=row["run_id"],
        task_id=row["task_id"],
        project_id=row["project_id"],
        event_type=row["event_type"],
        timestamp=row["timestamp"],
        role_id=row["role_id"],
        payload=_load_json_dict(row["payload_json"]),
    )


def _row_to_gate(row: sqlite3.Row) -> DecisionGate:
    import json as _json

    raw = row["suggested_order"]
    try:
        suggested_order = _json.loads(raw) if raw else []
    except (ValueError, TypeError):
        suggested_order = []
    return DecisionGate(
        id=row["id"],
        project_id=row["project_id"],
        sprint_id=row["sprint_id"],
        raised_at=row["raised_at"],
        conflict_description=row["conflict_description"],
        suggested_order=suggested_order,
        suggested_reason=row["suggested_reason"] or "",
        status=row["status"],  # type: ignore[assignment]
        resolved_at=row["resolved_at"],
        resolved_by=row["resolved_by"],
    )


def _row_to_lease(row: sqlite3.Row) -> Lease:
    return Lease(
        id=row["id"],
        project_id=row["project_id"],
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        holder_id=row["holder_id"],
        lease_token=row["lease_token"],
        fencing_token=row["fencing_token"],
        status=row["status"],  # type: ignore[assignment]
        acquired_at=row["acquired_at"],
        heartbeat_at=row["heartbeat_at"],
        expires_at=row["expires_at"],
        released_at=row["released_at"],
    )


def _row_to_engine_command(row: sqlite3.Row) -> EngineCommand:
    return EngineCommand(
        id=row["id"],
        project_id=row["project_id"],
        command=row["command"],  # type: ignore[arg-type]
        requested_by=row["requested_by"],
        task_id=row["task_id"],
        status=row["status"],  # type: ignore[arg-type]
        requested_at=row["requested_at"],
        acknowledged_at=row["acknowledged_at"],
        completed_at=row["completed_at"],
        result_detail=row["result_detail"],
    )


def _row_to_api_token(row: sqlite3.Row) -> ApiToken:
    return ApiToken(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        token_hash=row["token_hash"],
        scopes=_load_json_list(row["scopes_json"]),
        created_by=row["created_by"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        revoked_at=row["revoked_at"],
    )


def _row_to_notification_destination(row: sqlite3.Row) -> NotificationDestination:
    return NotificationDestination(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        target=row["target"],
        kind=row["kind"],
        config=_load_json_dict(row["config_json"]),
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_notification_delivery(row: sqlite3.Row) -> NotificationDelivery:
    return NotificationDelivery(
        id=row["id"],
        project_id=row["project_id"],
        destination_id=row["destination_id"],
        kind=row["kind"],
        payload=_load_json_dict(row["payload_json"]),
        task_id=row["task_id"],
        event_id=row["event_id"],
        status=row["status"],
        attempts=int(row["attempts"]),
        max_attempts=int(row["max_attempts"]),
        next_attempt_at=row["next_attempt_at"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        delivered_at=row["delivered_at"],
    )


def _row_to_human_gate_decision(row: sqlite3.Row) -> HumanGateDecision:
    return HumanGateDecision(
        id=row["id"],
        task_id=row["task_id"],
        project_id=row["project_id"],
        workflow_step=row["workflow_step"],
        decision=row["decision"],
        note=row["note"],
        decided_by=row["decided_by"] or "human",
        decided_at=row["decided_at"],
        run_id=row["run_id"],
    )


def _row_to_merge_waiver(row: sqlite3.Row) -> MergeWaiver:
    return MergeWaiver(
        id=row["id"],
        task_id=row["task_id"],
        project_id=row["project_id"],
        waiver_type=row["waiver_type"],
        reason=row["reason"],
        approved_by=row["approved_by"],
        approved_at=row["approved_at"],
        branch_name=row["branch_name"],
        head_sha=row["head_sha"],
        base_sha=row["base_sha"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
    )
