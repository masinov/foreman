"""The roles and workflows Foreman ships with."""

from __future__ import annotations

import argparse
import sys

from ..roles import RoleLoadError, default_roles_dir, load_roles
from ..workflows import WorkflowLoadError, default_workflows_dir, load_workflows

from .common import (
    print_lines,
    role_outcomes,
    set_handler,
)


def handle_roles(_: argparse.Namespace) -> int:
    """Handle ``foreman roles``."""

    roles_dir = default_roles_dir()
    try:
        roles = load_roles(roles_dir)
    except RoleLoadError as exc:
        print(f"Failed to load roles: {exc}", file=sys.stderr)
        return 1

    lines = ["Roles", f"Directory: {roles_dir}"]
    for role in roles.values():
        model = role.agent.model or "project-default"
        persistence = "persistent" if role.agent.session_persistence else "ephemeral"
        lines.append(
            f"{role.id} | backend={role.agent.backend} | model={model} | session={persistence}"
        )
    print_lines(*lines)
    return 0


def handle_workflows(_: argparse.Namespace) -> int:
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

    lines = ["Workflows", f"Directory: {workflows_dir}"]
    for workflow in workflows.values():
        fallback_action = workflow.fallback.action if workflow.fallback else "none"
        lines.append(
            f"{workflow.id} | methodology={workflow.methodology} | "
            f"entry={workflow.entry_step} | steps={len(workflow.steps)} | "
            f"transitions={len(workflow.transitions)} | gates={len(workflow.gates)} | "
            f"fallback={fallback_action}"
        )
    print_lines(*lines)
    return 0


def register_roles(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman roles` to the parser."""

    roles_parser = subparsers.add_parser("roles", help="List available roles.")
    set_handler(roles_parser, handle_roles, "roles")



def register_workflows(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman workflows` to the parser."""

    workflows_parser = subparsers.add_parser(
        "workflows",
        help="List available workflows.",
    )
    set_handler(workflows_parser, handle_workflows, "workflows")

