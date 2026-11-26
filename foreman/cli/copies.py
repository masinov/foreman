"""``foreman copies``: write ``docs/STATUS.md``, ``docs/sprints/current.md`` and ``docs/sprints/backlog.md`` by hand (ADR-0040)."""

from __future__ import annotations

import argparse
import sys

from ..domain.settings import SettingsError, settings_of
from ..mutations.checkpoint import SprintCheckpoints
from ..store import ForemanStore
from .common import (
    DB_OPTION_NOTE,
    add_db_option,
    print_lines,
    resolve_db_path_or_print,
    resolve_project_or_print,
    resolve_sprint_or_print,
    set_handler,
)


def handle_copies(args: argparse.Namespace) -> int:
    """Handle ``foreman copies``: write the project's status and sprint copies now."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        try:
            enabled = settings_of(project).generate_copies
        except SettingsError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if not enabled:
            print(
                f"Project {project.id} does not generate its status and sprint copies. "
                f"Turn it on with: foreman config {project.id} --set generate_copies=true",
                file=sys.stderr,
            )
            return 1
        checkpoints = SprintCheckpoints(store)
        if args.sprint:
            sprint = resolve_sprint_or_print(store, args.sprint)
            if sprint is None:
                return 1
            if sprint.project_id != project.id:
                print(f"{args.sprint} is not a sprint of project {project.id}.", file=sys.stderr)
                return 1
        else:
            # The writing is recorded on the active sprint, else the last finished.
            sprint = checkpoints.active_sprint(project) or checkpoints.sprint_for_changelog(project)
            if sprint is None:
                print(f"Project {project.id} has no sprint yet; there is nothing to write.", file=sys.stderr)
                return 1
        result = checkpoints.write_copies(project, sprint, why="written by hand", archive=bool(args.sprint), backlog=True)
    if result.problem:
        print(f"The copies were not written: {result.problem}", file=sys.stderr)
        return 1
    if result.sha is None:
        print_lines("The copies are up to date; nothing written.")
        return 0
    print_lines(
        "Wrote docs/STATUS.md, docs/sprints/current.md and docs/sprints/backlog.md"
        + (" and the sprint's archive copy" if args.sprint and sprint.status == "completed" else ""),
        f"Commit: {str(result.sha)[:7]} on {project.default_branch}",
    )
    return 0


def register_copies(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman copies` to the parser."""

    parser = subparsers.add_parser(
        "copies",
        help="Write docs/STATUS.md, docs/sprints/current.md and docs/sprints/backlog.md from the database.",
    )
    parser.add_argument("project_id", help="Project identifier.")
    parser.add_argument(
        "--sprint",
        help="Also write this finished sprint's archive copy, docs/sprints/archive/sprint-<n>-<slug>.md.",
    )
    add_db_option(
        parser,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(parser, handle_copies, "copies")
