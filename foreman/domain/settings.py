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


# Settings that decide where Foreman writes on the host, or where it sends data
# and credentials. They are changed by an operator at a terminal (`foreman
# config <project> --set key=value`), never over the dashboard API (ADR-0017).
# The test command is not one of them since 2026-11-19 (the owner): whoever may
# use the dashboard already starts agents that run commands on this host.
HOST_LEVEL_SETTINGS: frozenset[str] = frozenset(
    {
        "worktree_setup_command",
        "worktree_root",
        "worktree_link_paths",
        "context_dir",
        "merge_push_remote",
        "agent_env_passthrough",
        "sandbox_allowed_hosts",
        "sandbox_read_paths",
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
    # When a sprint is finished, a note listing its tasks is committed to
    # ``docs/checkpoints/<tag>.md`` before the sprint is tagged (spec 6.4).
    write_checkpoint_notes: bool = False
    # When a sprint is finished, ``CHANGELOG.md`` gets a section built from the
    # ``changes/`` files, which are removed, in the checkpoint's commit
    # (ADR-0040). Off: the file and ``changes/`` are left as they are.
    generate_changelog: bool = False
    # Foreman writes ``docs/STATUS.md`` and ``docs/sprints/current.md`` from its
    # database when a sprint starts and when it finishes (in the checkpoint's
    # commit), the finished sprint's archive copy, and with the finish and
    # ``foreman copies`` ``docs/sprints/backlog.md`` from its backlog (ADR-0040).
    # Off: the files are left to whoever edits them.
    generate_copies: bool = False
    # The repository folder whose ADRs are numbered when a task merges and
    # whose index is generated (ADR-0040). Empty: none. A project without the
    # folder is left alone.
    adr_dir: str = "docs/adr"
    # The git remote the default branch is pushed to after each merge.
    # Empty: merges stay on this machine. Host-level: it makes the engine
    # write to another machine with this host's git credentials.
    merge_push_remote: str = ""
    # Names of host environment variables passed to every agent process on
    # top of the short list all agents get (ADR-0023). Host-level: it hands
    # this machine's secrets to an agent.
    agent_env_passthrough: tuple[str, ...] = ()
    # Hosts a sandboxed step (the code reviewer) may reach over the network,
    # as names or ``*.example.com`` patterns. Empty: none; localhost always
    # works. Host-level: it opens the sandbox to the network (ADR new-claude-code-sandbox).
    sandbox_allowed_hosts: tuple[str, ...] = ()
    # Absolute paths (``~`` allowed) a sandboxed step may read although they
    # lie under the operator's home directory or beside the repository,
    # which are closed to it: a toolchain, a package cache. Host-level.
    sandbox_read_paths: tuple[str, ...] = ()
    # The policy matrix (see foreman/policy.py). Each decision names a
    # project default; "auto" lets the engine decide on its own and records
    # the decision, "human" routes it to a person. `policy_rules` refines the
    # defaults per task type, and a task override beats both.
    merge_approval: str = "auto"
    plan_approval: str = "human"
    triage: str = "human"
    notification: str = "attention"
    policy_rules: dict[str, dict[str, str]] = field(default_factory=dict)
    # Who finishes a sprint once every task of it is done or cancelled
    # (ADR-0025): "human" leaves it active for a person to finish; "auto" lets
    # the engine finish it and start the next one. A sprint is not a task, so
    # this is the project's alone: no task override or rule applies.
    sprint_completion: str = "human"
    # Per-run cost ceiling that can lower a role's; 0 means the role's applies.
    runner_max_cost_usd: float = 0.0
    runner_permission_mode: str = "auto"
    default_model: str = ""
    # Manager (meta-agent) model — see review Phase 2.
    meta_agent_model: str = ""
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
            write_checkpoint_notes=_validate_bool(raw.get("write_checkpoint_notes"), key="write_checkpoint_notes"),
            generate_changelog=_validate_bool(raw.get("generate_changelog"), key="generate_changelog"),
            generate_copies=_validate_bool(raw.get("generate_copies"), key="generate_copies"),
            adr_dir=_validate_adr_dir(raw.get("adr_dir")),
            merge_push_remote=_validate_remote_name(raw.get("merge_push_remote")),
            agent_env_passthrough=_validate_env_names(raw.get("agent_env_passthrough")),
            sandbox_allowed_hosts=_validate_hosts(raw.get("sandbox_allowed_hosts")),
            sandbox_read_paths=_validate_read_paths(raw.get("sandbox_read_paths")),
            merge_approval=_validate_policy_default(raw, "merge_approval"),
            plan_approval=_validate_policy_default(raw, "plan_approval"),
            triage=_validate_policy_default(raw, "triage"),
            notification=_validate_policy_default(raw, "notification"),
            sprint_completion=_validate_sprint_completion(raw.get("sprint_completion")),
            policy_rules=_validate_policy_rules(raw.get("policy_rules")),
            runner_max_cost_usd=_validate_non_negative_float(
                raw.get("runner_max_cost_usd"), default=0.0
            ),
            runner_permission_mode=str(raw.get("runner_permission_mode", "auto") or "auto"),
            default_model=str(raw.get("default_model") or ""),
            meta_agent_model=str(raw.get("meta_agent_model") or ""),
            review_diff_max_chars=_validate_positive_int(
                raw.get("review_diff_max_chars"), default=16000
            ),
        )


def _string_list(value: Any, *, key: str) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, (list, tuple)):
        raise SettingsError(f"{key} must be a list of strings, got {value!r}.")
    entries: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            raise SettingsError(f"{key} entries must be strings, got {entry!r}.")
        text = entry.strip()
        if text and text not in entries:
            entries.append(text)
    return entries


def _validate_hosts(value: Any) -> tuple[str, ...]:
    """Validate the hosts a sandboxed step may reach: names, ``*.`` patterns."""

    hosts = _string_list(value, key="sandbox_allowed_hosts")
    for host in hosts:
        bare = host.removeprefix("*.")
        if not bare or not all(ch.isalnum() or ch in ".-" for ch in bare) or bare.startswith((".", "-")):
            raise SettingsError(
                f"sandbox_allowed_hosts: {host!r} is not a host name "
                "(a name such as pypi.org, or a pattern such as *.example.com)."
            )
    return tuple(hosts)


def _validate_read_paths(value: Any) -> tuple[str, ...]:
    """Validate the absolute paths a sandboxed step may read."""

    paths = _string_list(value, key="sandbox_read_paths")
    for entry in paths:
        if not (entry.startswith("/") or entry == "~" or entry.startswith("~/")):
            raise SettingsError(
                f"sandbox_read_paths: {entry!r} must be an absolute path (or start with ~/)."
            )
        if ".." in Path(entry).parts:
            raise SettingsError(f"sandbox_read_paths: {entry!r} must not contain '..'.")
    return tuple(paths)


def _validate_env_names(value: Any) -> tuple[str, ...]:
    """Validate a list of environment variable names."""

    if value is None or value == "":
        return ()
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, (list, tuple)):
        raise SettingsError(
            f"agent_env_passthrough must be a list of variable names, got {value!r}."
        )
    names: list[str] = []
    for entry in value:
        name = str(entry).strip()
        if not name:
            continue
        if not (name[0].isalpha() or name[0] == "_") or not all(
            ch.isalnum() or ch == "_" for ch in name
        ):
            raise SettingsError(
                f"agent_env_passthrough: {entry!r} is not an environment variable name."
            )
        if name not in names:
            names.append(name)
    return tuple(names)


def _validate_bool(value: Any, *, key: str, default: bool = False) -> bool:
    """A yes-or-no setting: true or false, or absent for the default."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise SettingsError(f"{key} must be true or false.")


def _validate_adr_dir(value: Any) -> str:
    """A folder inside the repository. Absent: ``docs/adr``; empty: none."""

    if value is None:
        return "docs/adr"
    if not isinstance(value, str):
        raise SettingsError("adr_dir must be a folder in the repository, or empty for none.")
    folder = value.strip().strip("/")
    parts = folder.split("/") if folder else []
    if value.strip().startswith("/") or ".." in parts or "." in parts:
        raise SettingsError("adr_dir must be a folder inside the repository, such as docs/adr.")
    return folder


def _validate_remote_name(value: Any) -> str:
    """Validate the name of a git remote. Empty means none."""

    name = str(value or "").strip()
    if not name:
        return ""
    # A name, never a URL or an option: the engine passes it to ``git push``.
    if name.startswith("-") or not all(ch.isalnum() or ch in "._-" for ch in name):
        raise SettingsError(
            f"merge_push_remote must be the name of a git remote (letters, digits, "
            f"'.', '_' or '-'), got {value!r}."
        )
    return name


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


#: Who may finish a sprint: a person, or the engine.
SPRINT_COMPLETION_VALUES: tuple[str, ...] = ("auto", "human")


def _validate_sprint_completion(value: Any) -> str:
    if value is None or value == "":
        return "human"
    if value not in SPRINT_COMPLETION_VALUES:
        raise SettingsError(
            f"sprint_completion must be one of {', '.join(SPRINT_COMPLETION_VALUES)}, got {value!r}"
        )
    return str(value)


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
