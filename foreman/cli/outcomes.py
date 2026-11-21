"""`foreman outcomes`: how well a project's agents do (ADR-0034)."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from ..services import Services
from ..services.errors import NotFoundError
from ..store import ForemanStore
from .common import (
    DB_OPTION_NOTE,
    add_db_option,
    add_json_option,
    format_usd,
    print_json,
    print_lines,
    resolve_db_path_or_print,
    set_handler,
    token_split_parts,
)


def _share(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)}%" if whole else "-"


def _named_counts(counts: dict[str, int], *, ids: bool = False) -> str:
    named = [(name if ids else name.replace("_", " "), count) for name, count in counts.items() if count]
    named.sort(key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{name} {count}" for name, count in named)


def _wait(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 120:
        return f"{seconds:.0f}s"
    if seconds < 7200:
        return f"{seconds / 60:.0f} min"
    return f"{seconds / 3600:.1f} h"


def outcome_lines(numbers: dict[str, Any]) -> list[str]:
    """The outcome numbers in plain lines, for a terminal."""

    tasks = numbers["tasks"]
    merged = tasks["merged"]
    lines = [
        (
            f"Tasks: {tasks['started']} started, {merged} merged, "
            f"{tasks['closed_by_hand']} closed by hand, {tasks['cancelled']} cancelled, "
            f"{tasks['not_finished']} not finished"
        ),
        (
            f"Passed first time: {tasks['passed_first_time']} of {merged} merged "
            f"({_share(tasks['passed_first_time'], merged)}); "
            f"{tasks['passed_first_time_conflicts_aside']} "
            f"({_share(tasks['passed_first_time_conflicts_aside'], merged)}) "
            "leaving merge conflicts aside"
        ),
    ]
    send_backs = numbers["send_backs"]
    total = sum(send_backs.values())
    detail = _named_counts(send_backs)
    reviewers = _named_counts(numbers["send_backs_by_reviewer"], ids=True)
    if reviewers:
        detail = f"{detail} (review: {reviewers})"
    lines.append(f"Send-backs: {total}" + (f": {detail}" if detail else ""))
    people = numbers["people"]
    asked = f"asked {people['decisions_asked']} times, median wait {_wait(people['median_wait_seconds'])}"
    if people["decisions_waiting"]:
        asked += f", {people['decisions_waiting']} waiting"
    unasked = f"stepped in unasked {people['interventions']} times"
    if people["interventions"]:
        unasked += f" ({_named_counts(people['interventions_by_kind'])})"
    lines.append(f"A user: {asked}; {unasked}")
    cost = numbers["cost"]
    per_task = cost["per_merged_task_usd"]
    lines.append(
        f"Cost: {format_usd(cost['total_usd'])} in all, "
        f"{format_usd(per_task) if per_task is not None else '-'} per merged task, "
        f"{format_usd(cost['not_merged_usd'])} on tasks not merged"
    )
    per_task_tokens = token_split_parts(cost["tokens_per_merged_task"])
    if per_task_tokens:
        lines.append(f"Tokens per merged task: {' | '.join(per_task_tokens)}")
    minutes = numbers["median_minutes_to_merge"]
    lines.append(f"Time to merge: median {minutes} min" if minutes is not None else "Time to merge: -")
    lines.append("By role and model:")
    rows = numbers["by_role_and_model"]
    if not rows:
        lines.append("- none")
    for row in rows:
        parts = [
            row["role"],
            row["model"] or "model unknown",
            f"runs={row['runs']}",
            f"failed={row['failed_runs']}",
        ]
        if row["tasks_built_merged"]:
            parts.append(
                f"built {row['tasks_built_merged']} merged, "
                f"{row['tasks_built_passed_first_time']} first time"
            )
        if row["send_backs_caused"]:
            parts.append(f"sent back {row['send_backs_caused']}")
        parts.append(format_usd(row["cost_usd"]))
        parts.extend(token_split_parts(row["tokens"]))
        lines.append("- " + " | ".join(parts))
    return lines


def handle_outcomes(args: argparse.Namespace) -> int:
    """Handle ``foreman outcomes``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1
    with ForemanStore(db_path) as store:
        store.initialize()
        project = store.get_project(args.project_id)
        if project is None:
            print(f"Unknown project: {args.project_id}", file=sys.stderr)
            return 1
        try:
            numbers = Services(store).outcomes.numbers(project.id, sprint_id=args.sprint)
        except NotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.as_json:
        print_json(numbers)
        return 0
    scope = (
        f"Scope: sprint {numbers['sprint_id']} | {numbers['sprint_title']}"
        if numbers["sprint_id"]
        else "Scope: project"
    )
    print_lines(
        "Outcomes",
        f"Project: {project.id} | {project.name}",
        scope,
        *outcome_lines(numbers),
    )
    return 0


def register_outcomes(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman outcomes` to the parser."""

    parser = subparsers.add_parser(
        "outcomes",
        help="Show how well a project's agents do: first-time passes, send-backs, a user's part, cost.",
    )
    parser.add_argument("project_id", help="Project identifier.")
    parser.add_argument("--sprint", help="Only the tasks of this sprint.")
    add_json_option(parser)
    add_db_option(
        parser,
        help_text=f"Path to the SQLite store containing the project's runs. {DB_OPTION_NOTE}",
    )
    set_handler(parser, handle_outcomes, "outcomes")
