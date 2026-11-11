"""Human decisions: approve, deny, and merge waivers."""

from __future__ import annotations

import argparse
import sys
from uuid import uuid4

from ..models import utc_now_text
from ..orchestrator import ForemanOrchestrator, OrchestratorError
from ..store import ForemanStore

from .common import (
    DB_OPTION_NOTE,
    add_db_option,
    print_lines,
    resolve_db_path_or_print,
    set_handler,
)


def handle_approve(args: argparse.Namespace) -> int:
    """Handle ``foreman approve``."""

    return _handle_human_gate_decision(args, outcome="approve")


def handle_deny(args: argparse.Namespace) -> int:
    """Handle ``foreman deny``."""

    return _handle_human_gate_decision(args, outcome="deny")


def handle_waive_merge(args: argparse.Namespace) -> int:
    """Handle ``foreman waive-merge``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    from ..models import MergeWaiver

    waiver_types = {
        "missing_acceptance_criteria",
        "incomplete_criteria",
        "no_code_delta",
        "docs_only_impl_task",
    }
    if args.waiver_type not in waiver_types:
        print(
            f"Invalid waiver type {args.waiver_type!r}. "
            f"Must be one of: {', '.join(sorted(waiver_types))}",
            file=sys.stderr,
        )
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = store.get_task(args.task_id)
        if task is None:
            print(f"Task not found: {args.task_id}", file=sys.stderr)
            return 1
        if task.project_id != args.project_id:
            print(
                f"Task {args.task_id} does not belong to project {args.project_id}",
                file=sys.stderr,
            )
            return 1

        # Get branch info for the waiver
        branch_name = task.branch_name or "unknown"
        project = store.get_project(args.project_id)
        if project is None:
            print(f"Project not found: {args.project_id}", file=sys.stderr)
            return 1

        # Get current HEAD SHA
        try:
            from ..git import head_sha
            head_sha_val = head_sha(project.repo_path, f"refs/heads/{branch_name}") or ""
            base_sha = head_sha(project.repo_path, f"refs/heads/{project.default_branch}") or ""
        except Exception as e:
            print(f"Failed to get branch SHA: {e}", file=sys.stderr)
            return 1

        now = utc_now_text()
        waiver = MergeWaiver(
            id=f"waiver-{uuid4().hex[:12]}",
            task_id=task.id,
            project_id=args.project_id,
            waiver_type=args.waiver_type,
            reason=args.reason,
            approved_by=args.approved_by or "human",
            approved_at=now,
            branch_name=branch_name,
            head_sha=head_sha_val,
            base_sha=base_sha,
            expires_at=None,
            revoked_at=None,
        )
        store.save_merge_waiver(waiver)

    print_lines(
        "Waiver created",
        f"Database: {db_path}",
        f"Task ID: {task.id}",
        f"Type: {waiver.waiver_type}",
        f"Reason: {args.reason}",
        f"Approved by: {waiver.approved_by}",
        f"Branch: {branch_name} ({head_sha_val[:8]})",
        f"Waiver ID: {waiver.id}",
    )
    return 0


def handle_revoke_waiver(args: argparse.Namespace) -> int:
    """Handle ``foreman revoke-waiver``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        waiver = store.get_merge_waiver(args.waiver_id)
        if waiver is None:
            print(f"Waiver not found: {args.waiver_id}", file=sys.stderr)
            return 1

        revoked = store.revoke_merge_waiver(args.waiver_id)
        if not revoked:
            print(f"Waiver already revoked: {args.waiver_id}", file=sys.stderr)
            return 1

    print_lines(
        "Waiver revoked",
        f"Database: {db_path}",
        f"Waiver ID: {args.waiver_id}",
        f"Task ID: {waiver.task_id}",
    )
    return 0


def _handle_human_gate_decision(args: argparse.Namespace, *, outcome: str) -> int:
    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        orchestrator = ForemanOrchestrator(store)
        try:
            # A decision, not an execution: this process holds neither the
            # project's engine lock nor a task lease, so the step the decision
            # leads to is left for an engine. ADR-0011.
            result = orchestrator.resume_human_gate(
                args.task_id,
                outcome=outcome,
                note=args.note,
                defer=True,
            )
        except OrchestratorError as exc:
            print(f"Failed to {outcome} task: {exc}", file=sys.stderr)
            return 1
        engine_resident = store.get_engine_lock(result.task.project_id) is not None
        db_path = store.db_path

    action = "Approved" if outcome == "approve" else "Denied"
    lines = [
        f"{action} task",
        f"Database: {db_path}",
        f"Task ID: {result.task.id}",
        f"Resume from: {result.paused_step}",
        f"Next step: {result.next_step}",
        f"Status: {result.task.status}",
        (
            "Engine: resident; it continues the task"
            if engine_resident
            else (
                "Engine: none running; continue with "
                f"`foreman run {result.task.project_id}` or `foreman serve {result.task.project_id}`"
            )
        ),
    ]
    if args.note:
        lines.append(f"Note: {args.note}")
    if result.task.workflow_current_step:
        lines.append(f"Persisted step: {result.task.workflow_current_step}")
    if result.task.blocked_reason:
        lines.append(f"Blocked reason: {result.task.blocked_reason}")
    print_lines(*lines)
    return 0


def register_approve(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman approve` to the parser."""

    approve_parser = subparsers.add_parser("approve", help="Approve a paused task.")
    approve_parser.add_argument("task_id", help="Task identifier.")
    approve_parser.add_argument("--note", help="Optional approval note.")
    add_db_option(
        approve_parser,
        help_text=f"Path to the SQLite store containing the paused task. {DB_OPTION_NOTE}",
    )
    set_handler(approve_parser, handle_approve, "approve")



def register_deny(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman deny` to the parser."""

    deny_parser = subparsers.add_parser("deny", help="Deny a paused task.")
    deny_parser.add_argument("task_id", help="Task identifier.")
    deny_parser.add_argument("--note", help="Optional denial note.")
    add_db_option(
        deny_parser,
        help_text=f"Path to the SQLite store containing the paused task. {DB_OPTION_NOTE}",
    )
    set_handler(deny_parser, handle_deny, "deny")



def register_waive_merge(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman waive-merge` to the parser."""

    waive_parser = subparsers.add_parser(
        "waive-merge",
        help="Issue a human waiver allowing a task to merge despite proof deficiency.",
    )
    waive_parser.add_argument("task_id", help="Task identifier.")
    waive_parser.add_argument(
        "--project",
        dest="project_id",
        required=True,
        help="Project identifier.",
    )
    waive_parser.add_argument(
        "--type",
        dest="waiver_type",
        required=True,
        choices=[
            "missing_acceptance_criteria",
            "incomplete_criteria",
            "no_code_delta",
            "docs_only_impl_task",
        ],
        help="Type of proof deficiency being waived.",
    )
    waive_parser.add_argument(
        "--reason",
        required=True,
        help="Human-readable reason for the waiver.",
    )
    waive_parser.add_argument(
        "--by",
        dest="approved_by",
        default="human",
        help="Who approved the waiver (default: human).",
    )
    add_db_option(
        waive_parser,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(waive_parser, handle_waive_merge, "waive-merge")



def register_revoke_waiver(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman revoke-waiver` to the parser."""

    revoke_parser = subparsers.add_parser(
        "revoke-waiver",
        help="Revoke a previously issued merge waiver.",
    )
    revoke_parser.add_argument("waiver_id", help="Waiver identifier.")
    add_db_option(
        revoke_parser,
        help_text=f"Path to the SQLite store containing the waiver. {DB_OPTION_NOTE}",
    )
    set_handler(revoke_parser, handle_revoke_waiver, "revoke-waiver")

