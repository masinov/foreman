"""``foreman changelog``: write ``CHANGELOG.md`` from ``changes/`` by hand (ADR-0040)."""

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


def handle_changelog(args: argparse.Namespace) -> int:
    """Handle ``foreman changelog``: fold the change files into a sprint's section."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        try:
            enabled = settings_of(project).generate_changelog
        except SettingsError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if not enabled:
            print(
                f"Project {project.id} does not generate its changelog. "
                f"Turn it on with: foreman config {project.id} --set generate_changelog=true",
                file=sys.stderr,
            )
            return 1
        if args.sprint:
            sprint = resolve_sprint_or_print(store, args.sprint)
            if sprint is None:
                return 1
        else:
            sprint = SprintCheckpoints(store).sprint_for_changelog(project)
            if sprint is None:
                print(f"Project {project.id} has no sprint to name the section after; use --sprint.", file=sys.stderr)
                return 1
        result = SprintCheckpoints(store).write_changelog(project, sprint)
    if result.problem:
        print(f"The changelog was not written: {result.problem}", file=sys.stderr)
        return 1
    if result.changelog_path is None:
        print_lines("No change files in changes/; nothing written.")
        return 0
    print_lines(
        f"Wrote {result.changelog_path} for {sprint.title} and removed its change files",
        f"Commit: {str(result.sha or '')[:7]} on {project.default_branch}",
    )
    return 0


def register_changelog(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman changelog` to the parser."""

    parser = subparsers.add_parser(
        "changelog",
        help="Write CHANGELOG.md from the change files in changes/, as a finished sprint does.",
    )
    parser.add_argument("project_id", help="Project identifier.")
    parser.add_argument(
        "--sprint",
        help="The sprint the section is named after. Default: the active sprint, else the last finished.",
    )
    add_db_option(
        parser,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(parser, handle_changelog, "changelog")
