"""`foreman role` and `foreman workflow`: a project's own definitions (ADR-0024)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..definitions import (
    ROLE,
    WORKFLOW,
    DefinitionError,
    project_definitions,
    remove_definition,
    save_role,
    save_workflow,
)
from ..engine_control import default_command_requester
from ..model_check import check_model
from ..roles import RoleLoadError
from ..store import ForemanStore
from ..workflows import WorkflowLoadError
from .common import print_lines, resolve_db_path_or_print, set_handler


def _origin(definition_id: str, own: dict[str, str], shipped: frozenset[str]) -> str:
    if definition_id not in own:
        return "shipped"
    return "changed for this project" if definition_id in shipped else "this project's own"


def _open(args: argparse.Namespace):
    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return None
    store = ForemanStore(db_path)
    store.initialize()
    if store.get_project(args.project_id) is None:
        print(f"Unknown project: {args.project_id}", file=sys.stderr)
        store.close()
        return None
    return store


def _definitions(store: ForemanStore, project_id: str):
    try:
        return project_definitions(store, project_id)
    except (RoleLoadError, WorkflowLoadError) as exc:
        print(f"The project's definitions do not load: {exc}", file=sys.stderr)
        return None


def _parts(definitions, kind: str):
    if kind == ROLE:
        return definitions.roles, definitions.own_roles, definitions.shipped_roles
    return definitions.workflows, definitions.own_workflows, definitions.shipped_workflows


def handle_list(args: argparse.Namespace) -> int:
    store = _open(args)
    if store is None:
        return 1
    with store:
        definitions = _definitions(store, args.project_id)
        if definitions is None:
            return 1
        loaded, own, shipped = _parts(definitions, args.kind)
        lines = [f"{args.kind.capitalize()}s of {args.project_id}"]
        for definition_id, definition in loaded.items():
            lines.append(f"{definition_id} | {definition.name} | {_origin(definition_id, own, shipped)}")
        print_lines(*lines)
    return 0


def handle_show(args: argparse.Namespace) -> int:
    store = _open(args)
    if store is None:
        return 1
    with store:
        definitions = _definitions(store, args.project_id)
        if definitions is None:
            return 1
        loaded, own, _ = _parts(definitions, args.kind)
        if args.definition_id not in loaded:
            print(f"Unknown {args.kind}: {args.definition_id}", file=sys.stderr)
            return 1
        text = own.get(args.definition_id)
        if text is None:
            text = Path(loaded[args.definition_id].source_path).read_text(encoding="utf-8")
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


def handle_set(args: argparse.Namespace) -> int:
    try:
        text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Cannot read {args.file}: {exc}", file=sys.stderr)
        return 1
    store = _open(args)
    if store is None:
        return 1
    with store:
        try:
            if args.kind == ROLE:
                saved = save_role(
                    store, args.project_id, text, changed_by=default_command_requester(), check_model=check_model
                )
            else:
                saved = save_workflow(store, args.project_id, text, changed_by=default_command_requester())
        except DefinitionError as exc:
            print(f"Not saved: {exc}", file=sys.stderr)
            return 1
        print_lines(
            f"Saved {args.kind} {saved.id} for {args.project_id}.",
            "The engine uses it from the next task it starts.",
        )
    return 0


def handle_reset(args: argparse.Namespace) -> int:
    store = _open(args)
    if store is None:
        return 1
    with store:
        try:
            shipped_left = remove_definition(
                store,
                args.project_id,
                args.kind,
                args.definition_id,
                changed_by=default_command_requester(),
            )
        except DefinitionError as exc:
            print(f"Not changed: {exc}", file=sys.stderr)
            return 1
        print(
            f"{args.project_id} uses the shipped {args.kind} {args.definition_id} again."
            if shipped_left
            else f"Removed {args.kind} {args.definition_id} from {args.project_id}."
        )
    return 0


def _register(subparsers: argparse._SubParsersAction, kind: str) -> None:
    parser = subparsers.add_parser(
        kind,
        help=f"A project's own {kind}s: list, show, set from a file, reset.",
    )
    commands = parser.add_subparsers(dest=f"{kind}_command", required=True)

    def add(name: str, help_text: str, handler, *, definition: bool = False, file: bool = False):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("project_id", help="Project identifier.")
        if definition:
            sub.add_argument("definition_id", help=f"The {kind}'s id.")
        if file:
            sub.add_argument(
                "--file", required=True, help=f"TOML file holding the {kind}, or - for standard input."
            )
        sub.add_argument("--db", help="Path to the SQLite store. Defaults to $FOREMAN_DB, else repo-local discovery.")
        sub.set_defaults(kind=kind)
        set_handler(sub, handler, f"{kind} {name}")

    add("list", f"List the {kind}s the project runs with and where each comes from.", handle_list)
    add("show", f"Print one {kind} as TOML, the project's own text or the shipped file.", handle_show, definition=True)
    add(
        "set",
        f"Save a {kind} for the project from a TOML file. Its id is the one in the file: "
        f"a shipped id replaces the shipped {kind} for this project, a new id adds one.",
        handle_set,
        file=True,
    )
    add(
        "reset",
        f"Drop the project's own text for one {kind}: a shipped id goes back to the shipped one.",
        handle_reset,
        definition=True,
    )


def register_role(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman role` to the parser."""

    _register(subparsers, ROLE)


def register_workflow(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman workflow` to the parser."""

    _register(subparsers, WORKFLOW)
