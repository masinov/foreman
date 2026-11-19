"""The per-task git worktrees Foreman owns."""

from __future__ import annotations

import argparse
import sys

from ..repo.worktrees import (
    WorktreeError,
    prune_project_worktrees,
    worktree_root,
)
from ..services import Services
from ..services.errors import InvalidRequestError
from ..store import ForemanStore
from .common import (
    DB_OPTION_NOTE,
    add_db_option,
    add_json_option,
    print_json,
    print_lines,
    resolve_db_path_or_print,
    resolve_project_or_print,
    set_handler,
)


def handle_worktree_list(args: argparse.Namespace) -> int:
    """Handle ``foreman worktree list``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        db_path = store.db_path
        try:
            listing = Services(store).worktrees.list_worktrees(project.id)
        except InvalidRequestError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.as_json:
        print_json(listing)
        return 0

    lines = [
        "Worktrees",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Root: {listing['root']}",
    ]
    if not listing["worktrees"]:
        lines.append("- none")
    for entry in listing["worktrees"]:
        parts = [entry["slug"], f"branch={entry['branch'] or 'detached'}"]
        if entry["is_integration"]:
            parts.append("role=integration")
        if entry["task_key"] is not None:
            parts.append(f"task={entry['task_key']}")
            parts.append(f"status={entry['task_status']}")
        if not entry["exists"]:
            parts.append("missing=true")
        lines.append(f"- {' | '.join(parts)}")
        lines.append(f"  {entry['path']}")
    print_lines(*lines)
    return 0

def handle_worktree_prune(args: argparse.Namespace) -> int:
    """Handle ``foreman worktree prune``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        db_path = store.db_path
        try:
            removed, kept = prune_project_worktrees(store, project)
        except WorktreeError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    lines = [
        "Pruned worktrees",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Root: {worktree_root(project)}",
        f"Removed: {len(removed)}",
    ]
    for entry in removed:
        lines.append(f"- {entry.slug} | {entry.path}")
    lines.append(f"Kept: {len(kept)}")
    for entry in kept:
        lines.append(f"- {entry.slug} | {entry.path}")
    print_lines(*lines)
    return 0


def register_worktree(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman worktree` to the parser."""

    worktree_parser = subparsers.add_parser(
        "worktree",
        help="Inspect and clean up the per-task git worktrees Foreman owns.",
    )
    worktree_commands = worktree_parser.add_subparsers(dest="worktree_command")
    worktree_parser.set_defaults(handler=None, command_path="worktree")

    worktree_list = worktree_commands.add_parser(
        "list",
        help="List the worktrees Foreman owns for a project.",
    )
    worktree_list.add_argument("project_id", help="Project identifier.")
    add_db_option(
        worktree_list,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    add_json_option(worktree_list)
    set_handler(worktree_list, handle_worktree_list, "worktree list")

    worktree_prune = worktree_commands.add_parser(
        "prune",
        help="Remove worktrees of done or cancelled tasks and dangling entries.",
    )
    worktree_prune.add_argument("project_id", help="Project identifier.")
    add_db_option(
        worktree_prune,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(worktree_prune, handle_worktree_prune, "worktree prune")

