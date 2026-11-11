"""Read-only views of what is happening: status, board, watch, cost, history, transcript."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
import time
from typing import Callable

from ..dashboard_service import STREAM_POLL_INTERVAL_SECONDS
from ..engine_control import (
    blocked_kind,
    blocked_kind_counts,
    resolve_gate_steps,
)
from ..models import Event
from ..store import ForemanStore

from .common import (
    DB_OPTION_NOTE,
    add_db_option,
    format_idle_timeout,
    format_step_visits,
    format_task_counts,
    format_transcript_payload,
    format_usd,
    format_watch_activity_totals,
    indent_lines,
    print_lines,
    print_stream_lines,
    render_board_task_line,
    render_event_line,
    resolve_db_path_or_print,
    set_handler,
    token_split_parts,
    truncate_text,
)


BOARD_STATUS_SECTIONS: tuple[tuple[str, str], ...] = (
    ("triage", "Triage"),
    ("todo", "Todo"),
    ("in_progress", "In Progress"),
    ("blocked", "Blocked"),
    ("done", "Done"),
    ("cancelled", "Cancelled"),
)
WATCH_STREAM_BATCH_LIMIT = 100


@dataclass(frozen=True)
class WatchStreamPlan:
    """Resolved watch scope plus the functions needed to tail it."""

    header_lines: tuple[str, ...]
    recent_events: tuple[Event, ...]
    fetch_events: Callable[[str | None, int], list[Event]]


def _build_run_watch_plan(store: ForemanStore, run_id: str, *, limit: int) -> WatchStreamPlan | None:
    run = store.get_run(run_id)
    if run is None:
        return None

    task = store.get_task(run.task_id)
    project = store.get_project(run.project_id)
    header_lines = (
        f"Database: {store.db_path}",
        f"Scope: run {run.id}",
        f"Project: {run.project_id} | {project.name if project is not None else 'unknown'}",
        f"Task: {run.task_id} | {task.title if task is not None else 'unknown'}",
        f"Run: status={run.status} | step={run.workflow_step} | role={run.role_id}",
    )
    return WatchStreamPlan(
        header_lines=header_lines,
        recent_events=tuple(store.list_recent_events(run_id=run.id, limit=limit)),
        fetch_events=lambda after_event_id, batch_limit: store.list_events(
            run_id=run.id,
            after_event_id=after_event_id,
            limit=batch_limit,
        ),
    )


def _build_sprint_watch_plan(store: ForemanStore, sprint_id: str, *, limit: int) -> WatchStreamPlan | None:
    sprint = store.get_sprint(sprint_id)
    if sprint is None:
        return None

    project = store.get_project(sprint.project_id)
    counts = store.task_counts(sprint_id=sprint.id)
    totals = store.run_totals(project_id=sprint.project_id, sprint_id=sprint.id)
    header_lines = (
        f"Database: {store.db_path}",
        f"Scope: sprint {sprint.id}",
        f"Project: {sprint.project_id} | {project.name if project is not None else 'unknown'}",
        f"Sprint: {sprint.id} | {sprint.title}",
        format_task_counts(counts),
        format_watch_activity_totals(totals),
    )
    return WatchStreamPlan(
        header_lines=header_lines,
        recent_events=tuple(store.list_recent_sprint_events(sprint.id, limit=limit)),
        fetch_events=lambda after_event_id, batch_limit: store.list_sprint_events(
            sprint.id,
            after_event_id=after_event_id,
            limit=batch_limit,
        ),
    )


def _build_project_watch_plan(store: ForemanStore, project_id: str, *, limit: int) -> WatchStreamPlan | None:
    project = store.get_project(project_id)
    if project is None:
        return None

    active_sprint = store.get_active_sprint(project.id)
    header_lines = [
        f"Database: {store.db_path}",
        f"Scope: project {project.id}",
        f"Project: {project.id} | {project.name}",
    ]

    if active_sprint is not None:
        counts = store.task_counts(sprint_id=active_sprint.id)
        totals = store.run_totals(project_id=project.id, sprint_id=active_sprint.id)
        header_lines.extend(
            [
                f"Stream: active sprint {active_sprint.id} | {active_sprint.title}",
                format_task_counts(counts),
                format_watch_activity_totals(totals),
            ]
        )
        recent_events = tuple(store.list_recent_sprint_events(active_sprint.id, limit=limit))
        fetch_events = lambda after_event_id, batch_limit: store.list_sprint_events(
            active_sprint.id,
            after_event_id=after_event_id,
            limit=batch_limit,
        )
    else:
        counts = store.task_counts(project_id=project.id)
        totals = store.run_totals(project_id=project.id)
        header_lines.extend(
            [
                "Stream: project-wide persisted events",
                format_task_counts(counts),
                format_watch_activity_totals(totals),
            ]
        )
        recent_events = tuple(store.list_recent_events(project_id=project.id, limit=limit))
        fetch_events = lambda after_event_id, batch_limit: store.list_events(
            project_id=project.id,
            after_event_id=after_event_id,
            limit=batch_limit,
        )

    return WatchStreamPlan(
        header_lines=tuple(header_lines),
        recent_events=recent_events,
        fetch_events=fetch_events,
    )


def handle_board(args: argparse.Namespace) -> int:
    """Handle ``foreman board``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = store.get_project(args.project_id)
        if project is None:
            print(f"Unknown project: {args.project_id}", file=sys.stderr)
            return 1

        active_sprint = store.get_active_sprint(project.id)
        lines = [
            "Board",
            f"Database: {store.db_path}",
            f"Project: {project.id} | {project.name}",
        ]
        if active_sprint is None:
            lines.append("No active sprint for this project.")
            print_lines(*lines)
            return 0

        tasks = store.list_tasks(sprint_id=active_sprint.id)
        gates = resolve_gate_steps(project.workflow_id)
        blocked_counts = blocked_kind_counts(tasks, gates)
        counts = store.task_counts(sprint_id=active_sprint.id)
        totals = store.run_totals(project_id=project.id, sprint_id=active_sprint.id)
        task_totals = {
            str(row["task_id"]): row for row in store.task_run_totals(sprint_id=active_sprint.id)
        }
        task_count = sum(counts.values())

    lines.extend(
        [
            f"Sprint: {active_sprint.id} | {active_sprint.title}",
            f"Goal: {active_sprint.goal or 'n/a'}",
            (
                f"Progress: done={counts['done']}/{task_count} | "
                f"in_progress={counts['in_progress']} | "
                f"blocked={counts['blocked']} "
                f"(gate={blocked_counts['gate']} engine={blocked_counts['engine']}) | "
                f"todo={counts['todo']} | "
                f"triage={counts['triage']} | "
                f"cancelled={counts['cancelled']}"
            ),
            (
                f"Activity: runs={totals['run_count']} | "
                f"tokens={totals['total_token_count']} | "
                f"cost_usd={format_usd(float(totals['total_cost_usd']))}"
            ),
        ]
    )

    for status, label in BOARD_STATUS_SECTIONS:
        # `triage` and `cancelled` are exception states: show them only when a
        # project actually has work sitting there.
        if status in ("triage", "cancelled") and counts[status] == 0:
            continue
        lines.append(f"{label} ({counts[status]})")
        status_tasks = [task for task in tasks if task.status == status]
        if not status_tasks:
            lines.append("- none")
            continue
        for task in status_tasks:
            metrics = task_totals.get(task.id, {})
            details: list[str] = []
            token_count = int(metrics.get("total_token_count", 0))
            if token_count:
                details.append(f"tokens={token_count}")
            if task.branch_name:
                details.append(f"branch={task.branch_name}")
            if task.assigned_role:
                details.append(f"role={task.assigned_role}")
            if task.workflow_current_step:
                details.append(f"step={task.workflow_current_step}")
            if task.step_visit_counts:
                details.append(f"visits={format_step_visits(task.step_visit_counts)}")
            kind = blocked_kind(task, gates)
            if kind is not None:
                details.append(f"blocked_kind={kind}")
            if task.blocked_reason:
                details.append(f"reason={task.blocked_reason}")
            lines.append(render_board_task_line(task.id, task.title, task.task_type, details))

    print_lines(*lines)
    return 0


def handle_history(args: argparse.Namespace) -> int:
    """Handle ``foreman history``."""

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

    lines = [
        "History",
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
    if task.blocked_reason:
        lines.append(f"Blocked reason: {task.blocked_reason}")

    lines.append("Runs:")
    if not runs:
        lines.append("- none")
    else:
        for run in runs:
            parts = [
                run.id,
                f"role={run.role_id}",
                f"step={run.workflow_step}",
                f"backend={run.agent_backend}",
                f"status={run.status}",
                f"cost_usd={format_usd(run.cost_usd)}",
                f"tokens={run.token_count}",
                *token_split_parts(run.token_usage.as_dict()),
                f"duration_ms={run.duration_ms or 0}",
                f"retries={run.retry_count}",
            ]
            if run.outcome:
                parts.append(f"outcome={run.outcome}")
            if run.outcome_detail:
                parts.append(f"detail={truncate_text(run.outcome_detail)}")
            if run.model:
                parts.append(f"model={run.model}")
            if run.session_id:
                parts.append(f"session={run.session_id}")
            lines.append(f"- {' | '.join(parts)}")

    lines.append("Events:")
    if not events:
        lines.append("- none")
    else:
        for event in events:
            lines.append(
                f"- {render_event_line(event.event_type, event.timestamp, event.role_id, event.payload)}"
            )

    print_lines(*lines)
    return 0


def handle_transcript(args: argparse.Namespace) -> int:
    """Handle ``foreman transcript``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        run = store.get_run(args.run_id)
        if run is None:
            print(f"Unknown run: {args.run_id}", file=sys.stderr)
            return 1

        db_path = store.db_path
        task = store.get_task(run.task_id)
        project = store.get_project(run.project_id)
        events = store.list_events(run_id=run.id)

    lines = [
        "Transcript",
        f"Database: {db_path}",
        f"Run: {run.id}",
        f"Task: {run.task_id} | {task.title if task is not None else 'unknown'}",
        f"Project: {run.project_id} | {project.name if project is not None else 'unknown'}",
        (
            f"Role: {run.role_id} | step={run.workflow_step} | backend={run.agent_backend} | "
            f"status={run.status}"
        ),
    ]
    if run.outcome:
        lines.append(f"Outcome: {run.outcome}")
    if run.session_id:
        lines.append(f"Session: {run.session_id}")
    if run.model:
        lines.append(f"Model: {run.model}")
    if run.branch_name:
        lines.append(f"Branch: {run.branch_name}")
    if run.prompt_text and not any(event.event_type == "agent.prompt" for event in events):
        lines.append("Prompt (from run record):")
        lines.extend(indent_lines(run.prompt_text))

    lines.append("Events:")
    if not events:
        lines.append("- none")
    else:
        for event in events:
            header = f"- {event.timestamp} | {event.event_type}"
            if event.role_id:
                header += f" | role={event.role_id}"
            lines.append(header)
            lines.extend(format_transcript_payload(event))

    print_lines(*lines)
    return 0


def handle_cost(args: argparse.Namespace) -> int:
    """Handle ``foreman cost``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = store.get_project(args.project_id)
        if project is None:
            print(f"Unknown project: {args.project_id}", file=sys.stderr)
            return 1

        db_path = store.db_path
        sprint = None
        if args.sprint:
            sprint = store.get_sprint(args.sprint)
            if sprint is None:
                print(f"Unknown sprint: {args.sprint}", file=sys.stderr)
                return 1
            if sprint.project_id != project.id:
                print(
                    f"Sprint {sprint.id} does not belong to project {project.id}.",
                    file=sys.stderr,
                )
                return 1

        totals = store.run_totals(
            project_id=project.id,
            sprint_id=sprint.id if sprint is not None else None,
        )
        task_totals = store.task_run_totals(
            sprint_id=sprint.id if sprint is not None else None,
            project_id=None if sprint is not None else project.id,
        )

    lines = [
        "Cost",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        (
            f"Scope: sprint {sprint.id} | {sprint.title}"
            if sprint is not None
            else "Scope: project"
        ),
        (
            f"Totals: runs={totals['run_count']} | "
            f"tokens={totals['total_token_count']} | "
            f"cost_usd={format_usd(float(totals['total_cost_usd']))} | "
            f"duration_ms={totals['total_duration_ms']}"
        ),
        *(
            [f"Token split: {' | '.join(token_split_parts(totals.get('token_usage')))}"]
            if token_split_parts(totals.get("token_usage"))
            else []
        ),
        "By task:",
    ]
    if not task_totals:
        lines.append("- none")
    else:
        for row in task_totals:
            lines.append(
                "- "
                f"{row['task_id']} | {row['task_type']} | {row['task_title']} | "
                f"status={row['task_status']} | runs={row['run_count']} | "
                f"tokens={row['total_token_count']} | "
                f"cost_usd={format_usd(float(row['total_cost_usd']))}"
            )
    if int(totals["zero_cost_token_runs"]) > 0:
        lines.append(
            "Note: some runs reported token usage with $0.00 cost; persisted USD totals do not infer missing backend pricing."
        )

    print_lines(*lines)
    return 0


def handle_watch(args: argparse.Namespace) -> int:
    """Handle ``foreman watch``."""

    scope_count = sum(
        1
        for value in (
            args.project_id,
            args.run,
            args.sprint,
        )
        if value is not None
    )
    if scope_count != 1:
        print("Provide exactly one watch scope: project_id, --sprint, or --run.", file=sys.stderr)
        return 1
    if args.idle_timeout is not None and args.idle_timeout < 0:
        print("--idle-timeout must be zero or greater.", file=sys.stderr)
        return 1
    if args.limit < 1:
        print("--limit must be at least 1.", file=sys.stderr)
        return 1

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        if args.run:
            plan = _build_run_watch_plan(store, args.run, limit=args.limit)
            if plan is None:
                print(f"Unknown run: {args.run}", file=sys.stderr)
                return 1
        elif args.sprint:
            plan = _build_sprint_watch_plan(store, args.sprint, limit=args.limit)
            if plan is None:
                print(f"Unknown sprint: {args.sprint}", file=sys.stderr)
                return 1
        else:
            plan = _build_project_watch_plan(store, args.project_id, limit=args.limit)
            if plan is None:
                print(f"Unknown project: {args.project_id}", file=sys.stderr)
                return 1

        print_stream_lines(
            "Watch",
            *plan.header_lines,
            f"Delivery: recent {args.limit} persisted events followed by live updates",
            f"Exit: {format_idle_timeout(args.idle_timeout)}",
            "Recent activity:",
        )
        if not plan.recent_events:
            print_stream_lines("- none")
        else:
            for event in plan.recent_events:
                print_stream_lines(
                    f"- {render_event_line(event.event_type, event.timestamp, event.role_id, event.payload)}"
                )

        last_event_id = plan.recent_events[-1].id if plan.recent_events else None
        last_activity_at = time.monotonic()
        # Only run the event query when another connection (the engine) has
        # committed since the last tick; PRAGMA data_version is the cheap check.
        last_data_version: int | None = None
        try:
            while True:
                data_version = store.data_version()
                if data_version == last_data_version:
                    now = time.monotonic()
                    if args.idle_timeout is not None and now - last_activity_at >= args.idle_timeout:
                        if args.idle_timeout > 0:
                            print_stream_lines(
                                f"Watch ended after {args.idle_timeout:.1f}s without new activity."
                            )
                        return 0
                    time.sleep(STREAM_POLL_INTERVAL_SECONDS)
                    continue
                last_data_version = data_version
                recent_events = plan.fetch_events(last_event_id, WATCH_STREAM_BATCH_LIMIT)
                now = time.monotonic()
                if recent_events:
                    for event in recent_events:
                        print_stream_lines(
                            f"- {render_event_line(event.event_type, event.timestamp, event.role_id, event.payload)}"
                        )
                        last_event_id = event.id
                    last_activity_at = now
                    continue
                if args.idle_timeout is not None and now - last_activity_at >= args.idle_timeout:
                    if args.idle_timeout > 0:
                        print_stream_lines(
                            f"Watch ended after {args.idle_timeout:.1f}s without new activity."
                        )
                    return 0
                time.sleep(STREAM_POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print_stream_lines("Watch interrupted.")
            return 0

    return 0


def handle_status(args: argparse.Namespace) -> int:
    """Handle ``foreman status``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project_count = store.count_projects()
        active_sprint_count = store.count_active_sprints()
        task_counts = store.task_counts()
        # Blocked splits by workflow, so the kinds are counted per project and
        # summed: "12 blocked" is not actionable, "10 waiting on me, 2 dead
        # letters" is.
        blocked_counts = {"gate": 0, "engine": 0}
        for project in store.list_projects():
            gates = resolve_gate_steps(project.workflow_id)
            project_counts = blocked_kind_counts(
                store.list_tasks(project_id=project.id, status="blocked"), gates
            )
            for kind, value in project_counts.items():
                blocked_counts[kind] += value

    lines = ["Status", f"Database: {store.db_path}"]
    if active_sprint_count == 0:
        lines.append("No active projects or sprints.")
    lines.extend(
        [
            f"Projects: {project_count}",
            f"Active sprints: {active_sprint_count}",
            format_task_counts(task_counts),
            (
                f"Blocked: gate={blocked_counts['gate']} "
                f"engine={blocked_counts['engine']}"
            ),
        ]
    )
    print_lines(*lines)
    return 0


def register_status(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman status` to the parser."""

    status_parser = subparsers.add_parser(
        "status",
        help="Show a cross-project status overview.",
    )
    add_db_option(status_parser)
    set_handler(status_parser, handle_status, "status")



def register_board(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman board` to the parser."""

    board_parser = subparsers.add_parser("board", help="Show a terminal task board.")
    board_parser.add_argument("project_id", help="Project identifier.")
    add_db_option(
        board_parser,
        help_text=f"Path to the SQLite store containing the project board state. {DB_OPTION_NOTE}",
    )
    set_handler(board_parser, handle_board, "board")



def register_watch(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman watch` to the parser."""

    watch_parser = subparsers.add_parser("watch", help="Tail project, sprint, or run events.")
    watch_parser.add_argument("project_id", nargs="?", help="Project identifier.")
    watch_parser.add_argument("--run", help="Run identifier.")
    watch_parser.add_argument("--sprint", help="Sprint identifier.")
    watch_parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum number of recent persisted events to show before live tailing.",
    )
    watch_parser.add_argument(
        "--idle-timeout",
        type=float,
        help="Exit after this many idle seconds without new events. Omit to keep tailing until interrupted.",
    )
    add_db_option(
        watch_parser,
        help_text=f"Path to the SQLite store containing project or run activity. {DB_OPTION_NOTE}",
    )
    set_handler(watch_parser, handle_watch, "watch")



def register_cost(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman cost` to the parser."""

    cost_parser = subparsers.add_parser("cost", help="Show project cost totals.")
    cost_parser.add_argument("project_id", help="Project identifier.")
    cost_parser.add_argument("--sprint", help="Sprint identifier.")
    add_db_option(
        cost_parser,
        help_text=f"Path to the SQLite store containing project run totals. {DB_OPTION_NOTE}",
    )
    set_handler(cost_parser, handle_cost, "cost")



def register_history(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman history` to the parser."""

    history_parser = subparsers.add_parser(
        "history",
        help="Show run and event history for a task.",
    )
    history_parser.add_argument("task_id", help="Task identifier.")
    add_db_option(
        history_parser,
        help_text=f"Path to the SQLite store containing task history. {DB_OPTION_NOTE}",
    )
    set_handler(history_parser, handle_history, "history")



def register_transcript(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman transcript` to the parser."""

    transcript_parser = subparsers.add_parser(
        "transcript",
        help="Show the full persisted transcript for one run.",
    )
    transcript_parser.add_argument("run_id", help="Run identifier.")
    add_db_option(
        transcript_parser,
        help_text=f"Path to the SQLite store containing the run transcript. {DB_OPTION_NOTE}",
    )
    set_handler(transcript_parser, handle_transcript, "transcript")

