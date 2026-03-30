"""Command-line interface for the Foreman package."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
from typing import Callable, Sequence

from . import __version__
from .dashboard import run_dashboard
from .models import Project, utc_now_text
from .orchestrator import ForemanOrchestrator, OrchestratorError
from .roles import RoleLoadError, default_roles_dir, load_roles
from .scaffold import (
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
CLI_SHELL_NOTE = "This command surface is still incomplete while Foreman is under active development."
STORE_OPTION_NOTE = (
    "SQLite-backed inspection is available now via `--db PATH` for `projects`, `status`, `board`, `history`, `watch`, and `cost`."
)
STORE_FOLLOWUP_NOTE = (
    "Project creation is available via `foreman init --db PATH`; paused human-gate tasks can now be resumed with `foreman approve --db PATH` and `foreman deny --db PATH`."
)
BOARD_STATUS_SECTIONS: tuple[tuple[str, str], ...] = (
    ("todo", "Todo"),
    ("in_progress", "In Progress"),
    ("blocked", "Blocked"),
    ("done", "Done"),
    ("cancelled", "Cancelled"),
)

Handler = Callable[[argparse.Namespace], int]


def _print_lines(*lines: str) -> None:
    for line in lines:
        print(line)


def _add_db_option(
    parser: argparse.ArgumentParser,
    *,
    required: bool = False,
    help_text: str = "Path to the SQLite store to inspect.",
) -> None:
    parser.add_argument(
        "--db",
        required=required,
        help=help_text,
    )


def _format_task_counts(counts: dict[str, int]) -> str:
    return (
        "Tasks: "
        f"todo={counts['todo']} "
        f"in_progress={counts['in_progress']} "
        f"blocked={counts['blocked']} "
        f"done={counts['done']} "
        f"cancelled={counts['cancelled']}"
    )


def _format_usd(value: float) -> str:
    return f"${value:.2f}"


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


def handle_board(args: argparse.Namespace) -> int:
    """Handle ``foreman board``."""

    with ForemanStore(args.db) as store:
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

    with ForemanStore(args.db) as store:
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


def handle_cost(args: argparse.Namespace) -> int:
    """Handle ``foreman cost``."""

    with ForemanStore(args.db) as store:
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

    if args.run and args.project_id:
        print("Do not provide a project_id when using --run.", file=sys.stderr)
        return 1
    if not args.run and not args.project_id:
        print("Provide either a project_id or --run.", file=sys.stderr)
        return 1
    if args.iterations < 1:
        print("--iterations must be at least 1.", file=sys.stderr)
        return 1
    if args.interval < 0:
        print("--interval must be zero or greater.", file=sys.stderr)
        return 1
    if args.limit < 1:
        print("--limit must be at least 1.", file=sys.stderr)
        return 1

    lines: list[str] = ["Watch"]
    with ForemanStore(args.db) as store:
        store.initialize()
        if args.run:
            run = store.get_run(args.run)
            if run is None:
                print(f"Unknown run: {args.run}", file=sys.stderr)
                return 1
            task = store.get_task(run.task_id)
            project = store.get_project(run.project_id)
            lines.extend(
                [
                    f"Database: {store.db_path}",
                    f"Scope: run {run.id}",
                    f"Project: {run.project_id} | {project.name if project is not None else 'unknown'}",
                    f"Task: {run.task_id} | {task.title if task is not None else 'unknown'}",
                ]
            )
            for iteration_index in range(args.iterations):
                current_run = store.get_run(run.id) or run
                current_task = store.get_task(run.task_id) or task
                lines.append(
                    f"Snapshot {iteration_index + 1}/{args.iterations} | {utc_now_text()}"
                )
                lines.append(
                    f"Run: status={current_run.status} | step={current_run.workflow_step} | role={current_run.role_id}"
                )
                recent_events = store.list_recent_events(run_id=run.id, limit=args.limit)
                lines.append("Recent activity:")
                if not recent_events:
                    lines.append("- none")
                else:
                    for event in recent_events:
                        lines.append(
                            f"- {_render_event_line(event.event_type, event.timestamp, event.role_id, event.payload)}"
                        )
                if current_task.blocked_reason:
                    lines.append(f"Blocked reason: {current_task.blocked_reason}")
                if iteration_index + 1 < args.iterations:
                    lines.append("")
                    time.sleep(args.interval)
            _print_lines(*lines)
            return 0

        project = store.get_project(args.project_id)
        if project is None:
            print(f"Unknown project: {args.project_id}", file=sys.stderr)
            return 1

        lines.extend(
            [
                f"Database: {store.db_path}",
                f"Scope: project {project.id}",
                f"Project: {project.id} | {project.name}",
            ]
        )
        for iteration_index in range(args.iterations):
            active_sprint = store.get_active_sprint(project.id)
            sprint_id = active_sprint.id if active_sprint is not None else None
            counts = store.task_counts(
                project_id=project.id if sprint_id is None else None,
                sprint_id=sprint_id,
            )
            totals = store.run_totals(
                project_id=project.id,
                sprint_id=sprint_id,
            )
            recent_events = store.list_recent_events(project_id=project.id, limit=args.limit)
            lines.append(
                f"Snapshot {iteration_index + 1}/{args.iterations} | {utc_now_text()}"
            )
            if active_sprint is None:
                lines.append("Sprint: none")
            else:
                lines.append(f"Sprint: {active_sprint.id} | {active_sprint.title}")
            lines.append(_format_task_counts(counts))
            lines.append(
                f"Activity: runs={totals['run_count']} | tokens={totals['total_token_count']} | cost_usd={_format_usd(float(totals['total_cost_usd']))}"
            )
            lines.append("Recent activity:")
            if not recent_events:
                lines.append("- none")
            else:
                for event in recent_events:
                    lines.append(
                        f"- {_render_event_line(event.event_type, event.timestamp, event.role_id, event.payload)}"
                    )
            if iteration_index + 1 < args.iterations:
                lines.append("")
                time.sleep(args.interval)

    _print_lines(*lines)
    return 0


def handle_init(args: argparse.Namespace) -> int:
    """Handle ``foreman init``."""

    roles_dir = default_roles_dir()
    workflows_dir = default_workflows_dir()
    repo_path = Path(args.repo_path).expanduser().resolve()
    try:
        roles = load_roles(roles_dir)
        workflows = load_workflows(workflows_dir, available_role_ids=set(roles))
        spec_reference, _ = resolve_spec_path(repo_path, args.spec)
    except (RoleLoadError, WorkflowLoadError, ScaffoldError) as exc:
        print(f"Failed to initialize project: {exc}", file=sys.stderr)
        return 1

    with ForemanStore(args.db) as store:
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

    if not args.db:
        _print_lines(
            "Projects",
            "No projects are tracked yet.",
            CLI_SHELL_NOTE,
            STORE_OPTION_NOTE,
            STORE_FOLLOWUP_NOTE,
        )
        return 0

    with ForemanStore(args.db) as store:
        store.initialize()
        projects = store.list_projects()

        lines = ["Projects", f"Database: {store.db_path}"]
        if not projects:
            lines.extend(
                [
                    "No projects are tracked yet.",
                    "Use `foreman init --db PATH` to register a project, or seed the store through the Python API in the meantime.",
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

    if not args.db:
        _print_lines(
            "Status",
            "No active projects or sprints.",
            CLI_SHELL_NOTE,
            STORE_OPTION_NOTE,
            STORE_FOLLOWUP_NOTE,
        )
        return 0

    with ForemanStore(args.db) as store:
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


def handle_stub(args: argparse.Namespace) -> int:
    """Handle commands whose wiring exists before their implementation."""

    _print_lines(
        f"foreman {args.command_path} is not implemented yet.",
        "This CLI shell defines the canonical command surface from the product spec.",
        CLI_SHELL_NOTE,
    )
    return 0


def handle_dashboard(args: argparse.Namespace) -> int:
    """Handle ``foreman dashboard``."""

    try:
        run_dashboard(
            db_path=args.db,
            host=args.host,
            port=args.port,
        )
    except OSError as exc:
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
        required=True,
        help_text="Path to the SQLite store to initialize or update.",
    )
    init_parser.add_argument(
        "--workflow",
        default=None,
        help="Workflow identifier to assign to the project. Defaults to `development` for new projects.",
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
    _set_handler(project_parser, handle_stub, "project")

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
    _set_handler(sprint_add, handle_stub, "sprint add")

    sprint_activate = sprint_commands.add_parser(
        "activate",
        help="Activate a sprint.",
    )
    sprint_activate.add_argument("sprint_id", help="Sprint identifier.")
    _set_handler(sprint_activate, handle_stub, "sprint activate")

    sprint_list = sprint_commands.add_parser("list", help="List project sprints.")
    sprint_list.add_argument("project_id", help="Project identifier.")
    _set_handler(sprint_list, handle_stub, "sprint list")

    sprint_complete = sprint_commands.add_parser(
        "complete",
        help="Complete a sprint.",
    )
    sprint_complete.add_argument("sprint_id", help="Sprint identifier.")
    _set_handler(sprint_complete, handle_stub, "sprint complete")

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
    task_add.add_argument("--type", default="feature", help="Task type.")
    task_add.add_argument("--criteria", required=True, help="Acceptance criteria.")
    _set_handler(task_add, handle_stub, "task add")

    task_list = task_commands.add_parser("list", help="List project tasks.")
    task_list.add_argument("project_id", help="Project identifier.")
    _set_handler(task_list, handle_stub, "task list")

    task_block = task_commands.add_parser("block", help="Block a task.")
    task_block.add_argument("task_id", help="Task identifier.")
    task_block.add_argument("--reason", required=True, help="Blocking reason.")
    _set_handler(task_block, handle_stub, "task block")

    task_unblock = task_commands.add_parser("unblock", help="Unblock a task.")
    task_unblock.add_argument("task_id", help="Task identifier.")
    _set_handler(task_unblock, handle_stub, "task unblock")

    task_cancel = task_commands.add_parser("cancel", help="Cancel a task.")
    task_cancel.add_argument("task_id", help="Task identifier.")
    _set_handler(task_cancel, handle_stub, "task cancel")

    run_parser = subparsers.add_parser("run", help="Run Foreman against a project.")
    run_parser.add_argument("project_id", help="Project identifier.")
    run_parser.add_argument("--task", help="Single task identifier to run.")
    _set_handler(run_parser, handle_stub, "run")

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
        required=True,
        help_text="Path to the SQLite store containing the project board state.",
    )
    _set_handler(board_parser, handle_board, "board")

    watch_parser = subparsers.add_parser("watch", help="Tail project or run events.")
    watch_parser.add_argument("project_id", nargs="?", help="Project identifier.")
    watch_parser.add_argument("--run", help="Run identifier.")
    watch_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum number of recent events to show per snapshot.",
    )
    watch_parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds to wait between snapshots when polling.",
    )
    watch_parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of snapshots to render before exiting.",
    )
    _add_db_option(
        watch_parser,
        required=True,
        help_text="Path to the SQLite store containing project or run activity.",
    )
    _set_handler(watch_parser, handle_watch, "watch")

    cost_parser = subparsers.add_parser("cost", help="Show project cost totals.")
    cost_parser.add_argument("project_id", help="Project identifier.")
    cost_parser.add_argument("--sprint", help="Sprint identifier.")
    _add_db_option(
        cost_parser,
        required=True,
        help_text="Path to the SQLite store containing project run totals.",
    )
    _set_handler(cost_parser, handle_cost, "cost")

    history_parser = subparsers.add_parser(
        "history",
        help="Show run and event history for a task.",
    )
    history_parser.add_argument("task_id", help="Task identifier.")
    _add_db_option(
        history_parser,
        required=True,
        help_text="Path to the SQLite store containing task history.",
    )
    _set_handler(history_parser, handle_history, "history")

    approve_parser = subparsers.add_parser("approve", help="Approve a paused task.")
    approve_parser.add_argument("task_id", help="Task identifier.")
    approve_parser.add_argument("--note", help="Optional approval note.")
    _add_db_option(
        approve_parser,
        required=True,
        help_text="Path to the SQLite store containing the paused task.",
    )
    _set_handler(approve_parser, handle_approve, "approve")

    deny_parser = subparsers.add_parser("deny", help="Deny a paused task.")
    deny_parser.add_argument("task_id", help="Task identifier.")
    deny_parser.add_argument("--note", help="Optional denial note.")
    _add_db_option(
        deny_parser,
        required=True,
        help_text="Path to the SQLite store containing the paused task.",
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
    _set_handler(config_parser, handle_stub, "config")

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Start the web dashboard.",
    )
    _add_db_option(
        dashboard_parser,
        required=True,
        help_text="Path to the SQLite store for dashboard data.",
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
    with ForemanStore(args.db) as store:
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
