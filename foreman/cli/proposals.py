"""Proposals: create, list, show, confirm, decline (ADR-0022)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..engine_control import default_command_requester
from ..models import PROPOSAL_STATES
from ..proposals import (
    MANAGER,
    OPERATION_KINDS,
    PROPOSAL_PAGE_LIMIT,
    ProposalError,
    Proposals,
    manager_session,
    manager_turn,
    read_proposals,
    serialize_proposal,
)
from ..store import ForemanStore
from .common import (
    DB_OPTION_NOTE,
    add_db_option,
    add_json_option,
    print_json,
    print_lines,
    resolve_db_path_or_print,
    resolve_project_or_print,
    set_handler,
    truncate_text,
)

#: What `--json` reads: the document a proposal is made from.
PROPOSAL_DOCUMENT_HELP = (
    'A JSON document {"reason": "...", "operations": [...], "leaves": [task ids]}, '
    "from a file or - for standard input. Each operation is an object with a "
    f"\"kind\": {', '.join(OPERATION_KINDS)}."
)


def _read_document(source: str) -> Any:
    raw = sys.stdin.read() if source == "-" else Path(source).expanduser().read_text(encoding="utf-8")
    return json.loads(raw)


def _name(names: dict[str, Any], kind: str, item_id: str) -> str:
    entry = (names.get(kind) or {}).get(item_id) or {}
    if kind == "tasks":
        label = entry.get("key") or item_id
        return f"{label} {entry['title']}" if entry.get("title") else label
    return entry.get("title") or item_id


def describe_operation(operation: dict[str, Any], names: dict[str, Any]) -> str:
    """One operation in plain words, for `proposal show`."""

    kind = operation["kind"]
    task = _name(names, "tasks", operation["task_id"]) if operation.get("task_id") else ""
    sprint = _name(names, "sprints", operation["sprint_id"]) if operation.get("sprint_id") else ""
    if kind == "create_sprint":
        return f"Create sprint {operation['title']}, planned"
    if kind == "edit_sprint":
        fields = ", ".join(name for name in ("title", "goal") if name in operation)
        return f"Change the {fields} of sprint {sprint}"
    if kind == "activate_sprint":
        return f"Activate sprint {sprint}"
    if kind == "finish_sprint":
        return f"Finish sprint {sprint}"
    if kind == "file_task":
        state = "accepted" if operation.get("accept") else "filed"
        return f"File {operation['title']} in the backlog, {state}"
    if kind == "accept_task":
        return f"Accept {task}"
    if kind == "decline_task":
        reason = f": {operation['reason']}" if operation.get("reason") else ""
        return f"Decline {task}{reason}"
    if kind == "plan_tasks":
        tasks = ", ".join(_name(names, "tasks", task_id) for task_id in operation["task_ids"])
        if operation.get("new_sprint"):
            return f"Plan {tasks} into a new sprint, {operation['new_sprint']['title']}"
        return f"Plan {tasks} into {sprint}"
    if kind == "unplan_task":
        return f"Move {task} back to the backlog"
    if kind == "edit_task":
        fields = ", ".join(name for name in OPERATION_KINDS[kind].one_of if name in operation)
        return f"Change the {fields} of {task}"
    if kind == "block_task":
        return f"Block {task}: {operation['reason']}"
    if kind == "unblock_task":
        return f"Unblock {task}"
    if kind == "cancel_task":
        return f"Cancel {task}"
    if kind == "send_back":
        return f"Send {task} back: {operation['guidance']}"
    if kind == "approve_gate":
        return f"Approve {task} at its gate"
    return kind


def _proposal_lines(proposal: dict[str, Any]) -> list[str]:
    lines = [
        f"Proposal: {proposal['id']} | {proposal['state']}",
        f"Project: {proposal['project_id']}",
        f"Proposed by: {proposal['proposed_by']} at {proposal['created_at']}",
        f"Reason: {proposal['reason']}",
        "Operations:",
    ]
    for index, operation in enumerate(proposal["operations"], start=1):
        lines.append(f"  {index}. {describe_operation(operation, proposal['names'])}")
    for task_id in proposal["leaves"]:
        lines.append(f"  Leave {_name(proposal['names'], 'tasks', task_id)}")
    outcome = proposal.get("outcome") or {}
    if proposal["decided_by"]:
        lines.append(f"Decided by: {proposal['decided_by']} at {proposal['decided_at']}")
    if outcome.get("sentence"):
        lines.append(f"Outcome: {outcome['sentence']}")
    for warning in outcome.get("warnings") or ():
        lines.append(warning)
    return lines


def handle_proposal_create(args: argparse.Namespace) -> int:
    """Handle ``foreman proposal create``."""

    try:
        document = _read_document(args.document)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read the proposal from {args.document}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(document, dict):
        print("The proposal must be a JSON object with reason and operations.", file=sys.stderr)
        return 1
    session_project = manager_session()
    if session_project is not None and session_project != args.project_id:
        print(
            f"This manager session belongs to project {session_project}; it cannot "
            f"propose changes to {args.project_id}.",
            file=sys.stderr,
        )
        return 1
    unknown = sorted(set(document) - {"reason", "operations", "leaves"})
    if unknown:
        print(f"Unknown fields in the proposal: {', '.join(unknown)}.", file=sys.stderr)
        return 1

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        in_session = session_project is not None
        try:
            proposal = Proposals(store, via="cli", actor=default_command_requester()).create(
                project,
                reason=document.get("reason"),
                operations=document.get("operations"),
                leaves=document.get("leaves"),
                proposed_by=MANAGER if in_session else default_command_requester(),
                session_id=store.get_meta_session(project.id) if in_session else None,
                turn_id=manager_turn() if in_session else None,
            )
        except ProposalError as exc:
            print(f"Refused, nothing stored. {exc}", file=sys.stderr)
            return 1
        payload = serialize_proposal(proposal)

    if args.as_json:
        print_json(payload)
        return 0
    print_lines(
        "Stored the proposal. Nothing changes until a person confirms it.",
        *_proposal_lines(payload),
    )
    return 0


def handle_proposal_list(args: argparse.Namespace) -> int:
    """Handle ``foreman proposal list``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    states = [piece.strip() for value in args.state for piece in value.split(",") if piece.strip()]
    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        try:
            page = read_proposals(store, project, states=states, limit=args.limit, offset=args.offset)
        except ProposalError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.as_json:
        print_json(page)
        return 0
    lines = [f"Proposals: {project.id} | {project.name} | {page['total']} in all"]
    if not page["proposals"]:
        lines.append("None.")
    for proposal in page["proposals"]:
        lines.append(
            f"  {proposal['id']} | {proposal['state']} | {len(proposal['operations'])} op(s) | "
            f"{proposal['proposed_by']} | {truncate_text(proposal['reason'], limit=72)}"
        )
    print_lines(*lines)
    return 0


def handle_proposal_show(args: argparse.Namespace) -> int:
    """Handle ``foreman proposal show``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        proposal = store.get_proposal(args.proposal_id)
    if proposal is None:
        print(f"Proposal not found: {args.proposal_id}", file=sys.stderr)
        return 1
    payload = serialize_proposal(proposal)
    if args.as_json:
        print_json(payload)
    else:
        print_lines(*_proposal_lines(payload))
    return 0


def _decide(args: argparse.Namespace, decision: str) -> int:
    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        proposals = Proposals(store, via="cli", actor=default_command_requester())
        try:
            proposal = (
                proposals.confirm(args.proposal_id)
                if decision == "confirm"
                else proposals.decline(args.proposal_id)
            )
        except ProposalError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        payload = serialize_proposal(proposal)
    if args.as_json:
        print_json(payload)
    else:
        print_lines(*_proposal_lines(payload))
    return 1 if payload["state"] == "failed" else 0


def handle_proposal_confirm(args: argparse.Namespace) -> int:
    """Handle ``foreman proposal confirm``."""

    return _decide(args, "confirm")


def handle_proposal_decline(args: argparse.Namespace) -> int:
    """Handle ``foreman proposal decline``."""

    return _decide(args, "decline")


def register_proposal(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman proposal` to the parser."""

    proposal_parser = subparsers.add_parser(
        "proposal",
        help="Changes proposed for a project; nothing happens until a person confirms.",
    )
    commands = proposal_parser.add_subparsers(
        dest="proposal_command", metavar="proposal_command", required=True
    )
    db_help = f"Path to the SQLite store. {DB_OPTION_NOTE}"

    create = commands.add_parser(
        "create", help="Check and store a proposal. A refused operation stores nothing."
    )
    create.add_argument("project_id", help="Project identifier.")
    create.add_argument(
        "--json", dest="document", required=True, metavar="FILE", help=PROPOSAL_DOCUMENT_HELP
    )
    create.add_argument(
        "--print-json",
        dest="as_json",
        action="store_true",
        help="Print the stored proposal as one JSON document.",
    )
    add_db_option(create, help_text=db_help)
    set_handler(create, handle_proposal_create, "proposal create")

    listing = commands.add_parser("list", help="List a project's proposals, newest first.")
    listing.add_argument("project_id", help="Project identifier.")
    listing.add_argument(
        "--state",
        action="append",
        default=[],
        metavar="STATE",
        help=f"Only these states ({', '.join(PROPOSAL_STATES)}); repeatable or comma-separated.",
    )
    listing.add_argument("--limit", type=int, default=PROPOSAL_PAGE_LIMIT, help="How many to show.")
    listing.add_argument("--offset", type=int, default=0, help="How many to skip.")
    add_json_option(listing)
    add_db_option(listing, help_text=db_help)
    set_handler(listing, handle_proposal_list, "proposal list")

    for name, handler, help_text in (
        ("show", handle_proposal_show, "Show one proposal in plain words."),
        (
            "confirm",
            handle_proposal_confirm,
            "Apply a proposal, whole or not at all, as you.",
        ),
        ("decline", handle_proposal_decline, "Decline a proposal. Nothing changes."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("proposal_id", help="Proposal identifier.")
        add_json_option(command)
        add_db_option(command, help_text=db_help)
        set_handler(command, handler, f"proposal {name}")
