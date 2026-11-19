"""The roles and workflows Foreman ships with."""

from __future__ import annotations

import argparse
import sys

from ..definitions.roles import RoleLoadError, default_roles_dir, load_roles
from ..definitions.workflows import (
    WorkflowLoadError,
    default_workflows_dir,
    load_workflows,
)
from .common import (
    add_json_option,
    print_json,
    print_lines,
    role_outcomes,
    set_handler,
)


def handle_roles(args: argparse.Namespace) -> int:
    """Handle ``foreman roles``."""

    roles_dir = default_roles_dir()
    try:
        roles = load_roles(roles_dir)
    except RoleLoadError as exc:
        print(f"Failed to load roles: {exc}", file=sys.stderr)
        return 1

    rows = [
        {
            "id": role.id,
            "backend": role.agent.backend,
            "model": role.agent.model or None,
            "session_persistence": role.agent.session_persistence,
        }
        for role in roles.values()
    ]
    if args.as_json:
        print_json({"directory": str(roles_dir), "roles": rows})
        return 0
    lines = ["Roles", f"Directory: {roles_dir}"]
    for row in rows:
        persistence = "persistent" if row["session_persistence"] else "ephemeral"
        lines.append(
            f"{row['id']} | backend={row['backend']} | model={row['model'] or 'project-default'}"
            f" | session={persistence}"
        )
    print_lines(*lines)
    return 0


def handle_workflows(args: argparse.Namespace) -> int:
    """Handle ``foreman workflows``."""

    roles_dir = default_roles_dir()
    workflows_dir = default_workflows_dir()
    try:
        roles = load_roles(roles_dir)
        workflows = load_workflows(
            workflows_dir,
            available_role_ids=set(roles),
            role_outcomes=role_outcomes(roles),
        )
    except (RoleLoadError, WorkflowLoadError) as exc:
        print(f"Failed to load workflows: {exc}", file=sys.stderr)
        return 1

    rows = [
        {
            "id": workflow.id,
            "methodology": workflow.methodology,
            "entry": workflow.entry_step,
            "steps": len(workflow.steps),
            "transitions": len(workflow.transitions),
            "gates": len(workflow.gates),
            "fallback": workflow.fallback.action if workflow.fallback else None,
        }
        for workflow in workflows.values()
    ]
    if args.as_json:
        print_json({"directory": str(workflows_dir), "workflows": rows})
        return 0
    lines = ["Workflows", f"Directory: {workflows_dir}"]
    for row in rows:
        lines.append(
            f"{row['id']} | methodology={row['methodology']} | "
            f"entry={row['entry']} | steps={row['steps']} | "
            f"transitions={row['transitions']} | gates={row['gates']} | "
            f"fallback={row['fallback'] or 'none'}"
        )
    print_lines(*lines)
    return 0


def register_roles(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman roles` to the parser."""

    roles_parser = subparsers.add_parser("roles", help="List available roles.")
    add_json_option(roles_parser)
    set_handler(roles_parser, handle_roles, "roles")



def register_workflows(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman workflows` to the parser."""

    workflows_parser = subparsers.add_parser(
        "workflows",
        help="List available workflows.",
    )
    add_json_option(workflows_parser)
    set_handler(workflows_parser, handle_workflows, "workflows")

