"""The backlog: list, add, accept, decline, plan, unplan (ADR-0021)."""

from __future__ import annotations

import argparse
import sys

from ..backlog import BACKLOG_PAGE_LIMIT, BacklogQueryError, read_backlog
from ..models import BACKLOG_STATES, TASK_COMPLEXITIES, TASK_TYPES
from ..mutations import MutationError
from ..store import ForemanStore
from .common import (
    DB_OPTION_NOTE,
    add_db_option,
    add_json_option,
    cli_mutations,
    print_json,
    print_lines,
    resolve_db_path_or_print,
    resolve_project_or_print,
    resolve_task_or_print,
    set_handler,
    truncate_text,
)
from .tasks import handle_task_accept

#: Section headings, in the order the list shows them (the design's words).
_SECTIONS: tuple[tuple[str, str], ...] = (
    ("filed", "Filed, not accepted"),
    ("accepted", "Accepted, not planned"),
    ("declined", "Declined"),
)


def _split_states(values: list[str]) -> list[str]:
    return [piece for value in values for piece in (p.strip() for p in value.split(",")) if piece]


def handle_backlog_list(args: argparse.Namespace) -> int:
    """Handle ``foreman backlog list``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        try:
            page = read_backlog(
                store,
                project,
                states=_split_states(args.status),
                query=args.query,
                limit=args.limit,
                offset=args.offset,
            )
        except BacklogQueryError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if args.as_json:
        print_json(page)
        return 0

    who = "a person" if page["triage"] == "human" else "Foreman"
    lines = [
        f"Backlog: {project.id} | {project.name}",
        f"Filed work is accepted by {who}. "
        f"Filed {page['counts']['filed']}, accepted {page['counts']['accepted']}, "
        f"declined {page['counts']['declined']}.",
    ]
    if not page["tasks"]:
        lines.append("Nothing matches." if page["total"] else "The backlog is empty.")
    for state, heading in _SECTIONS:
        entries = [task for task in page["tasks"] if task["state"] == state]
        if not entries:
            continue
        lines.append(f"{heading} ({page['counts'][state]})")
        for task in entries:
            lines.append(
                f"  {task['task_key'] or task['id']} | {task['task_type']} | "
                f"{truncate_text(task['title'])} | filed by {task['created_by']} | {task['id']}"
            )
    shown = len(page["tasks"])
    if page["total"] > args.offset + shown:
        lines.append(
            f"Showing {args.offset + 1}-{args.offset + shown} of {page['total']}; "
            f"use --offset {args.offset + shown} for more."
        )
    print_lines(*lines)
    return 0


def handle_backlog_add(args: argparse.Namespace) -> int:
    """Handle ``foreman backlog add``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        mutations = cli_mutations(store)
        try:
            filed = mutations.file_task(
                project,
                title=args.title,
                task_type=args.task_type,
                description=args.description,
                acceptance_criteria=args.criteria,
                priority=args.priority,
                complexity=args.complexity,
                created_by=mutations.actor or "human",
                accept=args.accept,
            )
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    task = filed.task
    state = "accepted, not planned" if task.status == "todo" else "filed, not accepted"
    print_lines(
        "Filed task into the backlog",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Task: {task.id} | {task.task_key} | {task.title}",
        f"Type: {task.task_type}",
        f"State: {state}",
        f"Triage: {filed.triage.value} ({filed.triage.source})",
    )
    return 0


def handle_backlog_decline(args: argparse.Namespace) -> int:
    """Handle ``foreman backlog decline``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        try:
            cli_mutations(store).decline_task(task, args.reason)
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Declined task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        "It stays in the backlog, marked declined. "
        "`foreman backlog list --status declined` shows it.",
    )
    return 0


def handle_backlog_plan(args: argparse.Namespace) -> int:
    """Handle ``foreman backlog plan``."""

    if bool(args.sprint_id) == bool(args.new_sprint):
        print("Name a sprint with --sprint, or a new one with --new-sprint.", file=sys.stderr)
        return 1
    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        tasks = []
        for task_id in args.task_ids:
            task = resolve_task_or_print(store, task_id)
            if task is None:
                return 1
            if task.project_id != project.id:
                print(f"Task {task_id} does not belong to project {project.id}.", file=sys.stderr)
                return 1
            tasks.append(task)
        sprint = None
        if args.sprint_id:
            sprint = store.get_sprint(args.sprint_id)
            if sprint is None or sprint.is_backlog:
                print(f"Unknown sprint: {args.sprint_id}", file=sys.stderr)
                return 1
        try:
            planned = cli_mutations(store).plan_tasks(
                tasks,
                sprint=sprint,
                new_sprint_title=args.new_sprint,
                new_sprint_goal=args.goal,
            )
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    created = " (new)" if planned.created_sprint else ""
    print_lines(
        f"Planned {len(planned.tasks)} task(s)",
        f"Database: {db_path}",
        f"Sprint: {planned.sprint.id} | {planned.sprint.title}{created} | "
        f"status={planned.sprint.status}",
        *(f"Task: {task.id} | {task.title}" for task in planned.tasks),
    )
    return 0


def handle_backlog_unplan(args: argparse.Namespace) -> int:
    """Handle ``foreman backlog unplan``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        from_sprint = task.sprint_id
        try:
            cli_mutations(store).unplan_task(task)
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Moved task back to the backlog",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"From sprint: {from_sprint}",
    )
    return 0


def register_backlog(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman backlog` to the parser."""

    backlog_parser = subparsers.add_parser(
        "backlog",
        help="Work that is filed or accepted and not yet planned into a sprint.",
    )
    commands = backlog_parser.add_subparsers(
        dest="backlog_command", metavar="backlog_command", required=True
    )
    project_db_help = f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}"
    task_db_help = f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}"

    backlog_list = commands.add_parser(
        "list", help="List the backlog: filed work first, then accepted work."
    )
    backlog_list.add_argument("project_id", help="Project identifier.")
    backlog_list.add_argument(
        "--status",
        action="append",
        default=[],
        metavar="STATE",
        help=(
            f"Only these states ({', '.join(BACKLOG_STATES)}); repeatable or "
            "comma-separated. Defaults to filed and accepted."
        ),
    )
    backlog_list.add_argument("--query", "-q", help="Match part of the title, key or id.")
    backlog_list.add_argument(
        "--limit", type=int, default=BACKLOG_PAGE_LIMIT, help="How many to show."
    )
    backlog_list.add_argument("--offset", type=int, default=0, help="How many to skip.")
    add_json_option(backlog_list)
    add_db_option(backlog_list, help_text=project_db_help)
    set_handler(backlog_list, handle_backlog_list, "backlog list")

    backlog_add = commands.add_parser(
        "add", help="File a task into the backlog. The triage policy decides if it is accepted."
    )
    backlog_add.add_argument("project_id", help="Project identifier.")
    backlog_add.add_argument("--title", required=True, help="Task title.")
    backlog_add.add_argument(
        "--type", dest="task_type", default="feature", choices=TASK_TYPES, help="Task type."
    )
    backlog_add.add_argument("--criteria", help="Acceptance criteria.")
    backlog_add.add_argument("--description", help="Task description.")
    backlog_add.add_argument("--priority", type=int, default=0, help="Priority (0 first).")
    backlog_add.add_argument("--complexity", choices=TASK_COMPLEXITIES, help="Complexity hint.")
    backlog_add.add_argument(
        "--accept",
        action="store_true",
        help="File it already accepted: you are the one deciding.",
    )
    add_db_option(backlog_add, help_text=project_db_help)
    set_handler(backlog_add, handle_backlog_add, "backlog add")

    backlog_accept = commands.add_parser(
        "accept", help="Accept a filed task. It stays in the backlog until planned."
    )
    backlog_accept.add_argument("task_id", help="Task identifier.")
    add_db_option(backlog_accept, help_text=task_db_help)
    set_handler(backlog_accept, handle_task_accept, "backlog accept")

    backlog_decline = commands.add_parser(
        "decline", help="Decline a filed task. It is kept, marked declined."
    )
    backlog_decline.add_argument("task_id", help="Task identifier.")
    backlog_decline.add_argument("--reason", help="Why it was declined.")
    add_db_option(backlog_decline, help_text=task_db_help)
    set_handler(backlog_decline, handle_backlog_decline, "backlog decline")

    backlog_plan = commands.add_parser(
        "plan", help="Plan accepted tasks into a planned or active sprint, or a new one."
    )
    backlog_plan.add_argument("project_id", help="Project identifier.")
    backlog_plan.add_argument("task_ids", nargs="+", metavar="TASK_ID", help="Tasks to plan.")
    target = backlog_plan.add_mutually_exclusive_group(required=True)
    target.add_argument("--sprint", dest="sprint_id", help="An existing planned or active sprint.")
    target.add_argument(
        "--new-sprint", dest="new_sprint", metavar="TITLE", help="Create a planned sprint."
    )
    backlog_plan.add_argument("--goal", help="Goal of the new sprint.")
    add_db_option(backlog_plan, help_text=project_db_help)
    set_handler(backlog_plan, handle_backlog_plan, "backlog plan")

    backlog_unplan = commands.add_parser(
        "unplan", help="Move a task that has not started from its sprint back to the backlog."
    )
    backlog_unplan.add_argument("task_id", help="Task identifier.")
    add_db_option(backlog_unplan, help_text=task_db_help)
    set_handler(backlog_unplan, handle_backlog_unplan, "backlog unplan")
