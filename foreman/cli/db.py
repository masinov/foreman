"""Database schema version and migrations."""

from __future__ import annotations

import argparse
import sqlite3

from ..migrations import MIGRATIONS
from ..store import ForemanStore

from .common import (
    add_db_option,
    resolve_db_path_or_print,
    set_handler,
)


def handle_db_version(args: argparse.Namespace) -> int:
    """Handle ``foreman db version``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        try:
            version = store.schema_version()
        except sqlite3.OperationalError:
            print(
                "Schema version: 0 "
                "(schema_migrations table not present — run `foreman db migrate`)"
            )
            return 0

    latest = max((v for v, _, _ in MIGRATIONS), default=0)
    if version == latest:
        print(f"Schema version: {version} (up to date)")
    else:
        print(f"Schema version: {version} (latest available: {latest})")
    return 0


def handle_db_migrate(args: argparse.Namespace) -> int:
    """Handle ``foreman db migrate``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        applied = store.initialize()
        current_version = store.schema_version()

    if not applied:
        print(f"Schema is already up to date at version {current_version}.")
        return 0

    descriptions = {v: desc for v, desc, _ in MIGRATIONS}
    print(f"Applied {len(applied)} migration(s):")
    for v in applied:
        print(f"  [{v}] {descriptions.get(v, '(no description)')}")
    return 0


def register_db(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman db` to the parser."""

    db_parser = subparsers.add_parser("db", help="Database management commands.")
    db_commands = db_parser.add_subparsers(dest="db_command", metavar="db_command")

    db_version_parser = db_commands.add_parser(
        "version",
        help="Show the current schema version.",
    )
    add_db_option(db_version_parser)
    set_handler(db_version_parser, handle_db_version, "db version")

    db_migrate_parser = db_commands.add_parser(
        "migrate",
        help="Apply pending schema migrations.",
    )
    add_db_option(db_migrate_parser)
    set_handler(db_migrate_parser, handle_db_migrate, "db migrate")

