"""Proposals: changes the manager proposes and a person confirms (ADR-0022)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Sequence

from ..models import Proposal
from .base import StoreBase

_COLUMNS = (
    "id, project_id, proposed_by, session_id, turn_id, reason, operations_json, "
    "leaves_json, names_json, state, created_at, decided_by, decided_at, outcome_json"
)


def _row_to_proposal(row: sqlite3.Row) -> Proposal:
    return Proposal(
        id=row["id"],
        project_id=row["project_id"],
        proposed_by=row["proposed_by"],
        session_id=row["session_id"],
        turn_id=row["turn_id"],
        reason=row["reason"],
        operations=json.loads(row["operations_json"] or "[]"),
        leaves=json.loads(row["leaves_json"] or "[]"),
        names=json.loads(row["names_json"] or "{}"),
        state=row["state"],
        created_at=row["created_at"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
        outcome=json.loads(row["outcome_json"] or "{}"),
    )


class ProposalStore(StoreBase):
    """Proposals for a project, newest first."""

    def save_proposal(self, proposal: Proposal) -> Proposal:
        """Insert or replace one proposal."""

        values = (
            proposal.id,
            proposal.project_id,
            proposal.proposed_by,
            proposal.session_id,
            proposal.turn_id,
            proposal.reason,
            json.dumps(proposal.operations),
            json.dumps(proposal.leaves),
            json.dumps(proposal.names, sort_keys=True),
            proposal.state,
            proposal.created_at,
            proposal.decided_by,
            proposal.decided_at,
            json.dumps(proposal.outcome, sort_keys=True),
        )

        def _write(connection: sqlite3.Connection) -> None:
            connection.execute(
                f"INSERT OR REPLACE INTO proposals ({_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )

        self._write(_write)
        return proposal

    def get_proposal(self, proposal_id: str) -> Proposal | None:
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
        return _row_to_proposal(row) if row is not None else None

    def page_proposals(
        self,
        project_id: str,
        *,
        states: Sequence[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[Proposal], int]:
        """Return one page of a project's proposals, newest first, and the total."""

        where = "project_id = ?"
        params: list[Any] = [project_id]
        if states:
            where += f" AND state IN ({', '.join('?' for _ in states)})"
            params.extend(states)
        total = int(
            self._connection.execute(
                f"SELECT COUNT(*) FROM proposals WHERE {where}", tuple(params)
            ).fetchone()[0]
        )
        page_clause = ""
        page_params: list[Any] = []
        if limit is not None:
            page_clause = " LIMIT ? OFFSET ?"
            page_params = [limit, offset]
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM proposals WHERE {where} "
            f"ORDER BY created_at DESC, id DESC{page_clause}",
            tuple(params + page_params),
        ).fetchall()
        return [_row_to_proposal(row) for row in rows], total

    def list_turn_proposals(self, turn_id: str) -> list[Proposal]:
        """Return the proposals made during one manager turn, oldest first."""

        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM proposals WHERE turn_id = ? ORDER BY created_at, id",
            (turn_id,),
        ).fetchall()
        return [_row_to_proposal(row) for row in rows]
