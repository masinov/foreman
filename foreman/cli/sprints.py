"""Sprints: add, activate, list, complete."""

from __future__ import annotations

import argparse
import sys

from ..models import Sprint
from ..mutations import MutationError
from ..store import ForemanStore

from .common import (
    DB_OPTION_NOTE,
    add_db_option,
    add_json_option,
    allocate_entity_id,
    cli_mutations,
    format_run_totals,
    format_task_counts,
    next_order_index,
    print_json,
    print_lines,
    resolve_db_path_or_print,
    resolve_project_or_print,
    resolve_sprint_or_print,
    set_handler,
)


def handle_sprint_add(args: argparse.Namespace) -> int:
    """Handle ``foreman sprint add``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        sprints = store.list_sprints(project.id)
        sprint = Sprint(
            id=allocate_entity_id("sprint", args.title, exists=store.get_sprint),
            project_id=project.id,
            title=args.title,
            goal=args.goal,
            status="planned",
            order_index=next_order_index([item.order_index for item in sprints]),
        )
        store.save_sprint(sprint)
        db_path = store.db_path

    print_lines(
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

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        sprint = resolve_sprint_or_print(store, args.sprint_id)
        if sprint is None:
            return 1
        try:
            cli_mutations(store).transition_sprint(sprint, "active")
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path
        project = store.get_project(sprint.project_id)

    print_lines(
        "Activated sprint",
        f"Database: {db_path}",
        f"Project: {sprint.project_id} | {project.name if project is not None else 'unknown'}",
        f"Sprint: {sprint.id} | {sprint.title}",
        f"Status: {sprint.status}",
    )
    return 0


def handle_sprint_list(args: argparse.Namespace) -> int:
    """Handle ``foreman sprint list``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        sprints = store.list_sprints(project.id)
        db_path = store.db_path
        if getattr(args, "as_json", False):
            print_json(
                {
                    "database": str(db_path),
                    "project_id": project.id,
                    "sprints": [
                        {
                            "id": sprint.id,
                            "title": sprint.title,
                            "goal": sprint.goal,
                            "status": sprint.status,
                            "order_index": sprint.order_index,
                            "started_at": sprint.started_at,
                            "completed_at": sprint.completed_at,
                            "task_counts": store.task_counts(sprint_id=sprint.id),
                            "run_totals": store.run_totals(
                                project_id=project.id, sprint_id=sprint.id
                            ),
                        }
                        for sprint in sprints
                    ],
                }
            )
            return 0

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
                    f"goal={sprint.goal or 'n/a'} | {format_task_counts(counts)} | {format_run_totals(totals)}"
                )

    print_lines(*lines)
    return 0


def handle_sprint_complete(args: argparse.Namespace) -> int:
    """Handle ``foreman sprint complete``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        sprint = resolve_sprint_or_print(store, args.sprint_id)
        if sprint is None:
            return 1
        try:
            cli_mutations(store).transition_sprint(sprint, "completed")
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        project = store.get_project(sprint.project_id)
        db_path = store.db_path

    print_lines(
        "Completed sprint",
        f"Database: {db_path}",
        f"Project: {sprint.project_id} | {project.name if project is not None else 'unknown'}",
        f"Sprint: {sprint.id} | {sprint.title}",
        f"Status: {sprint.status}",
        f"Completed at: {sprint.completed_at}",
    )
    return 0


def register_sprint(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman sprint` to the parser."""

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
    add_db_option(
        sprint_add,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(sprint_add, handle_sprint_add, "sprint add")

    sprint_activate = sprint_commands.add_parser(
        "activate",
        help="Activate a sprint.",
    )
    sprint_activate.add_argument("sprint_id", help="Sprint identifier.")
    add_db_option(
        sprint_activate,
        help_text=f"Path to the SQLite store containing the sprint. {DB_OPTION_NOTE}",
    )
    set_handler(sprint_activate, handle_sprint_activate, "sprint activate")

    sprint_list = sprint_commands.add_parser("list", help="List project sprints.")
    sprint_list.add_argument("project_id", help="Project identifier.")
    add_db_option(
        sprint_list,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    add_json_option(sprint_list)
    set_handler(sprint_list, handle_sprint_list, "sprint list")

    sprint_complete = sprint_commands.add_parser(
        "complete",
        help="Complete a sprint.",
    )
    sprint_complete.add_argument("sprint_id", help="Sprint identifier.")
    add_db_option(
        sprint_complete,
        help_text=f"Path to the SQLite store containing the sprint. {DB_OPTION_NOTE}",
    )
    set_handler(sprint_complete, handle_sprint_complete, "sprint complete")

