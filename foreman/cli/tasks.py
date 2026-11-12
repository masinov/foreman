"""Tasks: add, show, list, override, block, unblock, accept, cancel."""

from __future__ import annotations

import argparse
import json
import sys

from ..engine_control import (
    blocked_kind,
    resolve_gate_steps,
)
from ..models import GATE_POLICY_NAMES, TASK_COMPLEXITIES, TASK_TYPES, Task
from ..mutations import MutationError
from ..policy import POLICY_VALUES, is_valid_value
from ..store import ForemanStore

from .common import (
    BLOCKED_KIND_HINTS,
    DB_OPTION_NOTE,
    add_db_option,
    add_json_option,
    allocate_entity_id,
    cli_mutations,
    format_step_visits,
    format_usd,
    next_order_index,
    print_json,
    print_lines,
    project_workflow_step_ids,
    render_event_line,
    resolve_db_path_or_print,
    resolve_project_or_print,
    resolve_task_or_print,
    select_task_creation_sprint,
    set_handler,
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
        task, resolve_gate_steps(project.workflow_id if project is not None else None)
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


def handle_task_add(args: argparse.Namespace) -> int:
    """Handle ``foreman task add``."""

    if args.task_type not in TASK_TYPES:
        print(
            f"Unsupported task type: {args.task_type}. Expected one of: {', '.join(TASK_TYPES)}.",
            file=sys.stderr,
        )
        return 1

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        sprint_id = getattr(args, "sprint_id", None)
        if sprint_id:
            sprint = store.get_sprint(sprint_id)
            if sprint is None or sprint.project_id != project.id:
                print(
                    f"Sprint {sprint_id} not found in project {project.id}.",
                    file=sys.stderr,
                )
                return 1
            if sprint.is_backlog:
                print(
                    f"{sprint_id} is the backlog, not a sprint. File work into it with "
                    f"`foreman backlog add {project.id}`.",
                    file=sys.stderr,
                )
                return 1
        else:
            sprint = select_task_creation_sprint(store, project.id)
            if sprint is None:
                print(
                    f"Project {project.id} has no active or planned sprint. Create one with `foreman sprint add` first.",
                    file=sys.stderr,
                )
                return 1

        depends_on_ids: list[str] = []
        raw_depends = getattr(args, "depends_on", None)
        if raw_depends:
            for dep_id in (part.strip() for part in raw_depends.split(",")):
                if not dep_id:
                    continue
                dep_task = store.get_task(dep_id)
                if dep_task is None or dep_task.project_id != project.id:
                    print(
                        f"Dependency task {dep_id} not found in project {project.id}.",
                        file=sys.stderr,
                    )
                    return 1
                if dep_id not in depends_on_ids:
                    depends_on_ids.append(dep_id)

        existing_tasks = store.list_tasks(sprint_id=sprint.id)
        task = Task(
            id=allocate_entity_id("task", args.title, exists=store.get_task),
            sprint_id=sprint.id,
            project_id=project.id,
            title=args.title,
            description=getattr(args, "description", None),
            task_type=args.task_type,
            acceptance_criteria=args.criteria,
            depends_on_task_ids=depends_on_ids,
            complexity=getattr(args, "complexity", None),
            order_index=next_order_index([item.order_index for item in existing_tasks]),
        )
        store.save_task(task)
        db_path = store.db_path

    print_lines(
        "Created task",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Sprint: {sprint.id} | {sprint.title}",
        f"Task: {task.id} | {task.title}",
        f"Type: {task.task_type}",
        f"Criteria: {task.acceptance_criteria or 'n/a'}",
        f"Depends on: {', '.join(task.depends_on_task_ids) if task.depends_on_task_ids else 'none'}",
        f"Complexity: {task.complexity or 'n/a'}",
        f"Status: {task.status}",
    )
    return 0


def handle_task_override(args: argparse.Namespace) -> int:
    """Handle ``foreman task override``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = store.get_task(args.task_id)
        if task is None:
            print(f"Unknown task: {args.task_id}", file=sys.stderr)
            return 1

        project = store.get_project(task.project_id)
        if project is None:
            print(f"Unknown project: {task.project_id}", file=sys.stderr)
            return 1

        valid_steps = project_workflow_step_ids(store, project)
        if valid_steps is None:
            return 1

        if args.clear:
            overrides: dict[str, object] = {}
        else:
            overrides = dict(task.executor_overrides or {})
            models = dict(overrides.get("models") or {})
            for raw in args.step_models:
                if "=" not in raw:
                    print(
                        f"Invalid --step value {raw!r}; expected STEP=MODEL.",
                        file=sys.stderr,
                    )
                    return 1
                step, model = raw.split("=", 1)
                step = step.strip()
                model = model.strip()
                if step not in valid_steps:
                    print(
                        f"Unknown workflow step {step!r}. Valid steps: "
                        f"{', '.join(sorted(valid_steps))}.",
                        file=sys.stderr,
                    )
                    return 1
                if not model:
                    models.pop(step, None)
                else:
                    models[step] = model
            if models:
                overrides["models"] = models
            else:
                overrides.pop("models", None)
            if args.ladder_start is not None:
                overrides["ladder_start"] = args.ladder_start
            gates = dict(overrides.get("gates") or {})
            for raw in args.gate_policies:
                if "=" not in raw:
                    print(
                        f"Invalid --gate value {raw!r}; expected POLICY=auto|human.",
                        file=sys.stderr,
                    )
                    return 1
                policy, decision = (part.strip() for part in raw.split("=", 1))
                if policy not in GATE_POLICY_NAMES:
                    print(
                        f"Unknown gate policy {policy!r}. Valid policies: "
                        f"{', '.join(sorted(GATE_POLICY_NAMES))}.",
                        file=sys.stderr,
                    )
                    return 1
                if not decision:
                    gates.pop(policy, None)
                elif decision not in ("auto", "human"):
                    print(
                        f"Gate policy {policy!r} must be 'auto' or 'human', got {decision!r}.",
                        file=sys.stderr,
                    )
                    return 1
                else:
                    gates[policy] = decision
            if gates:
                overrides["gates"] = gates
            else:
                overrides.pop("gates", None)

            policy = dict(overrides.get("policy") or {})
            for decision, raw_value in (
                ("triage", args.triage),
                ("notification", args.notification),
            ):
                if raw_value is None:
                    continue
                if not raw_value:
                    policy.pop(decision, None)
                elif not is_valid_value(decision, raw_value):
                    print(
                        f"Policy {decision!r} must be one of "
                        f"{', '.join(POLICY_VALUES[decision])}, got {raw_value!r}.",
                        file=sys.stderr,
                    )
                    return 1
                else:
                    policy[decision] = raw_value
            if policy:
                overrides["policy"] = policy
            else:
                overrides.pop("policy", None)

        task.executor_overrides = overrides
        store.save_task(task)
        db_path = store.db_path

    print_lines(
        "Updated task executor overrides",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Overrides: {json.dumps(task.executor_overrides, sort_keys=True)}",
    )
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


def handle_task_block(args: argparse.Namespace) -> int:
    """Handle ``foreman task block``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        try:
            cli_mutations(store).block_task(task, args.reason)
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Blocked task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
        f"Reason: {task.blocked_reason}",
    )
    return 0


def handle_task_unblock(args: argparse.Namespace) -> int:
    """Handle ``foreman task unblock``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        try:
            cli_mutations(store).unblock_task(task)
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Unblocked task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
        "Step visits reset: yes",
    )
    return 0


def handle_task_accept(args: argparse.Namespace) -> int:
    """Handle ``foreman task accept``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        try:
            cli_mutations(store).accept_task(task)
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Accepted task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
    )
    return 0


def handle_task_cancel(args: argparse.Namespace) -> int:
    """Handle ``foreman task cancel``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        try:
            removal = cli_mutations(store).cancel_task(task)
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        removed_worktree = removal.removed_worktree
        if removal.warning is not None:
            print(removal.warning, file=sys.stderr)
        db_path = store.db_path

    print_lines(
        "Cancelled task",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Status: {task.status}",
        f"Completed at: {task.completed_at}",
        *([f"Removed worktree: {removed_worktree}"] if removed_worktree else []),
    )
    return 0


def register_task(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman task` to the parser."""

    task_parser = subparsers.add_parser(
        "task",
        help="Manage tasks.",
    )
    task_commands = task_parser.add_subparsers(
        dest="task_command",
        metavar="task_command",
        required=True,
    )
    task_add = task_commands.add_parser("add", help="Create a task.")
    task_add.add_argument("project_id", help="Project identifier.")
    task_add.add_argument("--title", required=True, help="Task title.")
    task_add.add_argument("--type", dest="task_type", default="feature", help="Task type.")
    task_add.add_argument("--criteria", required=True, help="Acceptance criteria.")
    task_add.add_argument("--description", help="Task description.")
    task_add.add_argument(
        "--sprint",
        dest="sprint_id",
        metavar="SPRINT_ID",
        help="Target sprint id. Defaults to the active sprint, else the first planned sprint.",
    )
    task_add.add_argument(
        "--depends-on",
        dest="depends_on",
        metavar="TASK_IDS",
        help="Comma-separated task ids this task depends on (must exist in the same project).",
    )
    task_add.add_argument(
        "--complexity",
        choices=TASK_COMPLEXITIES,
        help="Optional architect-style complexity hint used for model-ladder start selection.",
    )
    add_db_option(
        task_add,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(task_add, handle_task_add, "task add")

    task_override = task_commands.add_parser(
        "override",
        help="Set per-task executor model overrides for workflow steps.",
    )
    task_override.add_argument("task_id", help="Task identifier.")
    task_override.add_argument(
        "--step",
        dest="step_models",
        action="append",
        metavar="STEP=MODEL",
        default=[],
        help="Pin a model for one workflow step (repeatable), e.g. --step develop=MiniMax-M2.",
    )
    task_override.add_argument(
        "--ladder-start",
        dest="ladder_start",
        type=int,
        help="Override the model-ladder start index for this task.",
    )
    task_override.add_argument(
        "--gate",
        dest="gate_policies",
        action="append",
        metavar="POLICY=auto|human",
        default=[],
        help=(
            "Override a gate policy for this task (repeatable), e.g. "
            "--gate merge_approval=human. An empty value removes the override."
        ),
    )
    task_override.add_argument(
        "--triage",
        metavar="auto|human",
        help=(
            "Override the triage policy for this task. An empty value removes "
            "the override."
        ),
    )
    task_override.add_argument(
        "--notification",
        metavar="none|attention|all",
        help=(
            "Override the notification policy for this task. An empty value "
            "removes the override."
        ),
    )
    task_override.add_argument(
        "--clear",
        action="store_true",
        help="Reset all executor overrides for this task to empty.",
    )
    add_db_option(
        task_override,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_override, handle_task_override, "task override")

    task_list = task_commands.add_parser("list", help="List project tasks.")
    task_list.add_argument("project_id", help="Project identifier.")
    task_list.add_argument("--sprint", metavar="SPRINT_ID", help="Filter to a specific sprint.")
    add_db_option(
        task_list,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    add_json_option(task_list)
    set_handler(task_list, handle_task_list, "task list")

    task_show = task_commands.add_parser("show", help="Show one task with recent runs and events.")
    task_show.add_argument("task_id", help="Task identifier.")
    task_show.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of recent runs to include.",
    )
    task_show.add_argument(
        "--events",
        type=int,
        default=8,
        help="Number of recent events to include.",
    )
    add_db_option(
        task_show,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_show, handle_task_show, "task show")

    task_block = task_commands.add_parser("block", help="Block a task.")
    task_block.add_argument("task_id", help="Task identifier.")
    task_block.add_argument("--reason", required=True, help="Blocking reason.")
    add_db_option(
        task_block,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_block, handle_task_block, "task block")

    task_unblock = task_commands.add_parser("unblock", help="Unblock a task.")
    task_unblock.add_argument("task_id", help="Task identifier.")
    add_db_option(
        task_unblock,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_unblock, handle_task_unblock, "task unblock")

    task_accept = task_commands.add_parser(
        "accept", help="Accept a task out of triage into the runnable queue."
    )
    task_accept.add_argument("task_id", help="Task identifier.")
    add_db_option(
        task_accept,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_accept, handle_task_accept, "task accept")

    task_cancel = task_commands.add_parser("cancel", help="Cancel a task.")
    task_cancel.add_argument("task_id", help="Task identifier.")
    add_db_option(
        task_cancel,
        help_text=f"Path to the SQLite store containing the task. {DB_OPTION_NOTE}",
    )
    set_handler(task_cancel, handle_task_cancel, "task cancel")

