"""``foreman task``: the subcommands and their arguments.
"""

from __future__ import annotations

import argparse

from ...domain.models import TASK_TYPES
from ..common import (
    DB_OPTION_NOTE,
    add_db_option,
    add_json_option,
    set_handler,
)
from .changes import handle_task_add, handle_task_edit, handle_task_override
from .lifecycle import (
    handle_task_accept,
    handle_task_block,
    handle_task_cancel,
    handle_task_done,
    handle_task_reopen,
    handle_task_unblock,
)
from .reads import handle_task_list, handle_task_show


def register_task(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman task` to the parser."""

    task_parser = subparsers.add_parser(
        "task",
        help="Manage tasks.",
    )
    task_commands = task_parser.add_subparsers(
        dest="task_command",
        metavar="task_command",
        required=True,
    )
    _register_add(task_commands)
    _register_override(task_commands)
    _register_list(task_commands)
    _register_show(task_commands)
    _register_block(task_commands)
    _register_unblock(task_commands)
    _register_accept(task_commands)
    _register_done(task_commands)
    _register_reopen(task_commands)
    _register_edit(task_commands)
    _register_cancel(task_commands)


def _register_add(task_commands: argparse._SubParsersAction) -> None:
    """`foreman task add`."""

    task_add = task_commands.add_parser("add", help="Create a task.")
    task_add.add_argument("project_id", help="Project identifier.")
    task_add.add_argument("--title", required=True, help="Task title.")
    task_add.add_argument("--type", dest="task_type", default="feature", help="Task type.")
    task_add.add_argument("--criteria", required=True, help="Acceptance criteria.")
    task_add.add_argument("--description", help="Task description.")
    task_add.add_argument(
        "--rests-on",
        action="append",
        metavar="PATH[#HEADING]",
        help="A document of the repository the task rests on, optionally with a "
        "heading: `docs/specs/engine-design-v3.md#6.3`. It must exist on the default "
        "branch; Foreman records that branch's commit with it. Repeat for several.",
    )
    task_add.add_argument(
        "--sprint",
        dest="sprint_id",
        metavar="SPRINT_ID",
        help="Target sprint id. Defaults to the active sprint, else the first planned sprint.",
    )
    task_add.add_argument(
        "--depends-on",
        dest="depends_on",
        metavar="TASK_IDS",
        help="Comma-separated task ids this task depends on (must exist in the same project).",
    )
    add_db_option(
        task_add,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(task_add, handle_task_add, "task add")


def _register_override(task_commands: argparse._SubParsersAction) -> None:
    """`foreman task override`."""

    task_override = task_commands.add_parser(
        "override",
        help="Set per-task executor model overrides for workflow steps.",
    )
    task_override.add_argument("task_id", help="Task id or key (FOR-56).")
    task_override.add_argument(
        "--step",
        dest="step_models",
        action="append",
        metavar="STEP=MODEL",
        default=[],
        help="Pin a model for one workflow step (repeatable), e.g. --step develop=MiniMax-M2.",
    )
    task_override.add_argument(
        "--ladder-start",
        dest="ladder_start",
        metavar="MODEL",
        help=(
            "Start each step on this one of its role's models (cheapest first); a "
            "role that does not list it starts on its first."
        ),
    )
    task_override.add_argument(
        "--gate",
        dest="gate_policies",
        action="append",
        metavar="POLICY=auto|human",
        default=[],
        help=(
            "Override a gate policy for this task (repeatable), e.g. "
            "--gate merge_approval=human. An empty value removes the override."
        ),
    )
    task_override.add_argument(
        "--triage",
        metavar="auto|human",
        help=(
            "Override the triage policy for this task. An empty value removes "
            "the override."
        ),
    )
    task_override.add_argument(
        "--notification",
        metavar="none|attention|all",
        help=(
            "Override the notification policy for this task. An empty value "
            "removes the override."
        ),
    )
    task_override.add_argument(
        "--clear",
        action="store_true",
        help="Reset all executor overrides for this task to empty.",
    )
    add_db_option(
        task_override,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_override, handle_task_override, "task override")


def _register_list(task_commands: argparse._SubParsersAction) -> None:
    """`foreman task list`."""

    task_list = task_commands.add_parser("list", help="List project tasks.")
    task_list.add_argument("project_id", help="Project identifier.")
    task_list.add_argument("--sprint", metavar="SPRINT_ID", help="Filter to a specific sprint.")
    add_db_option(
        task_list,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    add_json_option(task_list)
    set_handler(task_list, handle_task_list, "task list")


def _register_show(task_commands: argparse._SubParsersAction) -> None:
    """`foreman task show`."""

    task_show = task_commands.add_parser("show", help="Show one task with recent runs and events.")
    task_show.add_argument("task_id", help="Task id or key (FOR-56).")
    task_show.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of recent runs to include.",
    )
    task_show.add_argument(
        "--events",
        type=int,
        default=8,
        help="Number of recent events to include.",
    )
    add_db_option(
        task_show,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    add_json_option(task_show)
    set_handler(task_show, handle_task_show, "task show")


def _register_block(task_commands: argparse._SubParsersAction) -> None:
    """`foreman task block`."""

    task_block = task_commands.add_parser("block", help="Block a task.")
    task_block.add_argument("task_id", help="Task id or key (FOR-56).")
    task_block.add_argument("--reason", required=True, help="Blocking reason.")
    add_db_option(
        task_block,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_block, handle_task_block, "task block")


def _register_unblock(task_commands: argparse._SubParsersAction) -> None:
    """`foreman task unblock`."""

    task_unblock = task_commands.add_parser("unblock", help="Unblock a task.")
    task_unblock.add_argument("task_id", help="Task id or key (FOR-56).")
    add_db_option(
        task_unblock,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_unblock, handle_task_unblock, "task unblock")


def _register_accept(task_commands: argparse._SubParsersAction) -> None:
    """`foreman task accept`."""

    task_accept = task_commands.add_parser(
        "accept",
        help="Accept a filed task. In the backlog it then waits to be planned into a sprint.",
    )
    task_accept.add_argument("task_id", help="Task id or key (FOR-56).")
    add_db_option(
        task_accept,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_accept, handle_task_accept, "task accept")


def _register_done(task_commands: argparse._SubParsersAction) -> None:
    """`foreman task done`."""

    task_done = task_commands.add_parser(
        "done",
        help="Mark a task done by hand, for work finished outside the engine.",
    )
    task_done.add_argument("task_id", help="Task id or key (FOR-56).")
    task_done.add_argument("--reason", required=True, help="Why it is done; recorded on the task.")
    add_db_option(
        task_done,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_done, handle_task_done, "task done")


def _register_reopen(task_commands: argparse._SubParsersAction) -> None:
    """`foreman task reopen`."""

    task_reopen = task_commands.add_parser(
        "reopen",
        help="Return a done or cancelled task to the queue; its workflow starts over.",
    )
    task_reopen.add_argument("task_id", help="Task id or key (FOR-56).")
    add_db_option(
        task_reopen,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_reopen, handle_task_reopen, "task reopen")


def _register_edit(task_commands: argparse._SubParsersAction) -> None:
    """`foreman task edit`."""

    task_edit = task_commands.add_parser(
        "edit",
        help="Change a task's title, type, texts, priority or what it waits for.",
    )
    task_edit.add_argument("task_id", help="Task id or key (FOR-56).")
    task_edit.add_argument("--title", help="New title.")
    task_edit.add_argument(
        "--type", dest="task_type", choices=list(TASK_TYPES), help="New task type."
    )
    task_edit.add_argument(
        "--description", help="New description; an empty text clears it."
    )
    task_edit.add_argument(
        "--description-file",
        metavar="PATH",
        help="Read the new description from a file; `-` reads standard input.",
    )
    task_edit.add_argument(
        "--criteria", help="New acceptance criteria; an empty text clears them."
    )
    task_edit.add_argument(
        "--criteria-file",
        metavar="PATH",
        help="Read the new acceptance criteria from a file; `-` reads standard input.",
    )
    task_edit.add_argument(
        "--rests-on",
        action="append",
        metavar="PATH[#HEADING]",
        help="A document of the repository the task rests on, optionally with a "
        "heading: `docs/specs/engine-design-v3.md#6.3`. It must exist on the default "
        "branch; Foreman records that branch's commit with it. Repeat for several; the list replaces"
        " the task's documents (those already named keep their commit).",
    )
    task_edit.add_argument(
        "--no-rests-on",
        action="store_true",
        help="Name no documents: clear the task's list.",
    )
    task_edit.add_argument(
        "--edit",
        choices=["description", "criteria"],
        help="Edit one text in $VISUAL, else $EDITOR, else nano or vi. Needs a "
        "terminal. Closing without a change, or with the text emptied, changes nothing.",
    )
    task_edit.add_argument(
        "--priority", type=int, help="Lower runs first; 0 is the default."
    )
    task_edit.add_argument(
        "--depends-on",
        action="append",
        metavar="TASK_ID",
        help="A task this one waits for. Repeat for several; the list replaces "
        "what it waited for. Only before the task starts.",
    )
    task_edit.add_argument(
        "--no-dependencies",
        action="store_true",
        help="Make the task wait for nothing.",
    )
    add_db_option(
        task_edit,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_edit, handle_task_edit, "task edit")


def _register_cancel(task_commands: argparse._SubParsersAction) -> None:
    """`foreman task cancel`."""

    task_cancel = task_commands.add_parser("cancel", help="Cancel a task.")
    task_cancel.add_argument("task_id", help="Task id or key (FOR-56).")
    add_db_option(
        task_cancel,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_cancel, handle_task_cancel, "task cancel")
