"""Decision gates, human gate decisions and merge waivers."""

from __future__ import annotations


from ..models import (
    DecisionGate,
    HumanGateDecision,
    MergeWaiver,
    utc_now_text,
)

from .base import (
    StoreBase,
    retried_on_lock,
)
from .rows import (
    _row_to_gate,
    _row_to_human_gate_decision,
    _row_to_merge_waiver,
)


class GateStore(StoreBase):
    """Decision gates, human gate decisions and merge waivers."""

    @retried_on_lock
    def save_decision_gate(self, gate: DecisionGate) -> DecisionGate:
        """Insert or update a decision gate record."""
        import json as _json

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO decision_gates (
                    id, project_id, sprint_id, raised_at,
                    conflict_description, suggested_order, suggested_reason,
                    status, resolved_at, resolved_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    resolved_at = excluded.resolved_at,
                    resolved_by = excluded.resolved_by
                """,
                (
                    gate.id,
                    gate.project_id,
                    gate.sprint_id,
                    gate.raised_at,
                    gate.conflict_description,
                    _json.dumps(gate.suggested_order),
                    gate.suggested_reason,
                    gate.status,
                    gate.resolved_at,
                    gate.resolved_by,
                ),
            )
        return gate

    def get_decision_gate(self, gate_id: str) -> DecisionGate | None:
        """Return one decision gate by id."""
        row = self._connection.execute(
            "SELECT * FROM decision_gates WHERE id = ?", (gate_id,)
        ).fetchone()
        return _row_to_gate(row) if row else None

    def list_decision_gates(
        self,
        project_id: str,
        *,
        status: str | None = None,
    ) -> list[DecisionGate]:
        """List decision gates for a project, optionally filtered by status."""
        if status is not None:
            rows = self._connection.execute(
                "SELECT * FROM decision_gates WHERE project_id = ? AND status = ? ORDER BY raised_at DESC",
                (project_id, status),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM decision_gates WHERE project_id = ? ORDER BY raised_at DESC",
                (project_id,),
            ).fetchall()
        return [_row_to_gate(row) for row in rows]

    @retried_on_lock
    def save_human_gate_decision(self, decision: HumanGateDecision) -> HumanGateDecision:
        """Insert a human gate decision record."""
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO human_gate_decisions (
                    id, task_id, project_id, workflow_step,
                    decision, note, decided_by, decided_at, run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.id,
                    decision.task_id,
                    decision.project_id,
                    decision.workflow_step,
                    decision.decision,
                    decision.note,
                    decision.decided_by,
                    decision.decided_at,
                    decision.run_id,
                ),
            )
        return decision

    def get_human_gate_decision(
        self,
        task_id: str,
        workflow_step: str,
    ) -> HumanGateDecision | None:
        """Return the most recent human gate decision for a task/step."""
        row = self._connection.execute(
            """
            SELECT * FROM human_gate_decisions
            WHERE task_id = ? AND workflow_step = ?
            ORDER BY decided_at DESC
            LIMIT 1
            """,
            (task_id, workflow_step),
        ).fetchone()
        return _row_to_human_gate_decision(row) if row else None

    @retried_on_lock
    def save_merge_waiver(self, waiver: MergeWaiver) -> MergeWaiver:
        """Insert a merge waiver record."""
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO merge_waivers (
                    id, task_id, project_id, waiver_type, reason,
                    approved_by, approved_at, branch_name, head_sha, base_sha,
                    expires_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    waiver.id,
                    waiver.task_id,
                    waiver.project_id,
                    waiver.waiver_type,
                    waiver.reason,
                    waiver.approved_by,
                    waiver.approved_at,
                    waiver.branch_name,
                    waiver.head_sha,
                    waiver.base_sha,
                    waiver.expires_at,
                    waiver.revoked_at,
                ),
            )
        return waiver

    def get_merge_waiver(self, waiver_id: str) -> MergeWaiver | None:
        """Return a merge waiver by ID."""
        row = self._connection.execute(
            "SELECT * FROM merge_waivers WHERE id = ?",
            (waiver_id,),
        ).fetchone()
        return _row_to_merge_waiver(row) if row else None

    def get_active_merge_waiver(
        self,
        task_id: str,
        branch_name: str,
        head_sha: str,
        waiver_type: str | None = None,
    ) -> MergeWaiver | None:
        """Return an active (non-revoked, non-expired) waiver for a task and branch head.

        A waiver is active if:
        - revoked_at is NULL
        - expires_at is NULL or in the future
        - branch_name matches
        - head_sha matches (waiver is tied to specific branch state)
        - waiver_type matches if specified
        """
        now = utc_now_text()
        row = self._connection.execute(
            """
            SELECT * FROM merge_waivers
            WHERE task_id = ?
              AND branch_name = ?
              AND head_sha = ?
              AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > ?)
              AND (? IS NULL OR waiver_type = ?)
            ORDER BY approved_at DESC
            LIMIT 1
            """,
            (task_id, branch_name, head_sha, now, waiver_type, waiver_type),
        ).fetchone()
        return _row_to_merge_waiver(row) if row else None

    @retried_on_lock
    def revoke_merge_waiver(self, waiver_id: str) -> bool:
        """Revoke a merge waiver by setting revoked_at. Returns True if found and revoked."""
        now = utc_now_text()
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE merge_waivers SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (now, waiver_id),
            )
            return cursor.rowcount > 0
