"""``foreman task add``, ``edit`` and ``override``: a task's fields, through ``foreman.mutations``.
"""

from __future__ import annotations

import argparse
import json
import sys

from ...domain.models import GATE_POLICY_NAMES, TASK_TYPES, Task
from ...domain.policy import POLICY_VALUES, is_valid_value
from ...mutations import MutationError
from ...store import ForemanStore
from ..common import (
    cli_mutations,
    print_lines,
    project_workflow_step_ids,
    resolve_db_path_or_print,
    resolve_project_or_print,
    resolve_task_or_print,
    select_task_creation_sprint,
)

from .texts import (
    TEXT_FIELDS,
    TextInputError,
    check_text_options,
    edit_in_editor,
    read_text_option,
    text_field,
)


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
        else:
            sprint = select_task_creation_sprint(store, project.id)
            if sprint is None:
                print(
                    f"Project {project.id} has no active or planned sprint. Create one with `foreman sprint add` first.",
                    file=sys.stderr,
                )
                return 1

        try:
            task = cli_mutations(store).add_task(
                sprint,
                title=args.title,
                task_type=args.task_type,
                description=getattr(args, "description", None),
                acceptance_criteria=args.criteria,
                rests_on=getattr(args, "rests_on", None),
                depends_on=(getattr(args, "depends_on", None) or "").split(","),
            )
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Created task",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Sprint: {sprint.id} | {sprint.title}",
        f"Task: {task.id} | {task.title}",
        f"Type: {task.task_type}",
        f"Criteria: {task.acceptance_criteria or 'n/a'}",
        *_rests_on_lines(task),
        f"Depends on: {', '.join(task.depends_on_task_ids) if task.depends_on_task_ids else 'none'}",
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
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
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
                overrides["ladder_start"] = (
                    int(args.ladder_start) if args.ladder_start.isdigit() else args.ladder_start
                )
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

        try:
            cli_mutations(store).edit_task(
                task, {"executor_overrides": overrides}, valid_steps=valid_steps
            )
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Updated task executor overrides",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        f"Overrides: {json.dumps(task.executor_overrides, sort_keys=True)}",
    )
    return 0


def handle_task_edit(args: argparse.Namespace) -> int:
    """Handle ``foreman task edit``."""

    changes: dict[str, object] = {}
    if args.title is not None:
        changes["title"] = args.title
    if args.task_type is not None:
        changes["task_type"] = args.task_type
    if args.priority is not None:
        changes["priority"] = args.priority
    if args.no_rests_on and args.rests_on:
        print("Give --rests-on or --no-rests-on, not both.", file=sys.stderr)
        return 1
    if args.no_rests_on:
        changes["rests_on"] = []
    elif args.rests_on:
        changes["rests_on"] = list(args.rests_on)
    if args.no_dependencies and args.depends_on:
        print("Give --depends-on or --no-dependencies, not both.", file=sys.stderr)
        return 1
    if args.no_dependencies:
        changes["depends_on_task_ids"] = []
    elif args.depends_on:
        changes["depends_on_task_ids"] = list(args.depends_on)
    try:
        check_text_options(args)
        for field in TEXT_FIELDS:
            text = read_text_option(field, args)
            if text is not None:
                changes[field.mutation_field] = text
    except TextInputError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    restamp = list(getattr(args, "restamp", None) or [])
    if not changes and args.edit is None and not restamp:
        print(
            "Nothing to change. Give --title, --type, --priority, --description, "
            "--criteria, --rests-on or --no-rests-on, --restamp, --depends-on or --no-dependencies, "
            "or --edit description|criteria.",
            file=sys.stderr,
        )
        return 1

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    unchanged: list[str] = []
    with ForemanStore(db_path) as store:
        store.initialize()
        task = resolve_task_or_print(store, args.task_id)
        if task is None:
            return 1
        before = {
            "title": task.title,
            "task_type": task.task_type,
            "description": task.description,
            "acceptance_criteria": task.acceptance_criteria,
            "priority": task.priority,
            "depends_on_task_ids": list(task.depends_on_task_ids or []),
            "rests_on": [ref.as_dict() for ref in task.rests_on],
        }
        if args.edit is not None:
            field = text_field(args.edit)
            try:
                edited = edit_in_editor(field, before[field.mutation_field])
            except TextInputError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            # Closing the editor with nothing, or nothing new, changes nothing.
            if not edited.strip() or edited.strip() == (before[field.mutation_field] or "").strip():
                unchanged.append(field.label)
            else:
                changes[field.mutation_field] = edited
        changed: dict[str, object] = {}
        try:
            if changes:
                changed = cli_mutations(store).edit_task(task, changes)
            for document in restamp:
                changed.update(cli_mutations(store).restamp_document(task, document))
        except MutationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        db_path = store.db_path

    print_lines(
        "Edited task" if changed else "Nothing changed",
        f"Database: {db_path}",
        f"Task: {task.id} | {task.title}",
        *(f"{label} unchanged." for label in unchanged),
        *_describe_changes(before, changed),
        *_rests_on_lines(task),
        f"Priority: {task.priority}",
        "Waits for: "
        + (", ".join(task.depends_on_task_ids) if task.depends_on_task_ids else "nothing"),
    )
    return 0


_CHANGE_LABELS = {
    "title": "Title",
    "task_type": "Type",
    "description": "Description",
    "acceptance_criteria": "Acceptance criteria",
    "rests_on": "Documents",
}
# Priority and what a task waits for are shown in full on the lines after.


def _rests_on_lines(task: Task) -> list[str]:
    """``Rests on:`` with each document and the commit it was named at."""

    if not task.rests_on:
        return ["Rests on: nothing named"]
    return ["Rests on:"] + [
        f"  {ref.label()} (named at {ref.commit[:10]})" for ref in task.rests_on
    ]


def _describe_changes(before: dict[str, object], changed: dict[str, object]) -> list[str]:
    """One short line per changed field; a long text is counted, never printed."""

    lines = []
    for field, label in _CHANGE_LABELS.items():
        if field not in changed:
            continue
        old, new = before[field], changed[field]
        if field == "rests_on":
            restamped = len(old) == len(new) and [
                (ref["path"], ref["heading"]) for ref in old
            ] == [(ref["path"], ref["heading"]) for ref in new]
            lines.append(
                f"{label}: marked as read again" if restamped else f"{label}: {len(old)} -> {len(new)} documents"
            )
        elif field in ("description", "acceptance_criteria"):
            if not new:
                lines.append(f"{label}: cleared")
            else:
                lines.append(f"{label}: {'set' if not old else 'changed'} ({len(str(new))} characters)")
        else:
            lines.append(f"{label}: {old or 'not said'} -> {new or 'not said'}")
    return lines
