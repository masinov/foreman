"""The per-task git worktrees Foreman owns."""

from __future__ import annotations

import argparse
import sys

from ..store import ForemanStore
from ..worktrees import (
    WorktreeError,
    WorktreeManager,
    prune_project_worktrees,
    worktree_root,
)

from .common import (
    DB_OPTION_NOTE,
    add_db_option,
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
        tasks_by_path = {
            task.worktree_path: task
            for task in store.list_tasks(project_id=project.id)
            if task.worktree_path
        }
        try:
            entries = WorktreeManager(project).list()
        except WorktreeError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    lines = [
        "Worktrees",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Root: {worktree_root(project)}",
    ]
    if not entries:
        lines.append("- none")
    else:
        for entry in entries:
            parts = [entry.slug, f"branch={entry.branch or 'detached'}"]
            if entry.is_integration:
                parts.append("role=integration")
            task = tasks_by_path.get(str(entry.path))
            if task is not None:
                parts.append(f"task={task.task_key or task.id}")
                parts.append(f"status={task.status}")
            if not entry.exists:
                parts.append("missing=true")
            lines.append(f"- {' | '.join(parts)}")
            lines.append(f"  {entry.path}")
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
        # Forget the paths that no longer exist so `task show` stops
        # advertising a directory an operator cannot open.
        removed_paths = {str(entry.path) for entry in removed}
        for task in store.list_tasks(project_id=project.id):
            if task.worktree_path and task.worktree_path in removed_paths:
                task.worktree_path = None
                store.save_task(task)

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

