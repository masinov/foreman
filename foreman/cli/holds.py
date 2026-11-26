"""``foreman pause``, ``resume``, ``block`` and ``unblock`` (ADR-0043).

A user's holds on work. Pause and Resume act on a task (``--task``), on
every unfinished task of a sprint (``--sprint``) or on the whole workspace
(``--all``); ``--now`` makes a Pause a Stop, which cuts the running step.
Block and Unblock act on a sprint or the workspace; a task's own Block is
``foreman task block``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import Any

from ..mutations import MutationError, Mutations
from ..store import ForemanStore
from .common import (
    DB_OPTION_NOTE,
    add_db_option,
    cli_mutations,
    print_lines,
    resolve_db_path_or_print,
    resolve_project_or_print,
    resolve_sprint_or_print,
    resolve_task_or_print,
    set_handler,
)


def _target(
    store: ForemanStore, args: argparse.Namespace, *, tasks: bool
) -> tuple[str, Any] | None:
    """What the command names: ``("all", None)``, ``("sprint", s)`` or ``("task", t)``."""

    chosen = [name for name in ("task", "sprint", "all") if getattr(args, name, None)]
    if len(chosen) != 1:
        options = "--task, --sprint or --all" if tasks else "--sprint or --all"
        print(f"Name one of {options}.", file=sys.stderr)
        return None
    if args.all:
        return ("all", None)
    if not args.project_id:
        print("Name the project.", file=sys.stderr)
        return None
    project = resolve_project_or_print(store, args.project_id)
    if project is None:
        return None
    if getattr(args, "task", None):
        task = resolve_task_or_print(store, args.task, project_id=project.id)
        if task is None:
            return None
        if task.project_id != project.id:
            print(f"Task {args.task} is not in project {project.id}.", file=sys.stderr)
            return None
        return ("task", task)
    sprint = resolve_sprint_or_print(store, args.sprint)
    if sprint is None:
        return None
    if sprint.project_id != project.id:
        print(f"Sprint {args.sprint} is not in project {project.id}.", file=sys.stderr)
        return None
    return ("sprint", sprint)


def _run(
    args: argparse.Namespace,
    *,
    tasks: bool,
    act: Callable[[Mutations, str, Any], list[str]],
) -> int:
    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        target = _target(store, args, tasks=tasks)
        if target is None:
            return 1
        scope, record = target
        try:
            lines = act(cli_mutations(store), scope, record)
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    print_lines(*lines)
    return 0


def _keys(keys: list[str]) -> str:
    return ", ".join(keys) if keys else "none"


def handle_pause(args: argparse.Namespace) -> int:
    """Handle ``foreman pause``."""

    mode = "now" if args.now else "finish_step"
    verb = "Stopped" if args.now else "Paused"

    def act(mutations: Mutations, scope: str, record: Any) -> list[str]:
        if scope == "task":
            task = mutations.pause_task(record, mode=mode)
            keys = [task.task_key or task.id]
        elif scope == "sprint":
            keys = mutations.pause_sprint(record, mode=mode).task_keys
        else:
            keys = mutations.pause_all(mode=mode).task_keys
        tail = (
            "The running step is cut now and runs again on resume."
            if args.now
            else "A running step finishes first; nothing after it starts until resumed."
        )
        return [f"{verb}: {_keys(keys)}", tail]

    return _run(args, tasks=True, act=act)


def handle_resume(args: argparse.Namespace) -> int:
    """Handle ``foreman resume``."""

    def act(mutations: Mutations, scope: str, record: Any) -> list[str]:
        if scope == "task":
            task = mutations.resume_task(record)
            keys = [task.task_key or task.id]
        elif scope == "sprint":
            keys = mutations.resume_sprint(record).task_keys
        else:
            keys = mutations.resume_all().task_keys
        return [f"Resumed: {_keys(keys)}"]

    return _run(args, tasks=True, act=act)


def handle_block(args: argparse.Namespace) -> int:
    """Handle ``foreman block``."""

    def act(mutations: Mutations, scope: str, record: Any) -> list[str]:
        if scope == "sprint":
            mutations.block_sprint(record, args.reason)
            return [f"Blocked sprint {record.id}: {args.reason.strip()}"]
        mutations.block_all(args.reason)
        return [f"Blocked the workspace: {args.reason.strip()}"]

    return _run(args, tasks=False, act=act)


def handle_unblock(args: argparse.Namespace) -> int:
    """Handle ``foreman unblock``."""

    def act(mutations: Mutations, scope: str, record: Any) -> list[str]:
        if scope == "sprint":
            mutations.unblock_sprint(record)
            return [f"Unblocked sprint {record.id}. Tasks paused one by one stay paused."]
        mutations.unblock_all()
        return ["Unblocked the workspace. Pauses and sprint blocks stay."]

    return _run(args, tasks=False, act=act)


def _add_target(parser: argparse.ArgumentParser, *, tasks: bool) -> None:
    parser.add_argument(
        "project_id", nargs="?", help="Project identifier (not needed with --all)."
    )
    if tasks:
        parser.add_argument("--task", help="A task id or key (FOR-56).")
    parser.add_argument("--sprint", help="A sprint id.")
    parser.add_argument("--all", action="store_true", help="The whole workspace.")
    add_db_option(
        parser,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )


def register_holds(subparsers: argparse._SubParsersAction) -> None:
    """Add ``foreman pause``, ``resume``, ``block`` and ``unblock`` to the parser."""

    pause = subparsers.add_parser(
        "pause",
        help=(
            "Pause work: a running step finishes, then nothing after it starts. "
            "--now stops it: the step is cut."
        ),
    )
    _add_target(pause, tasks=True)
    pause.add_argument(
        "--now",
        action="store_true",
        help="Stop: cut the running step now; it runs again on resume.",
    )
    set_handler(pause, handle_pause, "pause")

    resume = subparsers.add_parser(
        "resume", help="Lift pauses on a task, a sprint's tasks, or every task. Blocks stay."
    )
    _add_target(resume, tasks=True)
    set_handler(resume, handle_resume, "resume")

    block = subparsers.add_parser(
        "block",
        help=(
            "Block a sprint or the workspace: nothing under it runs until unblocked. "
            "A task: `foreman task block`."
        ),
    )
    _add_target(block, tasks=False)
    block.add_argument("--reason", required=True, help="Why; shown wherever it holds work.")
    set_handler(block, handle_block, "block")

    unblock = subparsers.add_parser(
        "unblock", help="Lift the block on a sprint or the workspace."
    )
    _add_target(unblock, tasks=False)
    set_handler(unblock, handle_unblock, "unblock")
