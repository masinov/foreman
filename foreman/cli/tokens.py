"""API tokens other systems use to file work."""

from __future__ import annotations

import argparse
import sys

from ..api_tokens import API_TOKEN_SCOPES, ApiTokenError
from ..store import ForemanStore

from .common import (
    DB_OPTION_NOTE,
    add_db_option,
    print_lines,
    resolve_db_path_or_print,
    resolve_project_or_print,
    set_handler,
)


def handle_token_create(args: argparse.Namespace) -> int:
    """Handle ``foreman token create``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        try:
            token, secret = store.create_api_token(
                project_id=project.id,
                name=args.name,
                scopes=args.scope or None,
            )
        except (ApiTokenError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1

    print_lines(
        "API token created",
        f"Project: {project.id} | {project.name}",
        f"Token: {token.id} | {token.name}",
        f"Scopes: {', '.join(token.scopes)}",
        "",
        f"  {secret}",
        "",
        "This secret is shown once and is not stored — only its SHA-256 is.",
        "Copy it now; if it is lost, revoke this token and create another.",
    )
    return 0


def handle_token_list(args: argparse.Namespace) -> int:
    """Handle ``foreman token list``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        tokens = store.list_api_tokens(project.id)

    lines = [
        "API tokens",
        f"Project: {project.id} | {project.name}",
    ]
    if not tokens:
        lines.append("- none")
    else:
        for token in tokens:
            state = "active" if token.is_active else f"revoked {token.revoked_at}"
            lines.append(f"- {token.id} | {token.name} | {state}")
            lines.append(
                f"  scopes={', '.join(token.scopes)} | created={token.created_at}"
                f" | last_used={token.last_used_at or 'never'}"
            )
    print_lines(*lines)
    return 0


def handle_token_revoke(args: argparse.Namespace) -> int:
    """Handle ``foreman token revoke``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        token = store.get_api_token(args.token_id)
        # Scoped to the named project so a mistyped id cannot revoke another
        # project's credential.
        if token is None or token.project_id != project.id:
            print(
                f"Unknown API token for project {project.id}: {args.token_id}",
                file=sys.stderr,
            )
            return 1
        already_revoked = not token.is_active
        token = store.revoke_api_token(token.id)

    print_lines(
        "API token already revoked" if already_revoked else "API token revoked",
        f"Project: {project.id} | {project.name}",
        f"Token: {token.id} | {token.name}",
        f"Revoked: {token.revoked_at}",
    )
    return 0


def register_token(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman token` to the parser."""

    token_parser = subparsers.add_parser(
        "token",
        help="Manage the project API tokens other systems use to file work.",
    )
    token_commands = token_parser.add_subparsers(dest="token_command")
    token_parser.set_defaults(handler=None, command_path="token")

    token_create = token_commands.add_parser(
        "create",
        help="Create an API token and print its secret once.",
    )
    token_create.add_argument("project_id", help="Project identifier.")
    token_create.add_argument(
        "--name",
        required=True,
        help="What holds this token, e.g. `pagerduty` or `ci`. Recorded on every task it files.",
    )
    token_create.add_argument(
        "--scope",
        action="append",
        choices=sorted(API_TOKEN_SCOPES),
        help="Scope to grant; repeatable. Defaults to `intake`.",
    )
    add_db_option(
        token_create,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(token_create, handle_token_create, "token create")

    token_list = token_commands.add_parser(
        "list",
        help="List a project's API tokens (secrets are never shown).",
    )
    token_list.add_argument("project_id", help="Project identifier.")
    add_db_option(
        token_list,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(token_list, handle_token_list, "token list")

    token_revoke = token_commands.add_parser(
        "revoke",
        help="Revoke an API token so it can no longer authenticate.",
    )
    token_revoke.add_argument("project_id", help="Project identifier.")
    token_revoke.add_argument("token_id", help="API token identifier.")
    add_db_option(
        token_revoke,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(token_revoke, handle_token_revoke, "token revoke")

