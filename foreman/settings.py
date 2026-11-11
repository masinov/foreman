"""Explicit project settings validation for Foreman."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import TASK_TYPES, Project
from .policy import (
    POLICY_DECISIONS,
    POLICY_DEFAULTS,
    POLICY_VALUES,
    is_valid_value,
)


# Settings that decide what runs on the host, where Foreman writes, or where it
# sends data and credentials. They are changed by an operator at a terminal
# (`foreman config <project> --set key=value`), never over the dashboard API:
# an API caller who could set them could run commands as the engine's user.
HOST_LEVEL_SETTINGS: frozenset[str] = frozenset(
    {
        "test_command",
        "worktree_setup_command",
        "worktree_root",
        "worktree_link_paths",
        "context_dir",
        "judge_base_url",
        "judge_api_key_env",
    }
)


def changed_host_level_settings(
    current: dict[str, Any], updates: dict[str, Any]
) -> tuple[str, ...]:
    """Return the host-level keys ``updates`` would change, sorted.

    A client that sends back the settings it read is not changing anything, so
    a key counts only when its value differs. An absent key and an empty value
    are the same setting.
    """

    def normalized(value: Any) -> Any:
        if value is None or value == "" or value == [] or value == ():
            return None
        return list(value) if isinstance(value, tuple) else value

    return tuple(
        sorted(
            key
            for key in HOST_LEVEL_SETTINGS
            if key in updates and normalized(updates[key]) != normalized(current.get(key))
        )
    )


class SettingsError(ValueError):
    """Raised when project settings fail validation."""


def settings_of(project: Project) -> ProjectSettings:
    """Return a project's settings, validated and typed.

    This is the one way engine code reads a setting. The raw ``settings``
    dict on a project is what is stored; reading it directly means repeating
    the default and the type handling at every call site, and they drift.
    Raises ``SettingsError`` when a stored value is invalid.
    """

    return ProjectSettings.from_raw(project.settings or {})


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
    # The policy matrix (see foreman/policy.py). Each decision names a
    # project default; "auto" lets the engine decide on its own and records
    # the decision, "human" routes it to a person. `policy_rules` refines the
    # defaults per task type, and a task override beats both.
    merge_approval: str = "auto"
    plan_approval: str = "human"
    triage: str = "human"
    notification: str = "attention"
    policy_rules: dict[str, dict[str, str]] = field(default_factory=dict)
    # Per-run cost ceiling that can lower a role's; 0 means the role's applies.
    runner_max_cost_usd: float = 0.0
    runner_permission_mode: str = "auto"
    default_model: str = ""
    # Manager (meta-agent) model — see review Phase 2.
    meta_agent_model: str = ""
    # Criteria judge — opt-in; with base_url/model unset no criterion is judged.
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
            merge_approval=_validate_policy_default(raw, "merge_approval"),
            plan_approval=_validate_policy_default(raw, "plan_approval"),
            triage=_validate_policy_default(raw, "triage"),
            notification=_validate_policy_default(raw, "notification"),
            policy_rules=_validate_policy_rules(raw.get("policy_rules")),
            runner_max_cost_usd=_validate_non_negative_float(
                raw.get("runner_max_cost_usd"), default=0.0
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


def _validate_policy_default(raw: dict[str, Any], decision: str) -> str:
    """Validate one project-level policy default from the raw settings."""

    value = raw.get(decision)
    if value is None:
        return POLICY_DEFAULTS[decision]
    if not is_valid_value(decision, value):
        raise SettingsError(
            f"Policy {decision!r} must be one of "
            f"{', '.join(POLICY_VALUES[decision])}, got {value!r}"
        )
    return str(value)


def _validate_policy_rules(value: Any) -> dict[str, dict[str, str]]:
    """Validate the per-task-type policy rules object.

    Shape: ``{"<task_type>": {"<decision>": "<value>"}}``. Task types, decision
    names, and values are all checked, so a typo is refused at the point of
    writing rather than silently ignored on the next run.
    """

    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SettingsError(
            f"policy_rules must be an object keyed by task type, got "
            f"{type(value).__name__!r}"
        )
    rules: dict[str, dict[str, str]] = {}
    for task_type, rule in value.items():
        if not isinstance(task_type, str) or task_type not in TASK_TYPES:
            raise SettingsError(
                f"policy_rules key {task_type!r} is not a task type; expected one of "
                f"{', '.join(TASK_TYPES)}"
            )
        if not isinstance(rule, dict):
            raise SettingsError(
                f"policy_rules[{task_type!r}] must be an object mapping a policy "
                f"decision to a value, got {type(rule).__name__!r}"
            )
        cleaned: dict[str, str] = {}
        for decision, decision_value in rule.items():
            if not isinstance(decision, str) or decision not in POLICY_VALUES:
                raise SettingsError(
                    f"policy_rules[{task_type!r}] has unknown policy decision "
                    f"{decision!r}; expected one of {', '.join(POLICY_DECISIONS)}"
                )
            if not is_valid_value(decision, decision_value):
                raise SettingsError(
                    f"policy_rules[{task_type!r}][{decision!r}] must be one of "
                    f"{', '.join(POLICY_VALUES[decision])}, got {decision_value!r}"
                )
            cleaned[decision] = str(decision_value)
        rules[task_type] = cleaned
    return rules


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
