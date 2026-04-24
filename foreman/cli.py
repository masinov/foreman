"""Command-line interface for the Foreman package."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Callable, Sequence

from . import __version__
from .migrations import MIGRATIONS
from .dashboard_runtime import (
    DEFAULT_FRONTEND_DEV_URL,
    STREAM_POLL_INTERVAL_SECONDS,
    run_dashboard_server,
)
from .models import Event, Project, Sprint, TASK_TYPES, Task, utc_now_text
from .orchestrator import ForemanOrchestrator, OrchestratorError
from .roles import RoleLoadError, default_roles_dir, load_roles
from .scaffold import (
    DEFAULT_DB_FILENAME,
    DEFAULT_DEFAULT_BRANCH,
    DEFAULT_TEST_COMMAND,
    DEFAULT_WORKFLOW_ID,
    ScaffoldError,
    default_project_settings,
    generate_project_id,
    resolve_spec_path,
    scaffold_repository,
)
from .store import ForemanStore
from .workflows import WorkflowLoadError, default_workflows_dir, load_workflows

CLI_DESCRIPTION = (
    "Foreman is an autonomous development engine for spec-driven software delivery."
)
DB_OPTION_NOTE = (
    f"Defaults to repo-local `{DEFAULT_DB_FILENAME}` discovery; pass `--db PATH` to override."
)
BOARD_STATUS_SECTIONS: tuple[tuple[str, str], ...] = (
    ("todo", "Todo"),
    ("in_progress", "In Progress"),
    ("blocked", "Blocked"),
    ("done", "Done"),
    ("cancelled", "Cancelled"),
)

Handler = Callable[[argparse.Namespace], int]
WATCH_STREAM_BATCH_LIMIT = 100


@dataclass(frozen=True)
class WatchStreamPlan:
    """Resolved watch scope plus the functions needed to tail it."""

    header_lines: tuple[str, ...]
    recent_events: tuple[Event, ...]
    fetch_events: Callable[[str | None, int], list[Event]]


class CliResolutionError(ValueError):
    """Raised when CLI runtime inputs cannot be resolved safely."""


def _print_lines(*lines: str) -> None:
    for line in lines:
        print(line)


def _print_stream_lines(*lines: str) -> None:
    for line in lines:
        print(line, flush=True)


def _add_db_option(
    parser: argparse.ArgumentParser,
    *,
    required: bool = False,
    help_text: str = f"Path to the SQLite store. {DB_OPTION_NOTE}",
) -> None:
    parser.add_argument(
        "--db",
        required=required,
        help=help_text,
    )


def _iter_parent_paths(start_path: Path) -> tuple[Path, ...]:
    resolved = start_path.expanduser().resolve()
    return (resolved, *resolved.parents)


def _discover_repo_local_db_path(start_path: Path | None = None) -> Path | None:
    base = start_path or Path.cwd()
    for candidate in _iter_parent_paths(base):
        db_path = candidate / DEFAULT_DB_FILENAME
        if db_path.is_file():
            return db_path
    return None


def _looks_like_repo_root(path: Path) -> bool:
    return (
        (path / "AGENTS.md").is_file()
        or (path / ".git").exists()
        or (path / ".foreman").exists()
    )


def _discover_repo_root(start_path: Path | None = None) -> Path | None:
    base = start_path or Path.cwd()
    for candidate in _iter_parent_paths(base):
        if _looks_like_repo_root(candidate):
            return candidate
    return None


def _resolve_db_path(
    explicit_db: str | None,
    *,
    repo_path: str | Path | None = None,
) -> Path:
    if explicit_db:
        return Path(explicit_db).expanduser().resolve()

    if repo_path is not None:
        return Path(repo_path).expanduser().resolve() / DEFAULT_DB_FILENAME

    discovered_db = _discover_repo_local_db_path()
    if discovered_db is not None:
        return discovered_db

    repo_root = _discover_repo_root()
    if repo_root is not None:
        raise CliResolutionError(
            f"No repo-local Foreman database found at {repo_root / DEFAULT_DB_FILENAME}. "
            "Run `foreman init <repo_path> --name <name> --spec <path>` or pass `--db PATH`."
        )

    raise CliResolutionError(
        "Could not discover a Foreman repository from the current directory. "
        "Run the command from a Foreman repo or pass `--db PATH`."
    )


def _resolve_db_path_or_print(
    explicit_db: str | None,
    *,
    repo_path: str | Path | None = None,
) -> str | None:
    try:
        return str(_resolve_db_path(explicit_db, repo_path=repo_path))
    except CliResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return None


def _format_task_counts(counts: dict[str, int]) -> str:
    return (
        "Tasks: "
        f"todo={counts['todo']} "
        f"in_progress={counts['in_progress']} "
        f"blocked={counts['blocked']} "
        f"done={counts['done']} "
        f"cancelled={counts['cancelled']}"
    )


def _format_run_totals(totals: dict[str, int | float]) -> str:
    return (
        f"Activity: runs={totals['run_count']} | "
        f"tokens={totals['total_token_count']} | "
        f"cost_usd={_format_usd(float(totals['total_cost_usd']))} | "
        f"duration_ms={totals['total_duration_ms']}"
    )


def _format_usd(value: float) -> str:
    return f"${value:.2f}"


def _format_idle_timeout(value: float | None) -> str:
    if value is None:
        return "until interrupted"
    return f"{value:.1f}s of inactivity"


def _format_step_visits(step_visit_counts: dict[str, int]) -> str:
    if not step_visit_counts:
        return "none"
    return ", ".join(f"{step}={count}" for step, count in step_visit_counts.items())


def _truncate_text(text: str, *, limit: int = 96) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _format_event_details(event_type: str, payload: dict[str, object]) -> str:
    if event_type == "agent.command":
        command = str(payload.get("command", "")).strip()
        return _truncate_text(command or "(no command recorded)")

    if event_type == "agent.file_change":
        path = str(payload.get("path", "")).strip()
        return path or "(no path recorded)"

    if event_type == "agent.message":
        text = str(payload.get("text", "")).strip()
        return _truncate_text(text or "(no message text)")

    if event_type == "workflow.resumed":
        parts = []
        decision = str(payload.get("decision", "")).strip()
        next_step = str(payload.get("next_step", "")).strip()
        if decision:
            parts.append(f"decision={decision}")
        if next_step:
            parts.append(f"next={next_step}")
        if payload.get("deferred"):
            parts.append("deferred=yes")
        note = str(payload.get("note", "")).strip()
        if note:
            parts.append(f"note={_truncate_text(note)}")
        return " | ".join(parts) if parts else "(no workflow details)"

    detail_keys = (
        "summary",
        "note",
        "message",
        "step",
        "trigger",
        "path",
        "command",
        "session_id",
        "error",
        "decision",
        "next_step",
    )
    parts = []
    for key in detail_keys:
        value = payload.get(key)
        if value in (None, "", []):
            continue
        parts.append(f"{key}={_truncate_text(str(value))}")
    return " | ".join(parts) if parts else "(no payload details)"


def _render_event_line(event_type: str, timestamp: str, role_id: str | None, payload: dict[str, object]) -> str:
    line = f"{timestamp} | {event_type}"
    if role_id:
        line = f"{line} | role={role_id}"
    return f"{line} | {_format_event_details(event_type, payload)}"


def _render_board_task_line(task_id: str, title: str, task_type: str, details: list[str]) -> str:
    parts = [task_id, task_type, title]
    parts.extend(detail for detail in details if detail)
    return f"- {' | '.join(parts)}"


def _format_watch_activity_totals(totals: dict[str, int | float]) -> str:
    return _format_run_totals(totals)


def _format_setting_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def _parse_config_value(raw_value: str) -> Any:
    normalized = raw_value.strip()
    lowered = normalized.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    try:
        return int(normalized)
    except ValueError:
        pass
    try:
        return float(normalized)
    except ValueError:
        pass
    if normalized.startswith(("{", "[", '"')):
        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            pass
    return raw_value


def _parse_config_assignment(raw_assignment: str) -> tuple[str, Any]:
    if "=" not in raw_assignment:
        raise CliResolutionError("Configuration assignment must use key=value syntax.")

    key, raw_value = raw_assignment.split("=", 1)
    key = key.strip()
    if not key:
        raise CliResolutionError("Configuration key cannot be empty.")
    return key, _parse_config_value(raw_value)


def _allocate_entity_id(
    prefix: str,
    title: str,
    *,
    exists: Callable[[str], object | None],
) -> str:
    base_slug = generate_project_id(title, title)
    candidate = base_slug if base_slug.startswith(f"{prefix}-") else f"{prefix}-{base_slug}"
    suffix = 2
    while exists(candidate) is not None:
        suffixed = f"{base_slug}-{suffix}"
        candidate = suffixed if suffixed.startswith(f"{prefix}-") else f"{prefix}-{suffixed}"
        suffix += 1
    return candidate


def _next_order_index(values: Sequence[int]) -> int:
    return max(values, default=-1) + 1


def _resolve_project_or_print(store: ForemanStore, project_id: str) -> Project | None:
    project = store.get_project(project_id)
    if project is None:
        print(f"Unknown project: {project_id}", file=sys.stderr)
        return None
    return project


def _resolve_sprint_or_print(store: ForemanStore, sprint_id: str) -> Sprint | None:
    sprint = store.get_sprint(sprint_id)
    if sprint is None:
        print(f"Unknown sprint: {sprint_id}", file=sys.stderr)
        return None
    return sprint


def _resolve_task_or_print(store: ForemanStore, task_id: str) -> Task | None:
    task = store.get_task(task_id)
    if task is None:
        print(f"Unknown task: {task_id}", file=sys.stderr)
        return None
    return task


def _select_task_creation_sprint(store: ForemanStore, project_id: str) -> Sprint | None:
    active_sprint = store.get_active_sprint(project_id)
    if active_sprint is not None:
        return active_sprint
    planned_sprints = [
        sprint for sprint in store.list_sprints(project_id) if sprint.status == "planned"
    ]
    return planned_sprints[0] if planned_sprints else None


def _build_run_watch_plan(store: ForemanStore, run_id: str, *, limit: int) -> WatchStreamPlan | None:
    run = store.get_run(run_id)
    if run is None:
        return None

    task = store.get_task(run.task_id)
    project = store.get_project(run.project_id)
    header_lines = (
        f"Database: {store.db_path}",
        f"Scope: run {run.id}",
        f"Project: {run.project_id} | {project.name if project is not None else 'unknown'}",
        f"Task: {run.task_id} | {task.title if task is not None else 'unknown'}",
        f"Run: status={run.status} | step={run.workflow_step} | role={run.role_id}",
    )
    return WatchStreamPlan(
        header_lines=header_lines,
        recent_events=tuple(store.list_recent_events(run_id=run.id, limit=limit)),
        fetch_events=lambda after_event_id, batch_limit: store.list_events(
            run_id=run.id,
            after_event_id=after_event_id,
            limit=batch_limit,
        ),
    )


def _build_sprint_watch_plan(store: ForemanStore, sprint_id: str, *, limit: int) -> WatchStreamPlan | None:
    sprint = store.get_sprint(sprint_id)
    if sprint is None:
        return None

    project = store.get_project(sprint.project_id)
    counts = store.task_counts(sprint_id=sprint.id)
    totals = store.run_totals(project_id=sprint.project_id, sprint_id=sprint.id)
    header_lines = (
        f"Database: {store.db_path}",
        f"Scope: sprint {sprint.id}",
        f"Project: {sprint.project_id} | {project.name if project is not None else 'unknown'}",
        f"Sprint: {sprint.id} | {sprint.title}",
        _format_task_counts(counts),
        _format_watch_activity_totals(totals),
    )
    return WatchStreamPlan(
        header_lines=header_lines,
        recent_events=tuple(store.list_recent_sprint_events(sprint.id, limit=limit)),
        fetch_events=lambda after_event_id, batch_limit: store.list_sprint_events(
            sprint.id,
            after_event_id=after_event_id,
            limit=batch_limit,
        ),
    )


def _build_project_watch_plan(store: ForemanStore, project_id: str, *, limit: int) -> WatchStreamPlan | None:
    project = store.get_project(project_id)
    if project is None:
        return None

    active_sprint = store.get_active_sprint(project.id)
    header_lines = [
        f"Database: {store.db_path}",
        f"Scope: project {project.id}",
        f"Project: {project.id} | {project.name}",
    ]

    if active_sprint is not None:
        counts = store.task_counts(sprint_id=active_sprint.id)
        totals = store.run_totals(project_id=project.id, sprint_id=active_sprint.id)
        header_lines.extend(
            [
                f"Stream: active sprint {active_sprint.id} | {active_sprint.title}",
                _format_task_counts(counts),
                _format_watch_activity_totals(totals),
            ]
        )
        recent_events = tuple(store.list_recent_sprint_events(active_sprint.id, limit=limit))
        fetch_events = lambda after_event_id, batch_limit: store.list_sprint_events(
            active_sprint.id,
            after_event_id=after_event_id,
            limit=batch_limit,
        )
    else:
        counts = store.task_counts(project_id=project.id)
        totals = store.run_totals(project_id=project.id)
        header_lines.extend(
            [
                "Stream: project-wide persisted events",
                _format_task_counts(counts),
                _format_watch_activity_totals(totals),
            ]
        )
        recent_events = tuple(store.list_recent_events(project_id=project.id, limit=limit))
        fetch_events = lambda after_event_id, batch_limit: store.list_events(
            project_id=project.id,
            after_event_id=after_event_id,
            limit=batch_limit,
        )

    return WatchStreamPlan(
        header_lines=tuple(header_lines),
        recent_events=recent_events,
        fetch_events=fetch_events,
    )


def handle_board(args: argparse.Namespace) -> int:
    """Handle ``foreman board``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = store.get_project(args.project_id)
        if project is None:
            print(f"Unknown project: {args.project_id}", file=sys.stderr)
            return 1

        active_sprint = store.get_active_sprint(project.id)
        lines = [
            "Board",
            f"Database: {store.db_path}",
            f"Project: {project.id} | {project.name}",
        ]
        if active_sprint is None:
            lines.append("No active sprint for this project.")
            _print_lines(*lines)
            return 0

        tasks = store.list_tasks(sprint_id=active_sprint.id)
        counts = store.task_counts(sprint_id=active_sprint.id)
        totals = store.run_totals(project_id=project.id, sprint_id=active_sprint.id)
        task_totals = {
            str(row["task_id"]): row for row in store.task_run_totals(sprint_id=active_sprint.id)
        }
        task_count = sum(counts.values())

    lines.extend(
        [
            f"Sprint: {active_sprint.id} | {active_sprint.title}",
            f"Goal: {active_sprint.goal or 'n/a'}",
            (
                f"Progress: done={counts['done']}/{task_count} | "
                f"in_progress={counts['in_progress']} | "
                f"blocked={counts['blocked']} | "
                f"todo={counts['todo']} | "
                f"cancelled={counts['cancelled']}"
            ),
            (
                f"Activity: runs={totals['run_count']} | "
                f"tokens={totals['total_token_count']} | "
                f"cost_usd={_format_usd(float(totals['total_cost_usd']))}"
            ),
        ]
    )

    for status, label in BOARD_STATUS_SECTIONS:
        if status == "cancelled" and counts["cancelled"] == 0:
            continue
        lines.append(f"{label} ({counts[status]})")
        status_tasks = [task for task in tasks if task.status == status]
        if not status_tasks:
            lines.append("- none")
            continue
        for task in status_tasks:
            metrics = task_totals.get(task.id, {})
            details: list[str] = []
            token_count = int(metrics.get("total_token_count", 0))
            if token_count:
                details.append(f"tokens={token_count}")
            if task.branch_name:
                details.append(f"branch={task.branch_name}")
            if task.assigned_role:
                details.append(f"role={task.assigned_role}")
            if task.workflow_current_step:
                details.append(f"step={task.workflow_current_step}")
            if task.step_visit_counts:
                details.append(f"visits={_format_step_visits(task.step_visit_counts)}")
            if task.blocked_reason:
                details.append(f"reason={task.blocked_reason}")
            lines.append(_render_board_task_line(task.id, task.title, task.task_type, details))

    _print_lines(*lines)
    return 0


def handle_history(args: argparse.Namespace) -> int:
    """Handle ``foreman history``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = store.get_task(args.task_id)
        if task is None:
            print(f"Unknown task: {args.task_id}", file=sys.stderr)
            return 1

        db_path = store.db_path
        project = store.get_project(task.project_id)
        sprint = store.get_sprint(task.sprint_id)
        runs = store.list_runs(task_id=task.id)
        events = store.list_events(task_id=task.id)
        totals = store.run_totals(task_id=task.id)

    lines = [
        "History",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Project: {task.project_id} | {project.name if project is not None else 'unknown'}",
        f"Sprint: {task.sprint_id} | {sprint.title if sprint is not None else 'unknown'}",
        f"Status: {task.status} | type={task.task_type} | created_by={task.created_by}",
        (
            f"Totals: runs={totals['run_count']} | "
            f"tokens={totals['total_token_count']} | "
            f"cost_usd={_format_usd(float(totals['total_cost_usd']))} | "
            f"duration_ms={totals['total_duration_ms']}"
        ),
        f"Step visits: {_format_step_visits(task.step_visit_counts)}",
    ]
    if task.branch_name:
        lines.append(f"Branch: {task.branch_name}")
    if task.assigned_role:
        lines.append(f"Assigned role: {task.assigned_role}")
    if task.blocked_reason:
        lines.append(f"Blocked reason: {task.blocked_reason}")

    lines.append("Runs:")
    if not runs:
        lines.append("- none")
    else:
        for run in runs:
            parts = [
                run.id,
                f"role={run.role_id}",
                f"step={run.workflow_step}",
                f"backend={run.agent_backend}",
                f"status={run.status}",
                f"cost_usd={_format_usd(run.cost_usd)}",
                f"tokens={run.token_count}",
                f"duration_ms={run.duration_ms or 0}",
                f"retries={run.retry_count}",
            ]
            if run.outcome:
                parts.append(f"outcome={run.outcome}")
            if run.outcome_detail:
                parts.append(f"detail={_truncate_text(run.outcome_detail)}")
            if run.model:
                parts.append(f"model={run.model}")
            if run.session_id:
                parts.append(f"session={run.session_id}")
            lines.append(f"- {' | '.join(parts)}")

    lines.append("Events:")
    if not events:
        lines.append("- none")
    else:
        for event in events:
            lines.append(
                f"- {_render_event_line(event.event_type, event.timestamp, event.role_id, event.payload)}"
            )

    _print_lines(*lines)
    return 0


def handle_task_show(args: argparse.Namespace) -> int:
    """Handle ``foreman task show``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = store.get_task(args.task_id)
        if task is None:
            print(f"Unknown task: {args.task_id}", file=sys.stderr)
            return 1

        db_path = store.db_path
        project = store.get_project(task.project_id)
        sprint = store.get_sprint(task.sprint_id)
        runs = store.list_runs(task_id=task.id)
        events = store.list_events(task_id=task.id)
        totals = store.run_totals(task_id=task.id)

    latest_run = runs[-1] if runs else None
    active_run = next((run for run in reversed(runs) if run.status == "running"), None)
    latest_event = events[-1] if events else None

    lines = [
        "Task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Project: {task.project_id} | {project.name if project is not None else 'unknown'}",
        f"Sprint: {task.sprint_id} | {sprint.title if sprint is not None else 'unknown'}",
        f"Status: {task.status} | type={task.task_type} | created_by={task.created_by}",
        (
            f"Totals: runs={totals['run_count']} | "
            f"tokens={totals['total_token_count']} | "
            f"cost_usd={_format_usd(float(totals['total_cost_usd']))} | "
            f"duration_ms={totals['total_duration_ms']}"
        ),
        f"Step visits: {_format_step_visits(task.step_visit_counts)}",
    ]
    if task.branch_name:
        lines.append(f"Branch: {task.branch_name}")
    if task.assigned_role:
        lines.append(f"Assigned role: {task.assigned_role}")
    if task.workflow_current_step:
        lines.append(f"Current step: {task.workflow_current_step}")
    if task.blocked_reason:
        lines.append(f"Blocked reason: {task.blocked_reason}")

    if active_run is not None:
        lines.append(
            "Active run: "
            f"{active_run.id} | role={active_run.role_id} | step={active_run.workflow_step} | "
            f"status={active_run.status} | started_at={active_run.started_at or 'unknown'}"
        )
    else:
        lines.append("Active run: none")

    if latest_run is not None:
        latest_parts = [
            latest_run.id,
            f"role={latest_run.role_id}",
            f"step={latest_run.workflow_step}",
            f"status={latest_run.status}",
            f"cost_usd={_format_usd(latest_run.cost_usd)}",
            f"tokens={latest_run.token_count}",
            f"duration_ms={latest_run.duration_ms or 0}",
        ]
        if latest_run.outcome:
            latest_parts.append(f"outcome={latest_run.outcome}")
        if latest_run.outcome_detail:
            latest_parts.append(f"detail={_truncate_text(latest_run.outcome_detail)}")
        lines.append(f"Latest run: {' | '.join(latest_parts)}")
    else:
        lines.append("Latest run: none")

    if latest_event is not None:
        lines.append(
            "Latest event: "
            + _render_event_line(
                latest_event.event_type,
                latest_event.timestamp,
                latest_event.role_id,
                latest_event.payload,
            )
        )
    else:
        lines.append("Latest event: none")

    lines.append("Recent runs:")
    recent_runs = runs[-max(args.runs, 0):] if args.runs > 0 else []
    if not recent_runs:
        lines.append("- none")
    else:
        for run in recent_runs:
            parts = [
                run.id,
                f"role={run.role_id}",
                f"step={run.workflow_step}",
                f"status={run.status}",
            ]
            if run.outcome:
                parts.append(f"outcome={run.outcome}")
            if run.outcome_detail:
                parts.append(f"detail={_truncate_text(run.outcome_detail)}")
            lines.append(f"- {' | '.join(parts)}")

    lines.append("Recent events:")
    recent_events = events[-max(args.events, 0):] if args.events > 0 else []
    if not recent_events:
        lines.append("- none")
    else:
        for event in recent_events:
            lines.append(
                f"- {_render_event_line(event.event_type, event.timestamp, event.role_id, event.payload)}"
            )

    _print_lines(*lines)
    return 0


def handle_cost(args: argparse.Namespace) -> int:
    """Handle ``foreman cost``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = store.get_project(args.project_id)
        if project is None:
            print(f"Unknown project: {args.project_id}", file=sys.stderr)
            return 1

        db_path = store.db_path
        sprint = None
        if args.sprint:
            sprint = store.get_sprint(args.sprint)
            if sprint is None:
                print(f"Unknown sprint: {args.sprint}", file=sys.stderr)
                return 1
            if sprint.project_id != project.id:
                print(
                    f"Sprint {sprint.id} does not belong to project {project.id}.",
                    file=sys.stderr,
                )
                return 1

        totals = store.run_totals(
            project_id=project.id,
            sprint_id=sprint.id if sprint is not None else None,
        )
        task_totals = store.task_run_totals(
            sprint_id=sprint.id if sprint is not None else None,
            project_id=None if sprint is not None else project.id,
        )

    lines = [
        "Cost",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        (
            f"Scope: sprint {sprint.id} | {sprint.title}"
            if sprint is not None
            else "Scope: project"
        ),
        (
            f"Totals: runs={totals['run_count']} | "
            f"tokens={totals['total_token_count']} | "
            f"cost_usd={_format_usd(float(totals['total_cost_usd']))} | "
            f"duration_ms={totals['total_duration_ms']}"
        ),
        "By task:",
    ]
    if not task_totals:
        lines.append("- none")
    else:
        for row in task_totals:
            lines.append(
                "- "
                f"{row['task_id']} | {row['task_type']} | {row['task_title']} | "
                f"status={row['task_status']} | runs={row['run_count']} | "
                f"tokens={row['total_token_count']} | "
                f"cost_usd={_format_usd(float(row['total_cost_usd']))}"
            )
    if int(totals["zero_cost_token_runs"]) > 0:
        lines.append(
            "Note: some runs reported token usage with $0.00 cost; persisted USD totals do not infer missing backend pricing."
        )

    _print_lines(*lines)
    return 0


def handle_watch(args: argparse.Namespace) -> int:
    """Handle ``foreman watch``."""

    scope_count = sum(
        1
        for value in (
            args.project_id,
            args.run,
            args.sprint,
        )
        if value is not None
    )
    if scope_count != 1:
        print("Provide exactly one watch scope: project_id, --sprint, or --run.", file=sys.stderr)
        return 1
    if args.idle_timeout is not None and args.idle_timeout < 0:
        print("--idle-timeout must be zero or greater.", file=sys.stderr)
        return 1
    if args.limit < 1:
        print("--limit must be at least 1.", file=sys.stderr)
        return 1

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        if args.run:
            plan = _build_run_watch_plan(store, args.run, limit=args.limit)
            if plan is None:
                print(f"Unknown run: {args.run}", file=sys.stderr)
                return 1
        elif args.sprint:
            plan = _build_sprint_watch_plan(store, args.sprint, limit=args.limit)
            if plan is None:
                print(f"Unknown sprint: {args.sprint}", file=sys.stderr)
                return 1
        else:
            plan = _build_project_watch_plan(store, args.project_id, limit=args.limit)
            if plan is None:
                print(f"Unknown project: {args.project_id}", file=sys.stderr)
                return 1

        _print_stream_lines(
            "Watch",
            *plan.header_lines,
            f"Delivery: recent {args.limit} persisted events followed by live updates",
            f"Exit: {_format_idle_timeout(args.idle_timeout)}",
            "Recent activity:",
        )
        if not plan.recent_events:
            _print_stream_lines("- none")
        else:
            for event in plan.recent_events:
                _print_stream_lines(
                    f"- {_render_event_line(event.event_type, event.timestamp, event.role_id, event.payload)}"
                )

        last_event_id = plan.recent_events[-1].id if plan.recent_events else None
        last_activity_at = time.monotonic()
        try:
            while True:
                recent_events = plan.fetch_events(last_event_id, WATCH_STREAM_BATCH_LIMIT)
                now = time.monotonic()
                if recent_events:
                    for event in recent_events:
                        _print_stream_lines(
                            f"- {_render_event_line(event.event_type, event.timestamp, event.role_id, event.payload)}"
                        )
                        last_event_id = event.id
                    last_activity_at = now
                    continue
                if args.idle_timeout is not None and now - last_activity_at >= args.idle_timeout:
                    if args.idle_timeout > 0:
                        _print_stream_lines(
                            f"Watch ended after {args.idle_timeout:.1f}s without new activity."
                        )
                    return 0
                time.sleep(STREAM_POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            _print_stream_lines("Watch interrupted.")
            return 0

    return 0


def handle_init(args: argparse.Namespace) -> int:
    """Handle ``foreman init``."""

    roles_dir = default_roles_dir()
    workflows_dir = default_workflows_dir()
    repo_path = Path(args.repo_path).expanduser().resolve()
    db_path = _resolve_db_path_or_print(args.db, repo_path=repo_path)
    if db_path is None:
        return 1
    try:
        roles = load_roles(roles_dir)
        workflows = load_workflows(workflows_dir, available_role_ids=set(roles))
        spec_reference, _ = resolve_spec_path(repo_path, args.spec)
    except (RoleLoadError, WorkflowLoadError, ScaffoldError) as exc:
        print(f"Failed to initialize project: {exc}", file=sys.stderr)
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        existing = store.find_project_by_repo_path(str(repo_path))
        workflow_id = args.workflow or (
            existing.workflow_id if existing is not None else DEFAULT_WORKFLOW_ID
        )
        workflow = workflows.get(workflow_id)
        if workflow is None:
            print(f"Unknown workflow: {workflow_id}", file=sys.stderr)
            return 1

        default_branch = args.default_branch or (
            existing.default_branch if existing is not None else DEFAULT_DEFAULT_BRANCH
        )
        test_command = args.test_command or (
            str(existing.settings.get("test_command", ""))
            if existing is not None
            else DEFAULT_TEST_COMMAND
        )
        if not test_command:
            test_command = DEFAULT_TEST_COMMAND

        try:
            scaffold_result = scaffold_repository(
                repo_path,
                project_name=args.name,
                spec_path=spec_reference,
                default_branch=default_branch,
                test_command=test_command,
            )
        except ScaffoldError as exc:
            print(f"Failed to initialize project: {exc}", file=sys.stderr)
            return 1

        settings = dict(existing.settings) if existing is not None else {}
        for key, value in default_project_settings(test_command=test_command).items():
            settings.setdefault(key, value)
        settings["test_command"] = test_command

        project = Project(
            id=_allocate_project_id(store, args.name, repo_path, existing),
            name=args.name,
            repo_path=str(repo_path),
            spec_path=spec_reference,
            methodology=workflow.methodology,
            workflow_id=workflow_id,
            default_branch=default_branch,
            settings=settings,
            created_at=existing.created_at if existing is not None else utc_now_text(),
            updated_at=utc_now_text(),
        )
        store.save_project(project)
        db_path = store.db_path

    lines = [
        "Initialized project" if existing is None else "Updated project",
        f"Database: {db_path}",
        f"Project ID: {project.id}",
        f"Project name: {project.name}",
        f"Repo: {project.repo_path}",
        f"Spec: {project.spec_path}",
        f"Workflow: {project.workflow_id}",
        f"Default branch: {project.default_branch}",
        "Scaffold:",
    ]
    for artifact in scaffold_result.artifacts:
        lines.append(f"{artifact.path} | {artifact.action}")
    _print_lines(*lines)
    return 0


def handle_projects(args: argparse.Namespace) -> int:
    """Handle ``foreman projects``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        projects = store.list_projects()

        lines = ["Projects", f"Database: {store.db_path}"]
        if not projects:
            lines.extend(
                [
                    "No projects are tracked yet.",
                    f"Use `foreman init <repo_path> --name <name> --spec <path>` to create the default `{DEFAULT_DB_FILENAME}`, or pass `--db PATH` to inspect another store.",
                ]
            )
        else:
            for project in projects:
                active_sprint = store.get_active_sprint(project.id)
                task_counts = store.task_counts(project.id)
                active_sprint_label = active_sprint.title if active_sprint else "none"
                lines.append(
                    f"{project.id} | {project.name} | workflow={project.workflow_id} | active_sprint={active_sprint_label}"
                )
                lines.append(
                    f"repo={project.repo_path} | "
                    f"todo={task_counts['todo']} "
                    f"in_progress={task_counts['in_progress']} "
                    f"blocked={task_counts['blocked']} "
                    f"done={task_counts['done']} "
                    f"cancelled={task_counts['cancelled']}"
                )

    _print_lines(*lines)
    return 0


def handle_status(args: argparse.Namespace) -> int:
    """Handle ``foreman status``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project_count = store.count_projects()
        active_sprint_count = store.count_active_sprints()
        task_counts = store.task_counts()

    lines = ["Status", f"Database: {store.db_path}"]
    if active_sprint_count == 0:
        lines.append("No active projects or sprints.")
    lines.extend(
        [
            f"Projects: {project_count}",
            f"Active sprints: {active_sprint_count}",
            _format_task_counts(task_counts),
        ]
    )
    _print_lines(*lines)
    return 0


def handle_approve(args: argparse.Namespace) -> int:
    """Handle ``foreman approve``."""

    return _handle_human_gate_decision(args, outcome="approve")


def handle_deny(args: argparse.Namespace) -> int:
    """Handle ``foreman deny``."""

    return _handle_human_gate_decision(args, outcome="deny")


def handle_roles(_: argparse.Namespace) -> int:
    """Handle ``foreman roles``."""

    roles_dir = default_roles_dir()
    try:
        roles = load_roles(roles_dir)
    except RoleLoadError as exc:
        print(f"Failed to load roles: {exc}", file=sys.stderr)
        return 1

    lines = ["Roles", f"Directory: {roles_dir}"]
    for role in roles.values():
        model = role.agent.model or "project-default"
        persistence = "persistent" if role.agent.session_persistence else "ephemeral"
        lines.append(
            f"{role.id} | backend={role.agent.backend} | model={model} | session={persistence}"
        )
    _print_lines(*lines)
    return 0


def handle_workflows(_: argparse.Namespace) -> int:
    """Handle ``foreman workflows``."""

    roles_dir = default_roles_dir()
    workflows_dir = default_workflows_dir()
    try:
        role_ids = set(load_roles(roles_dir))
        workflows = load_workflows(workflows_dir, available_role_ids=role_ids)
    except (RoleLoadError, WorkflowLoadError) as exc:
        print(f"Failed to load workflows: {exc}", file=sys.stderr)
        return 1

    lines = ["Workflows", f"Directory: {workflows_dir}"]
    for workflow in workflows.values():
        fallback_action = workflow.fallback.action if workflow.fallback else "none"
        lines.append(
            f"{workflow.id} | methodology={workflow.methodology} | "
            f"entry={workflow.entry_step} | steps={len(workflow.steps)} | "
            f"transitions={len(workflow.transitions)} | gates={len(workflow.gates)} | "
            f"fallback={fallback_action}"
        )
    _print_lines(*lines)
    return 0


def handle_project(args: argparse.Namespace) -> int:
    """Handle ``foreman project``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = _resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        active_sprint = store.get_active_sprint(project.id)
        task_counts = store.task_counts(project_id=project.id)
        totals = store.run_totals(project_id=project.id)
        project_sprints = store.list_sprints(project.id)
        db_path = store.db_path

    lines = [
        "Project",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Repo: {project.repo_path}",
        f"Spec: {project.spec_path or 'n/a'}",
        (
            f"Workflow: {project.workflow_id} | methodology={project.methodology} | "
            f"default_branch={project.default_branch}"
        ),
        (
            f"Active sprint: {active_sprint.id} | {active_sprint.title}"
            if active_sprint is not None
            else "Active sprint: none"
        ),
        f"Sprints: {len(project_sprints)}",
        _format_task_counts(task_counts),
        _format_run_totals(totals),
        "Settings:",
    ]
    if not project.settings:
        lines.append("- none")
    else:
        for key in sorted(project.settings):
            lines.append(f"- {key}={_format_setting_value(project.settings[key])}")
    _print_lines(*lines)
    return 0


def handle_sprint_add(args: argparse.Namespace) -> int:
    """Handle ``foreman sprint add``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = _resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        sprints = store.list_sprints(project.id)
        sprint = Sprint(
            id=_allocate_entity_id("sprint", args.title, exists=store.get_sprint),
            project_id=project.id,
            title=args.title,
            goal=args.goal,
            status="planned",
            order_index=_next_order_index([item.order_index for item in sprints]),
        )
        store.save_sprint(sprint)
        db_path = store.db_path

    _print_lines(
        "Created sprint",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Sprint: {sprint.id} | {sprint.title}",
        f"Goal: {sprint.goal or 'n/a'}",
        f"Status: {sprint.status}",
        f"Order: {sprint.order_index}",
    )
    return 0


def handle_sprint_activate(args: argparse.Namespace) -> int:
    """Handle ``foreman sprint activate``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        sprint = _resolve_sprint_or_print(store, args.sprint_id)
        if sprint is None:
            return 1
        if sprint.status in {"completed", "cancelled"}:
            print(
                f"Sprint {sprint.id} cannot be activated from status {sprint.status}.",
                file=sys.stderr,
            )
            return 1

        active_sprint = store.get_active_sprint(sprint.project_id)
        if active_sprint is not None and active_sprint.id != sprint.id:
            print(
                f"Project {sprint.project_id} already has active sprint {active_sprint.id}.",
                file=sys.stderr,
            )
            return 1

        if sprint.status != "active":
            sprint.status = "active"
            sprint.started_at = sprint.started_at or utc_now_text()
            sprint.completed_at = None
            store.save_sprint(sprint)
        db_path = store.db_path
        project = store.get_project(sprint.project_id)

    _print_lines(
        "Activated sprint",
        f"Database: {db_path}",
        f"Project: {sprint.project_id} | {project.name if project is not None else 'unknown'}",
        f"Sprint: {sprint.id} | {sprint.title}",
        f"Status: {sprint.status}",
    )
    return 0


def handle_sprint_list(args: argparse.Namespace) -> int:
    """Handle ``foreman sprint list``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = _resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        sprints = store.list_sprints(project.id)
        db_path = store.db_path

        lines = [
            "Sprints",
            f"Database: {db_path}",
            f"Project: {project.id} | {project.name}",
        ]
        if not sprints:
            lines.append("No sprints are defined for this project.")
        else:
            for sprint in sprints:
                counts = store.task_counts(sprint_id=sprint.id)
                totals = store.run_totals(project_id=project.id, sprint_id=sprint.id)
                lines.append(
                    f"{sprint.id} | status={sprint.status} | order={sprint.order_index} | title={sprint.title}"
                )
                lines.append(
                    f"goal={sprint.goal or 'n/a'} | {_format_task_counts(counts)} | {_format_run_totals(totals)}"
                )

    _print_lines(*lines)
    return 0


def handle_sprint_complete(args: argparse.Namespace) -> int:
    """Handle ``foreman sprint complete``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        sprint = _resolve_sprint_or_print(store, args.sprint_id)
        if sprint is None:
            return 1
        if sprint.status == "cancelled":
            print(f"Sprint {sprint.id} is cancelled and cannot be completed.", file=sys.stderr)
            return 1

        unresolved = [
            task.id
            for task in store.list_tasks(sprint_id=sprint.id)
            if task.status not in {"done", "cancelled"}
        ]
        if unresolved:
            print(
                "Sprint cannot be completed while unresolved tasks remain: "
                + ", ".join(unresolved),
                file=sys.stderr,
            )
            return 1

        if sprint.status != "completed":
            completion_time = utc_now_text()
            sprint.status = "completed"
            sprint.started_at = sprint.started_at or completion_time
            sprint.completed_at = completion_time
            store.save_sprint(sprint)
        project = store.get_project(sprint.project_id)
        db_path = store.db_path

    _print_lines(
        "Completed sprint",
        f"Database: {db_path}",
        f"Project: {sprint.project_id} | {project.name if project is not None else 'unknown'}",
        f"Sprint: {sprint.id} | {sprint.title}",
        f"Status: {sprint.status}",
        f"Completed at: {sprint.completed_at}",
    )
    return 0


def handle_task_add(args: argparse.Namespace) -> int:
    """Handle ``foreman task add``."""

    if args.task_type not in TASK_TYPES:
        print(
            f"Unsupported task type: {args.task_type}. Expected one of: {', '.join(TASK_TYPES)}.",
            file=sys.stderr,
        )
        return 1

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = _resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        sprint = _select_task_creation_sprint(store, project.id)
        if sprint is None:
            print(
                f"Project {project.id} has no active or planned sprint. Create one with `foreman sprint add` first.",
                file=sys.stderr,
            )
            return 1

        existing_tasks = store.list_tasks(sprint_id=sprint.id)
        task = Task(
            id=_allocate_entity_id("task", args.title, exists=store.get_task),
            sprint_id=sprint.id,
            project_id=project.id,
            title=args.title,
            task_type=args.task_type,
            acceptance_criteria=args.criteria,
            order_index=_next_order_index([item.order_index for item in existing_tasks]),
        )
        store.save_task(task)
        db_path = store.db_path

    _print_lines(
        "Created task",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Sprint: {sprint.id} | {sprint.title}",
        f"Task: {task.id} | {task.title}",
        f"Type: {task.task_type}",
        f"Criteria: {task.acceptance_criteria or 'n/a'}",
        f"Status: {task.status}",
    )
    return 0


def handle_task_list(args: argparse.Namespace) -> int:
    """Handle ``foreman task list``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = _resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        sprint_filter = getattr(args, "sprint", None)
        sprints = store.list_sprints(project.id)
        if sprint_filter:
            sprints = [s for s in sprints if s.id == sprint_filter]
        sprint_ids = {s.id for s in sprints}
        tasks = store.list_tasks(project_id=project.id)
        tasks = [t for t in tasks if t.sprint_id in sprint_ids]
        totals_by_task = {
            str(row["task_id"]): row for row in store.task_run_totals(project_id=project.id)
        }
        tasks_by_sprint: dict[str, list[Task]] = {}
        for task in tasks:
            tasks_by_sprint.setdefault(task.sprint_id, []).append(task)

        lines = [
            "Tasks",
            f"Database: {store.db_path}",
            f"Project: {project.id} | {project.name}",
        ]
        if not tasks:
            lines.append("No tasks are defined for this project.")
        else:
            for sprint in sprints:
                sprint_tasks = tasks_by_sprint.get(sprint.id, [])
                if not sprint_tasks:
                    continue
                lines.append(
                    f"Sprint: {sprint.id} | {sprint.title} | status={sprint.status}"
                )
                for task in sprint_tasks:
                    totals = totals_by_task.get(task.id, {})
                    lines.append(
                        f"- {task.id} | {task.task_type} | {task.title} | status={task.status} | "
                        f"runs={totals.get('run_count', 0)} | "
                        f"tokens={totals.get('total_token_count', 0)} | "
                        f"cost_usd={_format_usd(float(totals.get('total_cost_usd', 0.0)))}"
                    )

    _print_lines(*lines)
    return 0


def handle_task_block(args: argparse.Namespace) -> int:
    """Handle ``foreman task block``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = _resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        if task.status in {"done", "cancelled"}:
            print(
                f"Task {task.id} cannot be blocked from status {task.status}.",
                file=sys.stderr,
            )
            return 1

        task.status = "blocked"
        task.blocked_reason = args.reason
        task.completed_at = None
        store.save_task(task)
        db_path = store.db_path

    _print_lines(
        "Blocked task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
        f"Reason: {task.blocked_reason}",
    )
    return 0


def handle_task_unblock(args: argparse.Namespace) -> int:
    """Handle ``foreman task unblock``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = _resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        if task.status != "blocked":
            print(f"Task {task.id} is not blocked.", file=sys.stderr)
            return 1
        if task.workflow_current_step is not None:
            print(
                f"Task {task.id} is paused at a workflow gate; use `foreman approve` or `foreman deny` instead.",
                file=sys.stderr,
            )
            return 1

        task.status = "todo"
        task.blocked_reason = None
        task.workflow_current_step = None
        task.workflow_carried_output = None
        task.step_visit_counts = {}
        task.completed_at = None
        store.save_task(task)
        db_path = store.db_path

    _print_lines(
        "Unblocked task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
        "Step visits reset: yes",
    )
    return 0


def handle_task_cancel(args: argparse.Namespace) -> int:
    """Handle ``foreman task cancel``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = _resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        if task.status == "done":
            print(f"Task {task.id} is already done and cannot be cancelled.", file=sys.stderr)
            return 1

        if task.status != "cancelled":
            task.status = "cancelled"
            task.blocked_reason = None
            task.workflow_current_step = None
            task.workflow_carried_output = None
            task.completed_at = utc_now_text()
            store.save_task(task)
        db_path = store.db_path

    _print_lines(
        "Cancelled task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
        f"Completed at: {task.completed_at}",
    )
    return 0


def handle_run(args: argparse.Namespace) -> int:
    """Handle ``foreman run``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = _resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        orchestrator = ForemanOrchestrator(store)
        try:
            result = orchestrator.run_project(project.id, task_id=args.task)
        except OrchestratorError as exc:
            print(f"Failed to run project: {exc}", file=sys.stderr)
            return 1
        db_path = store.db_path

    _print_lines(
        "Run",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        (f"Scope: task {args.task}" if args.task is not None else "Scope: project"),
        (
            "Executed tasks: " + ", ".join(result.executed_task_ids)
            if result.executed_task_ids
            else "Executed tasks: none"
        ),
        (
            "Blocked tasks: " + ", ".join(result.blocked_task_ids)
            if result.blocked_task_ids
            else "Blocked tasks: none"
        ),
        f"Stop reason: {result.stop_reason}",
    )
    return 0


def handle_config(args: argparse.Namespace) -> int:
    """Handle ``foreman config``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = _resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        assignment_summary = None
        if args.config_set:
            try:
                key, value = _parse_config_assignment(args.config_set)
            except CliResolutionError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            project.settings[key] = value
            project.updated_at = utc_now_text()
            store.save_project(project)
            assignment_summary = f"{key}={_format_setting_value(value)}"
        db_path = store.db_path

    lines = [
        "Updated config" if assignment_summary is not None else "Config",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Workflow: {project.workflow_id} | default_branch={project.default_branch}",
    ]
    if assignment_summary is not None:
        lines.append(f"Changed: {assignment_summary}")
    lines.append("Settings:")
    if not project.settings:
        lines.append("- none")
    else:
        for key in sorted(project.settings):
            lines.append(f"- {key}={_format_setting_value(project.settings[key])}")
    _print_lines(*lines)
    return 0


def handle_db_version(args: argparse.Namespace) -> int:
    """Handle ``foreman db version``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        try:
            version = store.schema_version()
        except sqlite3.OperationalError:
            print(
                "Schema version: 0 "
                "(schema_migrations table not present — run `foreman db migrate`)"
            )
            return 0

    latest = max((v for v, _, _ in MIGRATIONS), default=0)
    if version == latest:
        print(f"Schema version: {version} (up to date)")
    else:
        print(f"Schema version: {version} (latest available: {latest})")
    return 0


def handle_db_migrate(args: argparse.Namespace) -> int:
    """Handle ``foreman db migrate``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        applied = store.initialize()
        current_version = store.schema_version()

    if not applied:
        print(f"Schema is already up to date at version {current_version}.")
        return 0

    descriptions = {v: desc for v, desc, _ in MIGRATIONS}
    print(f"Applied {len(applied)} migration(s):")
    for v in applied:
        print(f"  [{v}] {descriptions.get(v, '(no description)')}")
    return 0


def handle_dashboard(args: argparse.Namespace) -> int:
    """Handle ``foreman dashboard``."""

    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    try:
        run_dashboard_server(
            db_path=db_path,
            host=args.host,
            port=args.port,
            frontend_mode=args.frontend_mode,
            frontend_dev_url=args.frontend_dev_url,
            reload=args.reload,
        )
    except (OSError, RuntimeError) as exc:
        print(f"Failed to start dashboard: {exc}", file=sys.stderr)
        return 1
    return 0


def _set_handler(
    parser: argparse.ArgumentParser, handler: Handler, command_path: str
) -> argparse.ArgumentParser:
    parser.set_defaults(handler=handler, command_path=command_path)
    return parser


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI argument parser."""

    parser = argparse.ArgumentParser(prog="foreman", description=CLI_DESCRIPTION)
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a repository for Foreman.",
    )
    init_parser.add_argument("repo_path", help="Path to the target repository.")
    init_parser.add_argument("--name", required=True, help="Human-readable project name.")
    init_parser.add_argument("--spec", required=True, help="Path to the project spec.")
    _add_db_option(
        init_parser,
        help_text=f"Path to the SQLite store to initialize or update. Defaults to <repo>/{DEFAULT_DB_FILENAME}.",
    )
    init_parser.add_argument(
        "--workflow",
        default=None,
        help="Workflow identifier to assign to the project. Defaults to `development` for new projects; use `development_secure` to require a security review step before test and merge.",
    )
    init_parser.add_argument(
        "--default-branch",
        default=None,
        help="Default branch for the target repository. Defaults to `main` for new projects.",
    )
    init_parser.add_argument(
        "--test-command",
        default=None,
        help="Override the persisted test command for the initialized project.",
    )
    _set_handler(init_parser, handle_init, "init")

    projects_parser = subparsers.add_parser(
        "projects",
        help="List tracked projects.",
    )
    _add_db_option(projects_parser)
    _set_handler(projects_parser, handle_projects, "projects")

    project_parser = subparsers.add_parser(
        "project",
        help="Inspect one project.",
    )
    project_parser.add_argument("project_id", help="Project identifier.")
    _add_db_option(
        project_parser,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    _set_handler(project_parser, handle_project, "project")

    sprint_parser = subparsers.add_parser(
        "sprint",
        help="Manage sprints.",
    )
    sprint_commands = sprint_parser.add_subparsers(
        dest="sprint_command",
        metavar="sprint_command",
        required=True,
    )
    sprint_add = sprint_commands.add_parser("add", help="Create a sprint.")
    sprint_add.add_argument("project_id", help="Project identifier.")
    sprint_add.add_argument("--title", required=True, help="Sprint title.")
    sprint_add.add_argument("--goal", required=True, help="Sprint goal.")
    _add_db_option(
        sprint_add,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    _set_handler(sprint_add, handle_sprint_add, "sprint add")

    sprint_activate = sprint_commands.add_parser(
        "activate",
        help="Activate a sprint.",
    )
    sprint_activate.add_argument("sprint_id", help="Sprint identifier.")
    _add_db_option(
        sprint_activate,
        help_text=f"Path to the SQLite store containing the sprint. {DB_OPTION_NOTE}",
    )
    _set_handler(sprint_activate, handle_sprint_activate, "sprint activate")

    sprint_list = sprint_commands.add_parser("list", help="List project sprints.")
    sprint_list.add_argument("project_id", help="Project identifier.")
    _add_db_option(
        sprint_list,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    _set_handler(sprint_list, handle_sprint_list, "sprint list")

    sprint_complete = sprint_commands.add_parser(
        "complete",
        help="Complete a sprint.",
    )
    sprint_complete.add_argument("sprint_id", help="Sprint identifier.")
    _add_db_option(
        sprint_complete,
        help_text=f"Path to the SQLite store containing the sprint. {DB_OPTION_NOTE}",
    )
    _set_handler(sprint_complete, handle_sprint_complete, "sprint complete")

    task_parser = subparsers.add_parser(
        "task",
        help="Manage tasks.",
    )
    task_commands = task_parser.add_subparsers(
        dest="task_command",
        metavar="task_command",
        required=True,
    )
    task_add = task_commands.add_parser("add", help="Create a task.")
    task_add.add_argument("project_id", help="Project identifier.")
    task_add.add_argument("--title", required=True, help="Task title.")
    task_add.add_argument("--type", dest="task_type", default="feature", help="Task type.")
    task_add.add_argument("--criteria", required=True, help="Acceptance criteria.")
    _add_db_option(
        task_add,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    _set_handler(task_add, handle_task_add, "task add")

    task_list = task_commands.add_parser("list", help="List project tasks.")
    task_list.add_argument("project_id", help="Project identifier.")
    task_list.add_argument("--sprint", metavar="SPRINT_ID", help="Filter to a specific sprint.")
    _add_db_option(
        task_list,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    _set_handler(task_list, handle_task_list, "task list")

    task_show = task_commands.add_parser("show", help="Show one task with recent runs and events.")
    task_show.add_argument("task_id", help="Task identifier.")
    task_show.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of recent runs to include.",
    )
    task_show.add_argument(
        "--events",
        type=int,
        default=8,
        help="Number of recent events to include.",
    )
    _add_db_option(
        task_show,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    _set_handler(task_show, handle_task_show, "task show")

    task_block = task_commands.add_parser("block", help="Block a task.")
    task_block.add_argument("task_id", help="Task identifier.")
    task_block.add_argument("--reason", required=True, help="Blocking reason.")
    _add_db_option(
        task_block,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    _set_handler(task_block, handle_task_block, "task block")

    task_unblock = task_commands.add_parser("unblock", help="Unblock a task.")
    task_unblock.add_argument("task_id", help="Task identifier.")
    _add_db_option(
        task_unblock,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    _set_handler(task_unblock, handle_task_unblock, "task unblock")

    task_cancel = task_commands.add_parser("cancel", help="Cancel a task.")
    task_cancel.add_argument("task_id", help="Task identifier.")
    _add_db_option(
        task_cancel,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    _set_handler(task_cancel, handle_task_cancel, "task cancel")

    run_parser = subparsers.add_parser("run", help="Run Foreman against a project.")
    run_parser.add_argument("project_id", help="Project identifier.")
    run_parser.add_argument("--task", help="Single task identifier to run.")
    _add_db_option(
        run_parser,
        help_text=f"Path to the SQLite store containing the project workflow state. {DB_OPTION_NOTE}",
    )
    _set_handler(run_parser, handle_run, "run")

    status_parser = subparsers.add_parser(
        "status",
        help="Show a cross-project status overview.",
    )
    _add_db_option(status_parser)
    _set_handler(status_parser, handle_status, "status")

    board_parser = subparsers.add_parser("board", help="Show a terminal task board.")
    board_parser.add_argument("project_id", help="Project identifier.")
    _add_db_option(
        board_parser,
        help_text=f"Path to the SQLite store containing the project board state. {DB_OPTION_NOTE}",
    )
    _set_handler(board_parser, handle_board, "board")

    watch_parser = subparsers.add_parser("watch", help="Tail project, sprint, or run events.")
    watch_parser.add_argument("project_id", nargs="?", help="Project identifier.")
    watch_parser.add_argument("--run", help="Run identifier.")
    watch_parser.add_argument("--sprint", help="Sprint identifier.")
    watch_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum number of recent persisted events to show before live tailing.",
    )
    watch_parser.add_argument(
        "--idle-timeout",
        type=float,
        help="Exit after this many idle seconds without new events. Omit to keep tailing until interrupted.",
    )
    _add_db_option(
        watch_parser,
        help_text=f"Path to the SQLite store containing project or run activity. {DB_OPTION_NOTE}",
    )
    _set_handler(watch_parser, handle_watch, "watch")

    cost_parser = subparsers.add_parser("cost", help="Show project cost totals.")
    cost_parser.add_argument("project_id", help="Project identifier.")
    cost_parser.add_argument("--sprint", help="Sprint identifier.")
    _add_db_option(
        cost_parser,
        help_text=f"Path to the SQLite store containing project run totals. {DB_OPTION_NOTE}",
    )
    _set_handler(cost_parser, handle_cost, "cost")

    history_parser = subparsers.add_parser(
        "history",
        help="Show run and event history for a task.",
    )
    history_parser.add_argument("task_id", help="Task identifier.")
    _add_db_option(
        history_parser,
        help_text=f"Path to the SQLite store containing task history. {DB_OPTION_NOTE}",
    )
    _set_handler(history_parser, handle_history, "history")

    approve_parser = subparsers.add_parser("approve", help="Approve a paused task.")
    approve_parser.add_argument("task_id", help="Task identifier.")
    approve_parser.add_argument("--note", help="Optional approval note.")
    _add_db_option(
        approve_parser,
        help_text=f"Path to the SQLite store containing the paused task. {DB_OPTION_NOTE}",
    )
    _set_handler(approve_parser, handle_approve, "approve")

    deny_parser = subparsers.add_parser("deny", help="Deny a paused task.")
    deny_parser.add_argument("task_id", help="Task identifier.")
    deny_parser.add_argument("--note", help="Optional denial note.")
    _add_db_option(
        deny_parser,
        help_text=f"Path to the SQLite store containing the paused task. {DB_OPTION_NOTE}",
    )
    _set_handler(deny_parser, handle_deny, "deny")

    roles_parser = subparsers.add_parser("roles", help="List available roles.")
    _set_handler(roles_parser, handle_roles, "roles")

    workflows_parser = subparsers.add_parser(
        "workflows",
        help="List available workflows.",
    )
    _set_handler(workflows_parser, handle_workflows, "workflows")

    config_parser = subparsers.add_parser(
        "config",
        help="Inspect or mutate project configuration.",
    )
    config_parser.add_argument("project_id", help="Project identifier.")
    config_parser.add_argument(
        "--set",
        dest="config_set",
        help="Configuration assignment in key=value form.",
    )
    _add_db_option(
        config_parser,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    _set_handler(config_parser, handle_config, "config")

    db_parser = subparsers.add_parser("db", help="Database management commands.")
    db_commands = db_parser.add_subparsers(dest="db_command", metavar="db_command")

    db_version_parser = db_commands.add_parser(
        "version",
        help="Show the current schema version.",
    )
    _add_db_option(db_version_parser)
    _set_handler(db_version_parser, handle_db_version, "db version")

    db_migrate_parser = db_commands.add_parser(
        "migrate",
        help="Apply pending schema migrations.",
    )
    _add_db_option(db_migrate_parser)
    _set_handler(db_migrate_parser, handle_db_migrate, "db migrate")

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Start the web dashboard.",
    )
    _add_db_option(
        dashboard_parser,
        help_text=f"Path to the SQLite store for dashboard data. {DB_OPTION_NOTE}",
    )
    dashboard_parser.add_argument(
        "--host",
        default="localhost",
        help="Host to bind to (default: localhost).",
    )
    dashboard_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080).",
    )
    dashboard_parser.add_argument(
        "--frontend-mode",
        choices=("dist", "dev"),
        default="dist",
        help=(
            "Frontend delivery mode. Use `dist` for the shipped built React app "
            "and `dev` when a Vite dev server will serve the frontend shell."
        ),
    )
    dashboard_parser.add_argument(
        "--frontend-dev-url",
        default=DEFAULT_FRONTEND_DEV_URL,
        help=(
            "Origin for the frontend dev server when `--frontend-mode dev` is used "
            f"(default: {DEFAULT_FRONTEND_DEV_URL})."
        ),
    )
    dashboard_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn reload support for local dashboard backend development.",
    )
    _set_handler(dashboard_parser, handle_dashboard, "dashboard")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Foreman CLI."""

    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        parser.print_help()
        return 0

    args = parser.parse_args(list(argv))
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    return handler(args)


def _allocate_project_id(
    store: ForemanStore,
    name: str,
    repo_path: Path,
    existing: Project | None,
) -> str:
    if existing is not None:
        return existing.id

    base_id = generate_project_id(name, repo_path)
    candidate = base_id
    suffix = 2
    while True:
        stored = store.get_project(candidate)
        if stored is None or stored.repo_path == str(repo_path):
            return candidate
        candidate = f"{base_id}-{suffix}"
        suffix += 1


def _handle_human_gate_decision(args: argparse.Namespace, *, outcome: str) -> int:
    db_path = _resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        orchestrator = ForemanOrchestrator(store)
        try:
            result = orchestrator.resume_human_gate(
                args.task_id,
                outcome=outcome,
                note=args.note,
            )
        except OrchestratorError as exc:
            print(f"Failed to {outcome} task: {exc}", file=sys.stderr)
            return 1
        db_path = store.db_path

    action = "Approved" if outcome == "approve" else "Denied"
    lines = [
        f"{action} task",
        f"Database: {db_path}",
        f"Task ID: {result.task.id}",
        f"Resume from: {result.paused_step}",
        f"Next step: {result.next_step}",
        f"Status: {result.task.status}",
        f"Resume deferred: {'yes' if result.deferred else 'no'}",
    ]
    if args.note:
        lines.append(f"Note: {args.note}")
    if result.task.workflow_current_step:
        lines.append(f"Persisted step: {result.task.workflow_current_step}")
    if result.task.blocked_reason:
        lines.append(f"Blocked reason: {result.task.blocked_reason}")
    _print_lines(*lines)
    return 0
