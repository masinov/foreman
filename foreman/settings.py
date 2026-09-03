"""Explicit project settings validation for Foreman."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class SettingsError(ValueError):
    """Raised when project settings fail validation."""


@dataclass
class ProjectSettings:
    """Validated project settings.

    All fields are optional and have safe defaults. If raw settings contain
    invalid values, validation raises SettingsError.
    """

    task_selection_mode: str = "directed"
    max_autonomous_tasks: int = 5
    max_step_visits: int = 5
    test_command: str = ""
    # Wall-clock cap for _builtin:run_tests; 0 disables the timeout.
    test_timeout_seconds: int = 1800
    time_limit_per_run_minutes: int = 0
    cost_limit_per_task_usd: float = 0.0
    cost_limit_per_sprint_usd: float = 0.0
    time_limit_per_task_ms: int = 0
    # Retention is opt-in: ``None`` disables that pruning type.  Audit-grade
    # events (decisions, evidence) are not yet separated from telemetry, so
    # the engine must never prune by default.
    event_retention_days: int | None = None
    run_retention_days: int | None = None
    prompt_retention_days: int | None = None
    # Engine resilience knobs read by the orchestrator.
    max_infra_retries: int = 3
    active_run_recovery_timeout_minutes: int = 0
    context_dir: str = ""
    completion_guard_enabled: bool = True
    # Gate policies: "auto" lets the engine approve the gate on its own and
    # records a policy decision; "human" pauses the task for a person.
    merge_approval: str = "auto"
    plan_approval: str = "human"
    runner_max_cost_usd: float = 1000.0
    runner_permission_mode: str = "auto"
    default_model: str = ""
    # Manager (meta-agent) model — see review Phase 2.
    meta_agent_model: str = ""
    # Criteria judge — opt-in; unset base_url/model falls back to the heuristic.
    judge_base_url: str = ""
    judge_model: str = ""
    judge_api_key_env: str = ""
    judge_max_diff_chars: int = 24000
    # Reviewer prompt diff payload cap — see review Phase 5.
    review_diff_max_chars: int = 16000

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> ProjectSettings:
        """Parse and validate raw settings dict into a ProjectSettings instance."""
        return cls(
            task_selection_mode=_validate_task_selection_mode(raw.get("task_selection_mode")),
            max_autonomous_tasks=_validate_positive_int(raw.get("max_autonomous_tasks"), default=5),
            max_step_visits=_validate_positive_int(raw.get("max_step_visits"), default=5),
            test_command=str(raw.get("test_command", "") or ""),
            test_timeout_seconds=_validate_non_negative_int(
                raw.get("test_timeout_seconds"), default=1800
            ),
            time_limit_per_run_minutes=_validate_non_negative_int(
                raw.get("time_limit_per_run_minutes"), default=0
            ),
            cost_limit_per_task_usd=_validate_non_negative_float(
                raw.get("cost_limit_per_task_usd"), default=0.0
            ),
            cost_limit_per_sprint_usd=_validate_non_negative_float(
                raw.get("cost_limit_per_sprint_usd"), default=0.0
            ),
            time_limit_per_task_ms=_validate_non_negative_int(
                raw.get("time_limit_per_task_ms"), default=0
            ),
            event_retention_days=_validate_optional_positive_int(raw.get("event_retention_days")),
            run_retention_days=_validate_optional_positive_int(raw.get("run_retention_days")),
            prompt_retention_days=_validate_optional_positive_int(
                raw.get("prompt_retention_days")
            ),
            max_infra_retries=_validate_non_negative_int(raw.get("max_infra_retries"), default=3),
            active_run_recovery_timeout_minutes=_validate_non_negative_int(
                raw.get("active_run_recovery_timeout_minutes"), default=0
            ),
            context_dir=str(raw.get("context_dir") or ""),
            completion_guard_enabled=bool(raw.get("completion_guard_enabled", True)),
            merge_approval=_validate_gate_policy(raw.get("merge_approval"), default="auto"),
            plan_approval=_validate_gate_policy(raw.get("plan_approval"), default="human"),
            runner_max_cost_usd=_validate_non_negative_float(
                raw.get("runner_max_cost_usd"), default=1000.0
            ),
            runner_permission_mode=str(raw.get("runner_permission_mode", "auto") or "auto"),
            default_model=str(raw.get("default_model") or ""),
            meta_agent_model=str(raw.get("meta_agent_model") or ""),
            judge_base_url=str(raw.get("judge_base_url") or ""),
            judge_model=str(raw.get("judge_model") or ""),
            judge_api_key_env=str(raw.get("judge_api_key_env") or ""),
            judge_max_diff_chars=_validate_positive_int(
                raw.get("judge_max_diff_chars"), default=24000
            ),
            review_diff_max_chars=_validate_positive_int(
                raw.get("review_diff_max_chars"), default=16000
            ),
        )


GATE_POLICY_VALUES: tuple[str, ...] = ("auto", "human")


def _validate_gate_policy(value: Any, *, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or value not in GATE_POLICY_VALUES:
        raise SettingsError(
            f"Gate policy must be one of {', '.join(GATE_POLICY_VALUES)}, got {value!r}"
        )
    return value


def _validate_task_selection_mode(value: Any) -> str:
    if value is None:
        return "directed"
    if not isinstance(value, str):
        raise SettingsError(f"task_selection_mode must be a string, got {type(value).__name__!r}")
    if value not in {"directed", "autonomous"}:
        raise SettingsError(
            f"task_selection_mode must be 'directed' or 'autonomous', got {value!r}"
        )
    return value


def _validate_positive_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, (int, float)):
        raise SettingsError(f"Expected integer for setting, got {type(value).__name__!r}")
    if isinstance(value, float) and not value.is_integer():
        raise SettingsError(f"Expected integer for setting, got {value!r}")
    int_val = int(value)
    if int_val <= 0:
        raise SettingsError(f"Expected positive integer for setting, got {int_val!r}")
    return int_val


def _validate_optional_positive_int(value: Any) -> int | None:
    """Return None when unset, otherwise a validated positive integer."""

    if value is None:
        return None
    return _validate_positive_int(value, default=1)


def _validate_non_negative_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, (int, float)):
        raise SettingsError(f"Expected integer for setting, got {type(value).__name__!r}")
    if isinstance(value, float) and not value.is_integer():
        raise SettingsError(f"Expected integer for setting, got {value!r}")
    int_val = int(value)
    if int_val < 0:
        raise SettingsError(f"Expected non-negative integer for setting, got {int_val!r}")
    return int_val


def _validate_non_negative_float(value: Any, *, default: float) -> float:
    if value is None:
        return default
    if not isinstance(value, (int, float)):
        raise SettingsError(f"Expected numeric for setting, got {type(value).__name__!r}")
    float_val = float(value)
    if float_val < 0:
        raise SettingsError(f"Expected non-negative numeric for setting, got {float_val!r}")
    return float_val
