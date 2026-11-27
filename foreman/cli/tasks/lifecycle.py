"""``foreman task accept``, ``block``, ``unblock``, ``done``, ``reopen`` and ``cancel``.
"""

from __future__ import annotations

import argparse
import sys

from ...domain.question import answer_words
from ...mutations import MutationError
from ...store import ForemanStore
from ..common import (
    format_step_visits,
    cli_mutations,
    print_lines,
    resolve_db_path_or_print,
    resolve_task_or_print,
)


def handle_task_block(args: argparse.Namespace) -> int:
    """Handle ``foreman task block``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        try:
            cli_mutations(store).block_task(task, args.reason)
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Blocked task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
        f"Reason: {task.blocked_reason}",
    )
    return 0


def handle_task_unblock(args: argparse.Namespace) -> int:
    """Handle ``foreman task unblock``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        try:
            cli_mutations(store).unblock_task(
                task, reset_visits=getattr(args, "reset_visits", False)
            )
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Unblocked task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
        (
            "Step visits reset: yes"
            if not task.step_visit_counts
            else f"Step visits kept: {format_step_visits(task.step_visit_counts)}"
        ),
    )
    return 0


def handle_task_answer(args: argparse.Namespace) -> int:
    """Handle ``foreman task answer``: answer the question an agent asked."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        try:
            result = cli_mutations(store).answer_question(
                task, option=args.option, text=args.text
            )
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        engine_resident = store.get_engine_lock(result.task.project_id) is not None
        db_path = store.db_path

    print_lines(
        "Answered task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Answer: {answer_words(result.answer)}",
        f"Answered by: {result.answer['answered_by']} at {result.answer['answered_at']}",
        f"Step: {result.step} runs again with the answer"
        + ("" if engine_resident else " when a worker runs (`foreman serve`)"),
    )
    return 0


def handle_task_accept(args: argparse.Namespace) -> int:
    """Handle ``foreman task accept``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        try:
            cli_mutations(store).accept_task(task)
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Accepted task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
    )
    return 0


def handle_task_done(args: argparse.Namespace) -> int:
    """Handle ``foreman task done``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    reason = (args.reason or "").strip()
    if not reason:
        print("Say why the task is done with --reason.", file=sys.stderr)
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        try:
            cli_mutations(store).complete_task(task, reason)
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Marked task done",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
        f"Reason: {reason}",
    )
    return 0


def handle_task_reopen(args: argparse.Namespace) -> int:
    """Handle ``foreman task reopen``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        try:
            cli_mutations(store).reopen_task(task)
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Reopened task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
    )
    return 0


def handle_task_cancel(args: argparse.Namespace) -> int:
    """Handle ``foreman task cancel``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        try:
            removal = cli_mutations(store).cancel_task(task)
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        removed_worktree = removal.removed_worktree
        if removal.warning is not None:
            print(removal.warning, file=sys.stderr)
        db_path = store.db_path

    print_lines(
        "Cancelled task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
        f"Completed at: {task.completed_at}",
        *([f"Removed worktree: {removed_worktree}"] if removed_worktree else []),
    )
    return 0
