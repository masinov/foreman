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
    time_limit_per_run_minutes: int = 0
    cost_limit_per_task_usd: float = 0.0
    cost_limit_per_sprint_usd: float = 0.0
    time_limit_per_task_ms: int = 0
    event_retention_days: int = 90
    context_dir: str = ""
    completion_guard_enabled: bool = True
    runner_max_cost_usd: float = 1000.0
    runner_permission_mode: str = "auto"
    default_model: str = ""

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> ProjectSettings:
        """Parse and validate raw settings dict into a ProjectSettings instance."""
        return cls(
            task_selection_mode=_validate_task_selection_mode(raw.get("task_selection_mode")),
            max_autonomous_tasks=_validate_positive_int(raw.get("max_autonomous_tasks"), default=5),
            max_step_visits=_validate_positive_int(raw.get("max_step_visits"), default=5),
            test_command=str(raw.get("test_command", "") or ""),
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
            event_retention_days=_validate_positive_int(raw.get("event_retention_days"), default=90),
            context_dir=str(raw.get("context_dir") or ""),
            completion_guard_enabled=bool(raw.get("completion_guard_enabled", True)),
            runner_max_cost_usd=_validate_non_negative_float(
                raw.get("runner_max_cost_usd"), default=1000.0
            ),
            runner_permission_mode=str(raw.get("runner_permission_mode", "auto") or "auto"),
            default_model=str(raw.get("default_model") or ""),
        )


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
