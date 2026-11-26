"""``foreman task show`` and ``foreman task list``.
"""

from __future__ import annotations

import argparse
import json
import sys

from ...services import Services
from ...services.errors import NotFoundError
from ...store import ForemanStore
from ..common import (
    read_or_print,
    BLOCKED_KIND_HINTS,
    format_step_visits,
    format_usd,
    print_json,
    print_lines,
    render_event_line,
    resolve_db_path_or_print,
    resolve_task_or_print,
    truncate_text,
)


def describe_filed_from(created_by: str | None, filed_from: dict | None) -> str | None:
    """"Filed by the developer while working on FOR-12", or None for other tasks."""

    if not filed_from:
        return None
    role = (created_by or "").removeprefix("agent:")
    who = f"the {role.replace('_', ' ').replace('-', ' ')}" if role else "an agent"
    if not filed_from["exists"]:
        return f"Filed by {who} while working on a task that no longer exists"
    return f"Filed by {who} while working on {filed_from['task_key'] or filed_from['task_id']}"


def handle_task_show(args: argparse.Namespace) -> int:
    """Handle ``foreman task show``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        task_row = resolve_task_or_print(store, args.task_id)
        if task_row is None:
            return 1
        try:
            history = Services(store).reports.history(task_row.id)
        except NotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.as_json:
        print_json(history)
        return 0

    task, totals, runs, events = history["task"], history["totals"], history["runs"], history["events"]
    latest_run = runs[-1] if runs else None
    active_run = next((run for run in reversed(runs) if run["status"] == "running"), None)
    latest_event = events[-1] if events else None
    kind = task["blocked_kind"]

    lines = [
        "Task",
        f"Database: {history['database']}",
        f"Task: {task['id']} | {task['title']}",
        f"Project: {history['project']['id']} | {history['project']['name'] or 'unknown'}",
        f"Sprint: {history['sprint']['id']} | {history['sprint']['title'] or 'unknown'}",
        f"Status: {task['status']} | type={task['task_type']} | created_by={task['created_by']}",
        (
            f"Totals: runs={totals['run_count']} | "
            f"tokens={totals['total_token_count']} | "
            f"cost_usd={format_usd(float(totals['total_cost_usd']))} | "
            f"duration_ms={totals['total_duration_ms']}"
        ),
        f"Step visits: {format_step_visits(task['step_visit_counts'])}",
    ]
    filed_from_line = describe_filed_from(task["created_by"], history["filed_from"])
    if filed_from_line:
        lines.append(filed_from_line)
    if task["branch_name"]:
        lines.append(f"Branch: {task['branch_name']}")
    if task["worktree_path"]:
        lines.append(f"Worktree: {task['worktree_path']}")
    if task["assigned_role"]:
        lines.append(f"Assigned role: {task['assigned_role']}")
    if task["workflow_current_step"]:
        lines.append(f"Current step: {task['workflow_current_step']}")
    if task["executor_overrides"]:
        lines.append(
            f"Executor overrides: {json.dumps(task['executor_overrides'], sort_keys=True)}"
        )
    if kind is not None:
        lines.append(f"Blocked kind: {kind} ({BLOCKED_KIND_HINTS[kind]})")
    if task["blocked_reason"]:
        lines.append(f"Blocked reason: {task['blocked_reason']}")

    if active_run is not None:
        lines.append(
            "Active run: "
            f"{active_run['id']} | role={active_run['role_id']} | step={active_run['workflow_step']} | "
            f"status={active_run['status']} | started_at={active_run['started_at'] or 'unknown'}"
        )
    else:
        lines.append("Active run: none")

    if latest_run is not None:
        latest_parts = [
            latest_run["id"],
            f"role={latest_run['role_id']}",
            f"step={latest_run['workflow_step']}",
            f"status={latest_run['status']}",
            f"cost_usd={format_usd(latest_run['cost_usd'])}",
            f"tokens={latest_run['token_count']}",
            f"duration_ms={latest_run['duration_ms'] or 0}",
        ]
        if latest_run["outcome"]:
            latest_parts.append(f"outcome={latest_run['outcome']}")
        if latest_run["outcome_detail"]:
            latest_parts.append(f"detail={truncate_text(latest_run['outcome_detail'])}")
        lines.append(f"Latest run: {' | '.join(latest_parts)}")
    else:
        lines.append("Latest run: none")

    if latest_event is not None:
        lines.append(
            "Latest event: "
            + render_event_line(
                latest_event["event_type"],
                latest_event["timestamp"],
                latest_event["role_id"],
                latest_event["payload"],
            )
        )
    else:
        lines.append("Latest event: none")

    lines.append("Recent runs:")
    recent_runs = runs[-max(args.runs, 0):] if args.runs > 0 else []
    if not recent_runs:
        lines.append("- none")
    for run in recent_runs:
        parts = [
            run["id"],
            f"role={run['role_id']}",
            f"step={run['workflow_step']}",
            f"status={run['status']}",
        ]
        if run["outcome"]:
            parts.append(f"outcome={run['outcome']}")
        if run["outcome_detail"]:
            parts.append(f"detail={truncate_text(run['outcome_detail'])}")
        lines.append(f"- {' | '.join(parts)}")

    lines.append("Recent events:")
    recent_events = events[-max(args.events, 0):] if args.events > 0 else []
    if not recent_events:
        lines.append("- none")
    for event in recent_events:
        lines.append(
            f"- {render_event_line(event['event_type'], event['timestamp'], event['role_id'], event['payload'])}"
        )

    print_lines(*lines)
    return 0

def handle_task_list(args: argparse.Namespace) -> int:
    """Handle ``foreman task list``."""

    listing = read_or_print(
        args,
        lambda store: Services(store).reports.tasks(
            args.project_id,
            sprint_id=getattr(args, "sprint", None),
            rests_on=getattr(args, "rests_on", None),
        ),
    )
    if listing is None:
        return 1
    if getattr(args, "as_json", False):
        print_json(
            {key: value for key, value in listing.items() if key not in ("project_name", "sprints")}
        )
        return 0

    lines = [
        "Tasks",
        f"Database: {listing['database']}",
        f"Project: {listing['project_id']} | {listing['project_name']}",
    ]
    if not listing["tasks"]:
        lines.append(
            f"No task rests on {args.rests_on}."
            if getattr(args, "rests_on", None)
            else "No tasks are defined for this project."
        )
    for sprint in listing["sprints"]:
        sprint_tasks = [task for task in listing["tasks"] if task["sprint_id"] == sprint["id"]]
        if not sprint_tasks:
            continue
        lines.append(f"Sprint: {sprint['id']} | {sprint['title']} | status={sprint['status']}")
        for task in sprint_tasks:
            lines.append(
                f"- {task['id']} | {task['task_type']} | {task['title']} | status={task['status']} | "
                f"runs={task['runs']} | "
                f"tokens={task['tokens']} | "
                f"cost_usd={format_usd(task['cost_usd'])}"
            )
            for ref in task["rests_on"] if getattr(args, "rests_on", None) else ():
                lines.append(
                    f"    rests on {ref['path']}{'#' + ref['heading'] if ref['heading'] else ''}"
                    f" (named at {ref['commit'][:10]})"
                )

    print_lines(*lines)
    return 0
