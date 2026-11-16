"""A workflow that starts with a plan and a gate, for tests.

Foreman shipped this workflow and its architect role until planning became
the manager's (ADR-0022, amendment of 2026-11-16). The engine still has to
run a workflow whose first step is an agent that is not the developer and
whose second is a gate, so the pair lives on here and a test gives it to its
project the way any project gets definitions of its own (ADR-0024).
"""

from __future__ import annotations

from pathlib import Path

from foreman.definitions import save_role, save_workflow

PLAN_WORKFLOW = "development_with_architect"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "definitions"
ARCHITECT_TOML = FIXTURES / "architect.toml"
PLAN_WORKFLOW_TOML = FIXTURES / "development_with_architect.toml"


def install_plan_workflow(store, project_id: str) -> None:
    """Give one project the architect role and the workflow that uses it."""

    save_role(store, project_id, ARCHITECT_TOML.read_text(encoding="utf-8"), changed_by="test")
    save_workflow(store, project_id, PLAN_WORKFLOW_TOML.read_text(encoding="utf-8"), changed_by="test")
