"""The `foreman` command: the parser and the entry point."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import Sequence

from .. import __version__
from ..errors import ForemanError
from ..proposals import manager_session
from . import (
    backlog,
    catalog,
    db,
    engine,
    gates,
    monitor,
    notify,
    projects,
    proposals,
    sprints,
    tasks,
    tokens,
    worktree,
)

#: What a manager session may run (ADR-0022): commands that only read, and
#: making a proposal. Everything else changes project state, and a manager
#: changes it only by proposing. New commands are refused until listed here.
MANAGER_SESSION_COMMANDS: frozenset[str] = frozenset(
    {
        "board",
        "cost",
        "history",
        "status",
        "transcript",
        "watch",
        "projects",
        "roles",
        "workflows",
        "task show",
        "task list",
        "sprint list",
        "backlog list",
        "worktree list",
        "notify list",
        "notify deliveries",
        "engine status",
        "token list",
        "db version",
        "proposal create",
        "proposal list",
        "proposal show",
    }
)

MANAGER_REFUSAL = (
    "Foreman's manager cannot change project state itself. Propose the change: "
    "`foreman proposal create <project> --json <file or ->`; a person confirms it."
)

CLI_DESCRIPTION = (
    "Foreman is an autonomous development engine for spec-driven software delivery."
)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI argument parser.

    Each command registers itself; the order here is the order of `--help`.
    """

    parser = argparse.ArgumentParser(prog="foreman", description=CLI_DESCRIPTION)
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    projects.register_init(subparsers)
    projects.register_projects(subparsers)
    projects.register_project(subparsers)
    sprints.register_sprint(subparsers)
    tasks.register_task(subparsers)
    backlog.register_backlog(subparsers)
    proposals.register_proposal(subparsers)
    worktree.register_worktree(subparsers)
    tokens.register_token(subparsers)
    notify.register_notify(subparsers)
    engine.register_run(subparsers)
    engine.register_serve(subparsers)
    engine.register_engine(subparsers)
    monitor.register_status(subparsers)
    monitor.register_board(subparsers)
    monitor.register_watch(subparsers)
    monitor.register_cost(subparsers)
    monitor.register_history(subparsers)
    monitor.register_transcript(subparsers)
    gates.register_approve(subparsers)
    gates.register_deny(subparsers)
    gates.register_waive_merge(subparsers)
    gates.register_revoke_waiver(subparsers)
    catalog.register_roles(subparsers)
    catalog.register_workflows(subparsers)
    projects.register_config(subparsers)
    db.register_db(subparsers)
    engine.register_dashboard(subparsers)

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

    command_path = getattr(args, "command_path", None)
    if manager_session() is not None and command_path not in MANAGER_SESSION_COMMANDS:
        print(f"foreman {command_path}: refused. {MANAGER_REFUSAL}", file=sys.stderr)
        return 1

    try:
        return handler(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except ForemanError as exc:
        # Something Foreman itself refused or could not do. The message is
        # written for the operator; a traceback would only bury it.
        print(f"foreman: {exc}", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:
        print(
            f"foreman: the database could not be used: {exc}",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:  # noqa: BLE001 - the last line of defence for a command
        if os.environ.get("FOREMAN_DEBUG"):
            raise
        print(
            f"foreman: unexpected error ({type(exc).__name__}): {exc}\n"
            "This is a bug in Foreman. Set FOREMAN_DEBUG=1 and run again for the traceback.",
            file=sys.stderr,
        )
        return 70
