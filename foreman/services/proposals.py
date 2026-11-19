"""The manager's proposals as a person sees and decides them (ADR-0022).
"""

from __future__ import annotations

from typing import Any

from ..manager.proposals import (
    PROPOSAL_PAGE_LIMIT,
    ProposalError,
    ProposalNotFound,
    Proposals,
    read_proposals,
    serialize_proposal,
)
from .base import Service
from .errors import NotFoundError, InvalidRequestError


class ProposalService(Service):
    """The manager's proposals as a person sees and decides them (ADR-0022)."""

    def list_proposals(
        self,
        project_id: str,
        *,
        states: list[str] | None = None,
        limit: int = PROPOSAL_PAGE_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        """One page of a project's proposals, newest first."""

        project = self._require_project(project_id)
        try:
            return read_proposals(self.store, project, states=states, limit=limit, offset=offset)
        except ProposalError as exc:
            raise InvalidRequestError(str(exc), field="state") from exc

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            raise NotFoundError(f"Proposal not found: {proposal_id}")
        return serialize_proposal(proposal)

    def confirm_proposal(
        self, proposal_id: str, *, requested_by: str | None = None
    ) -> dict[str, Any]:
        """Apply a proposal as the person confirming it; ``failed`` when one operation is refused."""

        return self._decide_proposal(proposal_id, "confirm", requested_by)

    def decline_proposal(
        self, proposal_id: str, *, requested_by: str | None = None
    ) -> dict[str, Any]:
        return self._decide_proposal(proposal_id, "decline", requested_by)

    def _decide_proposal(
        self, proposal_id: str, decision: str, requested_by: str | None
    ) -> dict[str, Any]:
        proposals = Proposals(
            self.store,
            via="dashboard",
            actor=(requested_by or "").strip() or None,
            now=self._now,
        )
        try:
            proposal = (
                proposals.confirm(proposal_id)
                if decision == "confirm"
                else proposals.decline(proposal_id)
            )
        except ProposalNotFound as exc:
            raise NotFoundError(str(exc)) from exc
        except ProposalError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return serialize_proposal(proposal)
