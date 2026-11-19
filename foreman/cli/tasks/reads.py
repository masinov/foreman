"""``foreman task show`` and ``foreman task list``.
"""

from __future__ import annotations

import argparse
import json
import sys

from ...definitions.gate_steps import (
    blocked_kind,
    resolve_gate_steps,
)
from ...domain.models import Task
from ...store import ForemanStore
from ..common import (
    BLOCKED_KIND_HINTS,
    format_step_visits,
    format_usd,
    print_json,
    print_lines,
    render_event_line,
    resolve_db_path_or_print,
    resolve_project_or_print,
    truncate_text,
)


def handle_task_show(args: argparse.Namespace) -> int:
    """Handle ``foreman task show``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = store.get_task(args.task_id)
        if task is None:
            print(f"Unknown task: {args.task_id}", file=sys.stderr)
            return 1

        db_path = store.db_path
        project = store.get_project(task.project_id)
        sprint = store.get_sprint(task.sprint_id)
        runs = store.list_runs(task_id=task.id)
        events = store.list_events(task_id=task.id)
        totals = store.run_totals(task_id=task.id)

    latest_run = runs[-1] if runs else None
    active_run = next((run for run in reversed(runs) if run.status == "running"), None)
    latest_event = events[-1] if events else None
    kind = blocked_kind(
        task, resolve_gate_steps(store, project)
    )

    lines = [
        "Task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Project: {task.project_id} | {project.name if project is not None else 'unknown'}",
        f"Sprint: {task.sprint_id} | {sprint.title if sprint is not None else 'unknown'}",
        f"Status: {task.status} | type={task.task_type} | created_by={task.created_by}",
        (
            f"Totals: runs={totals['run_count']} | "
            f"tokens={totals['total_token_count']} | "
            f"cost_usd={format_usd(float(totals['total_cost_usd']))} | "
            f"duration_ms={totals['total_duration_ms']}"
        ),
        f"Step visits: {format_step_visits(task.step_visit_counts)}",
    ]
    if task.branch_name:
        lines.append(f"Branch: {task.branch_name}")
    if task.worktree_path:
        lines.append(f"Worktree: {task.worktree_path}")
    if task.assigned_role:
        lines.append(f"Assigned role: {task.assigned_role}")
    if task.workflow_current_step:
        lines.append(f"Current step: {task.workflow_current_step}")
    if task.complexity:
        lines.append(f"Complexity: {task.complexity}")
    if task.executor_overrides:
        lines.append(
            f"Executor overrides: {json.dumps(task.executor_overrides, sort_keys=True)}"
        )
    if kind is not None:
        lines.append(f"Blocked kind: {kind} ({BLOCKED_KIND_HINTS[kind]})")
    if task.blocked_reason:
        lines.append(f"Blocked reason: {task.blocked_reason}")

    if active_run is not None:
        lines.append(
            "Active run: "
            f"{active_run.id} | role={active_run.role_id} | step={active_run.workflow_step} | "
            f"status={active_run.status} | started_at={active_run.started_at or 'unknown'}"
        )
    else:
        lines.append("Active run: none")

    if latest_run is not None:
        latest_parts = [
            latest_run.id,
            f"role={latest_run.role_id}",
            f"step={latest_run.workflow_step}",
            f"status={latest_run.status}",
            f"cost_usd={format_usd(latest_run.cost_usd)}",
            f"tokens={latest_run.token_count}",
            f"duration_ms={latest_run.duration_ms or 0}",
        ]
        if latest_run.outcome:
            latest_parts.append(f"outcome={latest_run.outcome}")
        if latest_run.outcome_detail:
            latest_parts.append(f"detail={truncate_text(latest_run.outcome_detail)}")
        lines.append(f"Latest run: {' | '.join(latest_parts)}")
    else:
        lines.append("Latest run: none")

    if latest_event is not None:
        lines.append(
            "Latest event: "
            + render_event_line(
                latest_event.event_type,
                latest_event.timestamp,
                latest_event.role_id,
                latest_event.payload,
            )
        )
    else:
        lines.append("Latest event: none")

    lines.append("Recent runs:")
    recent_runs = runs[-max(args.runs, 0):] if args.runs > 0 else []
    if not recent_runs:
        lines.append("- none")
    else:
        for run in recent_runs:
            parts = [
                run.id,
                f"role={run.role_id}",
                f"step={run.workflow_step}",
                f"status={run.status}",
            ]
            if run.outcome:
                parts.append(f"outcome={run.outcome}")
            if run.outcome_detail:
                parts.append(f"detail={truncate_text(run.outcome_detail)}")
            lines.append(f"- {' | '.join(parts)}")

    lines.append("Recent events:")
    recent_events = events[-max(args.events, 0):] if args.events > 0 else []
    if not recent_events:
        lines.append("- none")
    else:
        for event in recent_events:
            lines.append(
                f"- {render_event_line(event.event_type, event.timestamp, event.role_id, event.payload)}"
            )

    print_lines(*lines)
    return 0


def handle_task_list(args: argparse.Namespace) -> int:
    """Handle ``foreman task list``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        sprint_filter = getattr(args, "sprint", None)
        sprints = store.list_sprints(project.id)
        if sprint_filter:
            sprints = [s for s in sprints if s.id == sprint_filter]
        sprint_ids = {s.id for s in sprints}
        tasks = store.list_tasks(project_id=project.id)
        tasks = [t for t in tasks if t.sprint_id in sprint_ids]
        totals_by_task = {
            str(row["task_id"]): row for row in store.task_run_totals(project_id=project.id)
        }
        tasks_by_sprint: dict[str, list[Task]] = {}
        for task in tasks:
            tasks_by_sprint.setdefault(task.sprint_id, []).append(task)
        if getattr(args, "as_json", False):
            print_json(
                {
                    "database": str(store.db_path),
                    "project_id": project.id,
                    "tasks": [
                        {
                            "id": task.id,
                            "key": task.task_key,
                            "sprint_id": task.sprint_id,
                            "title": task.title,
                            "task_type": task.task_type,
                            "status": task.status,
                            "blocked_reason": task.blocked_reason,
                            "branch_name": task.branch_name,
                            "workflow_current_step": task.workflow_current_step,
                            "runs": totals_by_task.get(task.id, {}).get("run_count", 0),
                            "tokens": totals_by_task.get(task.id, {}).get("total_token_count", 0),
                            "cost_usd": float(
                                totals_by_task.get(task.id, {}).get("total_cost_usd", 0.0)
                            ),
                        }
                        for sprint in sprints
                        for task in tasks_by_sprint.get(sprint.id, [])
                    ],
                }
            )
            return 0

        lines = [
            "Tasks",
            f"Database: {store.db_path}",
            f"Project: {project.id} | {project.name}",
        ]
        if not tasks:
            lines.append("No tasks are defined for this project.")
        else:
            for sprint in sprints:
                sprint_tasks = tasks_by_sprint.get(sprint.id, [])
                if not sprint_tasks:
                    continue
                lines.append(
                    f"Sprint: {sprint.id} | {sprint.title} | status={sprint.status}"
                )
                for task in sprint_tasks:
                    totals = totals_by_task.get(task.id, {})
                    lines.append(
                        f"- {task.id} | {task.task_type} | {task.title} | status={task.status} | "
                        f"runs={totals.get('run_count', 0)} | "
                        f"tokens={totals.get('total_token_count', 0)} | "
                        f"cost_usd={format_usd(float(totals.get('total_cost_usd', 0.0)))}"
                    )

    print_lines(*lines)
    return 0
