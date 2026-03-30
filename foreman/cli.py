"""Command-line interface for the Foreman package."""

from __future__ import annotations

import argparse
from typing import Callable, Sequence

from . import __version__
from .store import ForemanStore

CLI_DESCRIPTION = (
    "Foreman is an autonomous development engine for spec-driven software delivery."
)
CLI_SHELL_NOTE = "This command surface is still incomplete while Foreman is under active development."
STORE_OPTION_NOTE = (
    "SQLite-backed inspection is available now via `--db PATH` for `projects` and `status`."
)
STORE_FOLLOWUP_NOTE = (
    "Project creation and richer workflow commands land in later slices."
)

Handler = Callable[[argparse.Namespace], int]


def _print_lines(*lines: str) -> None:
    for line in lines:
        print(line)


def _add_db_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db",
        help="Path to the SQLite store to inspect.",
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
    """Handle ``foreman init`` while scaffold generation is still pending."""

    _print_lines(
        "foreman init is wired but not implemented yet.",
        f"Target repo: {args.repo_path}",
        f"Project name: {args.name}",
        f"Spec path: {args.spec}",
        f"Workflow: {args.workflow}",
        "Planned follow-up: repo scaffold generation after the loader foundations land.",
    )
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
                    "Use `foreman init` once scaffold generation lands, or seed the store through the Python API in the meantime.",
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
    init_parser.add_argument(
        "--workflow",
        default="development",
        help="Workflow identifier to assign to the project.",
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
    _set_handler(roles_parser, handle_stub, "roles")

    workflows_parser = subparsers.add_parser(
        "workflows",
        help="List available workflows.",
    )
    _set_handler(workflows_parser, handle_stub, "workflows")

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
        import sys

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
