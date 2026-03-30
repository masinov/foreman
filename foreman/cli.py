"""Command-line interface for the Foreman package."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Callable, Sequence

from . import __version__
from .models import Project, utc_now_text
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
    "SQLite-backed inspection is available now via `--db PATH` for `projects` and `status`."
)
STORE_FOLLOWUP_NOTE = (
    "Project creation is available via `foreman init --db PATH`; richer workflow commands land in later slices."
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
    _set_handler(board_parser, handle_stub, "board")

    watch_parser = subparsers.add_parser("watch", help="Tail project or run events.")
    watch_parser.add_argument("project_id", nargs="?", help="Project identifier.")
    watch_parser.add_argument("--run", help="Run identifier.")
    _set_handler(watch_parser, handle_stub, "watch")

    cost_parser = subparsers.add_parser("cost", help="Show project cost totals.")
    cost_parser.add_argument("project_id", help="Project identifier.")
    cost_parser.add_argument("--sprint", help="Sprint identifier.")
    _set_handler(cost_parser, handle_stub, "cost")

    history_parser = subparsers.add_parser(
        "history",
        help="Show run and event history for a task.",
    )
    history_parser.add_argument("task_id", help="Task identifier.")
    _set_handler(history_parser, handle_stub, "history")

    approve_parser = subparsers.add_parser("approve", help="Approve a paused task.")
    approve_parser.add_argument("task_id", help="Task identifier.")
    approve_parser.add_argument("--note", help="Optional approval note.")
    _set_handler(approve_parser, handle_stub, "approve")

    deny_parser = subparsers.add_parser("deny", help="Deny a paused task.")
    deny_parser.add_argument("task_id", help="Task identifier.")
    deny_parser.add_argument("--note", help="Optional denial note.")
    _set_handler(deny_parser, handle_stub, "deny")

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
