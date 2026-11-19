"""Decision gates: a question about a project's sprints raised for a person.

An agent that finds the sprint order in conflict raises a gate with the
order it suggests. Accepting it reorders the sprints; rejecting or
dismissing it closes it and changes nothing.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..domain.models import DecisionGate, Project, Sprint
from .base import MutationBase, MutationError

#: How a decision gate can be resolved.
GATE_RESOLUTIONS: tuple[str, ...] = ("accepted", "rejected", "dismissed")


class DecisionGateMutations(MutationBase):
    """Raising and resolving decision gates."""

    def raise_decision_gate(
        self,
        project: Project,
        sprint: Sprint,
        *,
        conflict_description: str,
        suggested_order: Sequence[str] = (),
        suggested_reason: str = "",
    ) -> DecisionGate:
        """Raise a gate about ``sprint``'s place in the project's order."""

        if sprint.project_id != project.id:
            raise MutationError("Sprint does not belong to this project.")
        description = (conflict_description or "").strip()
        if not description:
            raise MutationError("conflict_description cannot be empty.")
        now = self._now()
        gate = DecisionGate(
            id=f"gate-{now.strftime('%Y%m%d%H%M%S%f')}-{project.id[:8]}",
            project_id=project.id,
            sprint_id=sprint.id,
            conflict_description=description,
            suggested_order=list(suggested_order),
            suggested_reason=(suggested_reason or "").strip(),
            raised_at=now.isoformat(),
        )
        self.store.save_decision_gate(gate)
        return gate

    def resolve_decision_gate(
        self, gate: DecisionGate, resolution: str, *, resolved_by: str = "human"
    ) -> DecisionGate:
        """Close a pending gate; ``accepted`` applies its suggested sprint order."""

        if gate.status != "pending":
            raise MutationError(f"Gate is already resolved (status: {gate.status}).")
        if resolution not in GATE_RESOLUTIONS:
            raise MutationError(
                f"Invalid resolution '{resolution}'. Expected one of: {', '.join(GATE_RESOLUTIONS)}."
            )
        gate.status = resolution  # type: ignore[assignment]
        gate.resolved_at = self._now().isoformat()
        gate.resolved_by = resolved_by
        if resolution == "accepted":
            for index, sprint_id in enumerate(gate.suggested_order):
                sprint = self.store.get_sprint(sprint_id)
                if sprint is not None and sprint.project_id == gate.project_id:
                    sprint.order_index = index
                    self.store.save_sprint(sprint)
        self.store.save_decision_gate(gate)
        return gate
