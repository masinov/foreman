"""Decision gates: a question raised for a person, and its answer.
"""

from __future__ import annotations

from typing import Any

from ..domain.models import (
    DecisionGate,
)
from ..mutations import MutationError
from .base import Service
from .errors import InvalidRequestError, NotFoundError


class DecisionGateService(Service):
    """Decision gates: a question raised for a person, and its answer."""

    def create_gate(
        self,
        project_id: str,
        *,
        sprint_id: str,
        conflict_description: str,
        suggested_order: list[str] | None = None,
        suggested_reason: str = "",
    ) -> dict[str, Any]:
        """Raise a new decision gate for a project."""

        project = self.store.get_project(project_id)
        if project is None:
            raise NotFoundError(f"Project not found: {project_id}")
        sprint = self.store.get_sprint(sprint_id)
        if sprint is None:
            raise NotFoundError(f"Sprint not found: {sprint_id}")
        try:
            gate = self._mutations().raise_decision_gate(
                project,
                sprint,
                conflict_description=conflict_description,
                suggested_order=suggested_order or [],
                suggested_reason=suggested_reason,
            )
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self._serialize_gate(gate)

    def list_gates(self, project_id: str, *, status: str | None = None) -> dict[str, Any]:
        """List decision gates for a project."""

        project = self.store.get_project(project_id)
        if project is None:
            raise NotFoundError(f"Project not found: {project_id}")
        gates = self.store.list_decision_gates(project_id, status=status)
        return {"gates": [self._serialize_gate(g) for g in gates]}

    def resolve_gate(self, gate_id: str, *, resolution: str, resolved_by: str = "human") -> dict[str, Any]:
        """Resolve a pending decision gate.

        resolution must be one of: accepted, rejected, dismissed.
        - accepted: applies suggested_order by rewriting order_index values on the sprints.
        - rejected / dismissed: no sprint reorder; gate is closed.
        """

        gate = self.store.get_decision_gate(gate_id)
        if gate is None:
            raise NotFoundError(f"Decision gate not found: {gate_id}")
        try:
            gate = self._mutations().resolve_decision_gate(gate, resolution, resolved_by=resolved_by)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self._serialize_gate(gate)

    @staticmethod
    def _serialize_gate(gate: DecisionGate) -> dict[str, Any]:
        return {
            "id": gate.id,
            "project_id": gate.project_id,
            "sprint_id": gate.sprint_id,
            "conflict_description": gate.conflict_description,
            "suggested_order": gate.suggested_order,
            "suggested_reason": gate.suggested_reason,
            "status": gate.status,
            "raised_at": gate.raised_at,
            "resolved_at": gate.resolved_at,
            "resolved_by": gate.resolved_by,
        }
