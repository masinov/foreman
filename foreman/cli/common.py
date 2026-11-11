"""What every command shares: finding the database, resolving ids, formatting output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

from ..engine_control import (
    default_command_requester,
)
from ..models import Event, Project, Sprint, Task
from ..roles import RoleLoadError, default_roles_dir, load_roles
from ..mutations import Mutations
from ..scaffold import (
    DEFAULT_DB_FILENAME,
    generate_project_id,
)
from ..store import ForemanStore
from ..workflows import WorkflowLoadError, default_workflows_dir, load_workflows


#: Exit code of ``foreman run`` when the pass stopped because the agent backend's
#: usage quota ran out (BSD ``EX_TEMPFAIL``): nothing is broken, try again later.
EXIT_QUOTA_EXHAUSTED = 75


DB_OPTION_NOTE = (
    f"Defaults to repo-local `{DEFAULT_DB_FILENAME}` discovery; pass `--db PATH` to override."
)


Handler = Callable[[argparse.Namespace], int]


class CliResolutionError(ValueError):
    """Raised when CLI runtime inputs cannot be resolved safely."""


def add_json_option(parser: argparse.ArgumentParser) -> None:
    """Let a read command print one JSON document for another program to read."""

    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Print the result as one JSON document.",
    )


def print_json(payload: Any) -> None:
    """Print one JSON document (keys in insertion order, two-space indent)."""

    print_lines(json.dumps(payload, indent=2, default=str))


def print_lines(*lines: str) -> None:
    try:
        for line in lines:
            print(line)
    except BrokenPipeError:  # pragma: no cover - depends on shell piping
        raise SystemExit(0) from None


def print_stream_lines(*lines: str) -> None:
    try:
        for line in lines:
            print(line, flush=True)
    except BrokenPipeError:  # pragma: no cover - depends on shell piping
        raise SystemExit(0) from None


def add_db_option(
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


def iter_parent_paths(start_path: Path) -> tuple[Path, ...]:
    resolved = start_path.expanduser().resolve()
    return (resolved, *resolved.parents)


def discover_repo_local_db_path(start_path: Path | None = None) -> Path | None:
    base = start_path or Path.cwd()
    for candidate in iter_parent_paths(base):
        db_path = candidate / DEFAULT_DB_FILENAME
        if db_path.is_file():
            return db_path
    return None


def looks_like_repo_root(path: Path) -> bool:
    return (
        (path / "AGENTS.md").is_file()
        or (path / ".git").exists()
        or (path / ".foreman").exists()
    )


def discover_repo_root(start_path: Path | None = None) -> Path | None:
    base = start_path or Path.cwd()
    for candidate in iter_parent_paths(base):
        if looks_like_repo_root(candidate):
            return candidate
    return None


def resolve_db_path(
    explicit_db: str | None,
    *,
    repo_path: str | Path | None = None,
) -> Path:
    if explicit_db:
        return Path(explicit_db).expanduser().resolve()

    if repo_path is not None:
        return Path(repo_path).expanduser().resolve() / DEFAULT_DB_FILENAME

    discovered_db = discover_repo_local_db_path()
    if discovered_db is not None:
        return discovered_db

    repo_root = discover_repo_root()
    if repo_root is not None:
        raise CliResolutionError(
            f"No repo-local Foreman database found at {repo_root / DEFAULT_DB_FILENAME}. "
            "Run `foreman init <repo_path> --name <name> --spec <path>` or pass `--db PATH`."
        )

    raise CliResolutionError(
        "Could not discover a Foreman repository from the current directory. "
        "Run the command from a Foreman repo or pass `--db PATH`."
    )


def resolve_db_path_or_print(
    explicit_db: str | None,
    *,
    repo_path: str | Path | None = None,
) -> str | None:
    try:
        return str(resolve_db_path(explicit_db, repo_path=repo_path))
    except CliResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return None


#: What each dead-letter kind means to the person reading it, and which command
#: clears it.
BLOCKED_KIND_HINTS = {
    "gate": "waiting for `foreman approve` or `foreman deny`",
    "engine": "blocked by the engine; clear with `foreman task unblock`",
}


def format_task_counts(counts: dict[str, int]) -> str:
    return (
        "Tasks: "
        f"triage={counts['triage']} "
        f"todo={counts['todo']} "
        f"in_progress={counts['in_progress']} "
        f"blocked={counts['blocked']} "
        f"done={counts['done']} "
        f"cancelled={counts['cancelled']}"
    )


def format_run_totals(totals: dict[str, int | float]) -> str:
    return (
        f"Activity: runs={totals['run_count']} | "
        f"tokens={totals['total_token_count']} | "
        f"cost_usd={format_usd(float(totals['total_cost_usd']))} | "
        f"duration_ms={totals['total_duration_ms']}"
    )


def format_usd(value: float) -> str:
    return f"${value:.2f}"


def format_idle_timeout(value: float | None) -> str:
    if value is None:
        return "until interrupted"
    return f"{value:.1f}s of inactivity"


def format_step_visits(step_visit_counts: dict[str, int]) -> str:
    if not step_visit_counts:
        return "none"
    return ", ".join(f"{step}={count}" for step, count in step_visit_counts.items())


def truncate_text(text: str, *, limit: int = 96) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def format_event_details(event_type: str, payload: dict[str, object]) -> str:
    if event_type == "agent.command":
        command = str(payload.get("command", "")).strip()
        return truncate_text(command or "(no command recorded)")

    if event_type == "agent.file_change":
        path = str(payload.get("path", "")).strip()
        return path or "(no path recorded)"

    if event_type == "agent.message":
        text = str(payload.get("text", "")).strip()
        return truncate_text(text or "(no message text)")

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
            parts.append(f"note={truncate_text(note)}")
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
        parts.append(f"{key}={truncate_text(str(value))}")
    return " | ".join(parts) if parts else "(no payload details)"


def render_event_line(event_type: str, timestamp: str, role_id: str | None, payload: dict[str, object]) -> str:
    line = f"{timestamp} | {event_type}"
    if role_id:
        line = f"{line} | role={role_id}"
    return f"{line} | {format_event_details(event_type, payload)}"


def indent_lines(text: str, *, prefix: str = "    ") -> list[str]:
    if not text:
        return [f"{prefix}(empty)"]
    return [f"{prefix}{line}" for line in text.splitlines()]


def format_transcript_payload(event: Event) -> list[str]:
    payload = event.payload
    if not payload:
        return ["    {}"]

    if event.event_type == "agent.prompt":
        return indent_lines(str(payload.get("text", "")))

    if event.event_type == "agent.raw_output":
        stream = str(payload.get("stream", "")).strip() or "unknown"
        if "line" in payload:
            return [f"    stream={stream}", *indent_lines(str(payload.get("line", "")))]
        raw_message = json.dumps(payload.get("message"), indent=2, sort_keys=True)
        return [f"    stream={stream}", *indent_lines(raw_message)]

    if event.event_type == "engine.test_output":
        stream = str(payload.get("stream", "")).strip() or "unknown"
        return [f"    stream={stream}", *indent_lines(str(payload.get("text", "")))]

    if event.event_type == "engine.test_run":
        lines = [
            f"    command={payload.get('command', '')}",
            f"    exit_code={payload.get('exit_code', '')}",
        ]
        if "stdout" in payload:
            lines.append("    stdout:")
            lines.extend(indent_lines(str(payload.get("stdout", "")), prefix="      "))
        if "stderr" in payload:
            lines.append("    stderr:")
            lines.extend(indent_lines(str(payload.get("stderr", "")), prefix="      "))
        if "output_tail" in payload:
            lines.append("    output_tail:")
            lines.extend(indent_lines(str(payload.get("output_tail", "")), prefix="      "))
        return lines

    return indent_lines(json.dumps(payload, indent=2, sort_keys=True))


def render_board_task_line(task_id: str, title: str, task_type: str, details: list[str]) -> str:
    parts = [task_id, task_type, title]
    parts.extend(detail for detail in details if detail)
    return f"- {' | '.join(parts)}"


def format_watch_activity_totals(totals: dict[str, int | float]) -> str:
    return format_run_totals(totals)


def format_setting_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def parse_config_value(raw_value: str) -> Any:
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


def parse_config_assignment(raw_assignment: str) -> tuple[str, Any]:
    if "=" not in raw_assignment:
        raise CliResolutionError("Configuration assignment must use key=value syntax.")

    key, raw_value = raw_assignment.split("=", 1)
    key = key.strip()
    if not key:
        raise CliResolutionError("Configuration key cannot be empty.")
    return key, parse_config_value(raw_value)


def allocate_entity_id(
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


def next_order_index(values: Sequence[int]) -> int:
    return max(values, default=-1) + 1


def resolve_project_or_print(store: ForemanStore, project_id: str) -> Project | None:
    project = store.get_project(project_id)
    if project is None:
        print(f"Unknown project: {project_id}", file=sys.stderr)
        return None
    return project


def resolve_sprint_or_print(store: ForemanStore, sprint_id: str) -> Sprint | None:
    sprint = store.get_sprint(sprint_id)
    if sprint is None:
        print(f"Unknown sprint: {sprint_id}", file=sys.stderr)
        return None
    return sprint


def resolve_task_or_print(store: ForemanStore, task_id: str) -> Task | None:
    task = store.get_task(task_id)
    if task is None:
        print(f"Unknown task: {task_id}", file=sys.stderr)
        return None
    return task


def select_task_creation_sprint(store: ForemanStore, project_id: str) -> Sprint | None:
    active_sprint = store.get_active_sprint(project_id)
    if active_sprint is not None:
        return active_sprint
    planned_sprints = [
        sprint for sprint in store.list_sprints(project_id) if sprint.status == "planned"
    ]
    return planned_sprints[0] if planned_sprints else None


def role_outcomes(roles: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """Map loaded roles to the outcomes they declare, for workflow validation."""

    return {role_id: role.completion.outcomes for role_id, role in roles.items()}


def project_workflow_step_ids(store: ForemanStore, project: Project) -> set[str] | None:
    """Return the set of agent-step ids for a project's workflow.

    Returns ``None`` (after printing) when workflows cannot be loaded so callers
    can surface the failure as a non-zero exit.
    """

    try:
        roles = load_roles(default_roles_dir())
        workflows = load_workflows(
            default_workflows_dir(),
            available_role_ids=set(roles),
            role_outcomes=role_outcomes(roles),
        )
    except (RoleLoadError, WorkflowLoadError) as exc:
        print(f"Failed to load workflow definitions: {exc}", file=sys.stderr)
        return None

    workflow = workflows.get(project.workflow_id)
    if workflow is None:
        print(
            f"Project {project.id} references unknown workflow {project.workflow_id!r}.",
            file=sys.stderr,
        )
        return None
    return {step.id for step in workflow.steps}


def cli_mutations(store: ForemanStore) -> Mutations:
    """Return the shared mutation service, stamped as the CLI and the OS user."""

    return Mutations(store, via="cli", actor=default_command_requester())


def set_handler(
    parser: argparse.ArgumentParser, handler: Handler, command_path: str
) -> argparse.ArgumentParser:
    parser.set_defaults(handler=handler, command_path=command_path)
    return parser


def token_split_parts(usage: dict[str, int] | None) -> list[str]:
    """Return ``key=value`` parts for a token split, or nothing when it is empty."""

    if not usage or not any(usage.values()):
        return []
    return [
        f"in={usage.get('input', 0)}",
        f"out={usage.get('output', 0)}",
        f"cache_read={usage.get('cache_read', 0)}",
        f"cache_write={usage.get('cache_creation', 0)}",
    ]


def allocate_project_id(
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
