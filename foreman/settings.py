"""Explicit project settings validation for Foreman."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .notifications import NOTIFICATION_POLICIES


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
    # Where the per-task git worktrees live. Empty means the default,
    # ``<repo>/.foreman/worktrees``; an absolute path puts them elsewhere.
    worktree_root: str = ""
    # Repository-relative paths symlinked from the operator's checkout into
    # every new worktree. A worktree is a clean checkout, so ignored local
    # tooling a test command needs (``venv``, ``node_modules``) is not there
    # unless it is named here. Prefer ``worktree_setup_command``: a link
    # shares the operator's environment rather than isolating from it.
    worktree_link_paths: tuple[str, ...] = ()
    # Ceiling on how many task worktrees may exist at once. The engine
    # reclaims clean, idle trees oldest-first to stay under it; 0 disables
    # the cap. See ADR-0012.
    max_live_worktrees: int = 4
    # Shell command run once inside each newly created worktree, before any
    # step runs there, to build that tree's own environment.
    worktree_setup_command: str = ""
    # Wall-clock cap for ``worktree_setup_command``; 0 disables the timeout.
    worktree_setup_timeout_seconds: int = 1800
    completion_guard_enabled: bool = True
    # Gate policies: "auto" lets the engine approve the gate on its own and
    # records a policy decision; "human" pauses the task for a person.
    merge_approval: str = "auto"
    plan_approval: str = "human"
    # Notification policy: "none" says nothing, "attention" delivers the
    # moments that want a person (engine attention turns, human gates), and
    # "all" adds task completions. Read by ``foreman.notifications``; where
    # the message goes is a destination row, not a setting.
    notification: str = "attention"
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
            worktree_root=str(raw.get("worktree_root") or ""),
            worktree_link_paths=_validate_worktree_link_paths(
                raw.get("worktree_link_paths")
            ),
            max_live_worktrees=_validate_non_negative_int(
                raw.get("max_live_worktrees"), default=4
            ),
            worktree_setup_command=str(raw.get("worktree_setup_command") or ""),
            worktree_setup_timeout_seconds=_validate_non_negative_int(
                raw.get("worktree_setup_timeout_seconds"), default=1800
            ),
            completion_guard_enabled=bool(raw.get("completion_guard_enabled", True)),
            merge_approval=_validate_gate_policy(raw.get("merge_approval"), default="auto"),
            plan_approval=_validate_gate_policy(raw.get("plan_approval"), default="human"),
            notification=_validate_notification_policy(
                raw.get("notification"), default="attention"
            ),
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


def _validate_worktree_link_paths(value: Any) -> tuple[str, ...]:
    """Validate the repo-relative paths linked into every task worktree."""

    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise SettingsError(
            f"worktree_link_paths must be a list of relative paths, got "
            f"{type(value).__name__!r}"
        )
    names: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            raise SettingsError(
                f"worktree_link_paths entries must be strings, got {entry!r}"
            )
        name = entry.strip()
        if not name:
            continue
        candidate = Path(name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise SettingsError(
                f"worktree_link_paths entry {name!r} must be a relative path inside "
                "the repository."
            )
        names.append(name)
    return tuple(names)


GATE_POLICY_VALUES: tuple[str, ...] = ("auto", "human")


def _validate_gate_policy(value: Any, *, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or value not in GATE_POLICY_VALUES:
        raise SettingsError(
            f"Gate policy must be one of {', '.join(GATE_POLICY_VALUES)}, got {value!r}"
        )
    return value


#: Re-exported so a caller validating settings and a caller delivering
#: notifications cannot disagree about the vocabulary.
NOTIFICATION_POLICY_VALUES: tuple[str, ...] = NOTIFICATION_POLICIES


def _validate_notification_policy(value: Any, *, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or value not in NOTIFICATION_POLICY_VALUES:
        raise SettingsError(
            f"notification must be one of {', '.join(NOTIFICATION_POLICY_VALUES)}, "
            f"got {value!r}"
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
