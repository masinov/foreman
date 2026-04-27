"""Canonical outcome constants and normalizers for Foreman."""

from __future__ import annotations

# Task-level terminal statuses
DONE = "done"
CANCELLED = "cancelled"
BLOCKED = "blocked"

# Run-level outcomes
SUCCESS = "success"
FAILURE = "failure"
ERROR = "error"
KILLED = "killed"
PAUSED = "paused"

# Reviewer decisions
APPROVE = "approve"
DENY = "deny"
STEER = "steer"

# All canonical outcome values in one frozenset for validation
CANONICAL_OUTCOMES = frozenset({
    DONE,
    CANCELLED,
    BLOCKED,
    SUCCESS,
    FAILURE,
    ERROR,
    KILLED,
    PAUSED,
    APPROVE,
    DENY,
    STEER,
})


def normalize_agent_outcome(raw: str) -> str:
    """Map agent event outcomes to canonical constants.

    Agents may emit variant strings (e.g. "completed", "done", "success").
    Normalize them to the canonical set so workflow transitions are deterministic.
    """
    normalized = raw.strip().lower()

    # Map common variants
    if normalized in ("completed", "done"):
        return DONE
    if normalized in ("error", "failed"):
        return ERROR
    if normalized in ("failure",):
        return FAILURE
    if normalized in ("killed", "terminated", "timeout"):
        return KILLED
    if normalized == "paused":
        return PAUSED
    if normalized in ("success", "succeeded"):
        return SUCCESS

    # Unknown but structural — pass through as-is for now; caller should handle
    return normalized


def normalize_reviewer_decision(raw: str) -> str:
    """Normalize reviewer decision strings to canonical constants.

    Reviewer output may contain typos or extra whitespace. Normalize to
    canonical approve/deny/steer constants.
    """
    normalized = raw.strip().lower()

    if normalized in ("approve", "approved", "yes", "lgtm", "pass"):
        return APPROVE
    if normalized in ("deny", "denied", "no", "reject", "rejected", "needs_work"):
        return DENY
    if normalized in ("steer", "steering", "redirect", "revise"):
        return STEER

    return raw.strip()
