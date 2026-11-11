"""Leases on tasks and the per-project engine lock."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..models import (
    EngineLockView,
    Lease,
    utc_now_text,
)

from .base import (
    ENGINE_RESOURCE_TYPE,
    StoreBase,
    retried_on_lock,
)
from .rows import (
    _row_to_lease,
)


class LeaseStore(StoreBase):
    """Leases on tasks and the per-project engine lock."""

    def get_lease(self, lease_id: str) -> Lease | None:
        """Return one lease by identifier."""
        row = self._connection.execute(
            "SELECT * FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        return _row_to_lease(row) if row else None

    def get_active_lease(
        self,
        *,
        project_id: str,
        resource_type: str,
        resource_id: str,
    ) -> Lease | None:
        """Return the active lease for one resource, or None."""
        row = self._connection.execute(
            """
            SELECT * FROM leases
            WHERE project_id = ?
              AND resource_type = ?
              AND resource_id = ?
              AND status = 'active'
            LIMIT 1
            """,
            (project_id, resource_type, resource_id),
        ).fetchone()
        return _row_to_lease(row) if row else None

    @retried_on_lock
    def expire_resource_leases(
        self,
        *,
        project_id: str,
        resource_type: str,
        resource_id: str,
        force: bool = False,
    ) -> int:
        """Mark all active leases for one resource as expired. Returns count of expired leases.

        By default, only leases whose ``expires_at`` is already in the past are
        transitioned. Pass ``force=True`` to expire every active lease for the
        resource regardless of ``expires_at``; used by recovery when the
        original holder is known to be gone and a future lease expiry cannot be
        waited for.
        """
        now = utc_now_text()
        with self._connection:
            if force:
                cursor = self._connection.execute(
                    """
                    UPDATE leases
                    SET status = 'expired'
                    WHERE project_id = ?
                      AND resource_type = ?
                      AND resource_id = ?
                      AND status = 'active'
                    """,
                    (project_id, resource_type, resource_id),
                )
            else:
                cursor = self._connection.execute(
                    """
                    UPDATE leases
                    SET status = 'expired'
                    WHERE project_id = ?
                      AND resource_type = ?
                      AND resource_id = ?
                      AND status = 'active'
                      AND expires_at < ?
                    """,
                    (project_id, resource_type, resource_id, now),
                )
            return cursor.rowcount

    @retried_on_lock
    def acquire_lease(
        self,
        *,
        project_id: str,
        resource_type: str,
        resource_id: str,
        holder_id: str,
        lease_token: str,
        duration_seconds: float = 300.0,
    ) -> Lease | None:
        """Atomically acquire a lease on a resource.

        Returns the new Lease if acquisition succeeded.
        Returns None if an active lease already exists (enforced by the DB's
        unique partial index on active leases).
        Expired leases are transitioned to 'expired' before insertion so they
        do not block reacquisition.

        The fencing_token is auto-incremented: new leases get MAX(existing) + 1.
        """
        from ..leases import compute_lease_expiry

        now = utc_now_text()
        expires_at = compute_lease_expiry(duration_seconds)

        with self._connection:
            # Transition any expired leases for this resource to 'expired'.
            self._connection.execute(
                """
                UPDATE leases
                SET status = 'expired'
                WHERE project_id = ?
                  AND resource_type = ?
                  AND resource_id = ?
                  AND status = 'active'
                  AND expires_at < ?
                """,
                (project_id, resource_type, resource_id, now),
            )

            # Compute next fencing token: MAX(existing) + 1 for this resource
            max_token_row = self._connection.execute(
                """
                SELECT COALESCE(MAX(fencing_token), 0) + 1 AS next_token
                FROM leases
                WHERE project_id = ?
                  AND resource_type = ?
                  AND resource_id = ?
                """,
                (project_id, resource_type, resource_id),
            ).fetchone()
            next_fencing_token: int = max_token_row["next_token"] if max_token_row else 1

            # Insert the new lease. The unique partial index enforces that only
            # one active lease per resource exists at a time.
            lease_id = f"lease-{uuid4().hex[:12]}"
            try:
                self._connection.execute(
                    """
                    INSERT INTO leases (
                        id, project_id, resource_type, resource_id, holder_id,
                        lease_token, fencing_token, status,
                        acquired_at, heartbeat_at, expires_at, released_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, NULL)
                    """,
                    (
                        lease_id, project_id, resource_type, resource_id,
                        holder_id, lease_token, next_fencing_token,
                        now, now, expires_at,
                    ),
                )
            except sqlite3.IntegrityError:
                # Another connection inserted an active lease between our expiry
                # update and insert; this is the expected race result.
                return None

        return self.get_lease(lease_id)

    @retried_on_lock
    def renew_lease(
        self,
        *,
        project_id: str,
        resource_type: str,
        resource_id: str,
        holder_id: str,
        lease_token: str,
        duration_seconds: float = 300.0,
    ) -> Lease | None:
        """Renew an active lease if the caller holds it with the correct token.

        Returns the renewed Lease on success.
        Returns None if: no active lease, holder_id mismatch, or token mismatch.
        """
        from ..leases import compute_lease_expiry, is_lease_expired

        now = utc_now_text()
        expires_at = compute_lease_expiry(duration_seconds)

        with self._connection:
            row = self._connection.execute(
                """
                SELECT * FROM leases
                WHERE project_id = ?
                  AND resource_type = ?
                  AND resource_id = ?
                  AND status = 'active'
                """,
                (project_id, resource_type, resource_id),
            ).fetchone()
            if row is None:
                return None

            lease = _row_to_lease(row)

            # Validate holder and token.
            if lease.holder_id != holder_id or lease.lease_token != lease_token:
                return None

            # Check expiry (edge case: clock skew or concurrent expiry).
            if is_lease_expired(lease):
                self._connection.execute(
                    "UPDATE leases SET status = 'expired' WHERE id = ?",
                    (lease.id,),
                )
                return None

            # Renew: update heartbeat and expiry.
            self._connection.execute(
                """
                UPDATE leases
                SET heartbeat_at = ?, expires_at = ?
                WHERE id = ?
                """,
                (now, expires_at, lease.id),
            )

        return self.get_lease(lease.id)

    @retried_on_lock
    def release_lease(
        self,
        *,
        project_id: str,
        resource_type: str,
        resource_id: str,
        holder_id: str,
        lease_token: str,
    ) -> bool:
        """Release an active lease if the caller holds it with the correct token.

        Returns True on successful release.
        Returns False if: no active lease, holder_id mismatch, or token mismatch.
        """
        now = utc_now_text()

        with self._connection:
            row = self._connection.execute(
                """
                SELECT * FROM leases
                WHERE project_id = ?
                  AND resource_type = ?
                  AND resource_id = ?
                  AND status = 'active'
                """,
                (project_id, resource_type, resource_id),
            ).fetchone()
            if row is None:
                return False

            lease = _row_to_lease(row)

            if lease.holder_id != holder_id or lease.lease_token != lease_token:
                return False

            self._connection.execute(
                """
                UPDATE leases
                SET status = 'released', released_at = ?
                WHERE id = ?
                """,
                (now, lease.id),
            )

        return True

    @retried_on_lock
    def expire_leases(
        self,
        *,
        project_id: str | None = None,
        holder_id: str | None = None,
        older_than_seconds: float | None = None,
    ) -> int:
        """Mark active leases as expired based on heartbeat age or holder.

        If older_than_seconds is provided, expires leases whose heartbeat is
        older than that threshold. If holder_id is provided, only expires
        leases for that holder. If both provided, both conditions must match.

        Returns the number of leases expired.
        """
        from datetime import timedelta

        conditions = ["status = 'active'"]
        params: list[Any] = []

        if older_than_seconds is not None:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
            ).isoformat(timespec="microseconds").replace("+00:00", "Z")
            conditions.append("heartbeat_at < ?")
            params.append(cutoff)

        if holder_id is not None:
            conditions.append("holder_id = ?")
            params.append(holder_id)

        if project_id is not None:
            conditions.append("project_id = ?")
            params.append(project_id)

        where_clause = " AND ".join(conditions)

        with self._connection:
            cursor = self._connection.execute(
                f"""
                UPDATE leases
                SET status = 'expired'
                WHERE {where_clause}
                """,
                tuple(params),
            )
        return int(cursor.rowcount)

    def list_leases(
        self,
        *,
        project_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        holder_id: str | None = None,
        status: str | None = None,
    ) -> list[Lease]:
        """List leases with optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if project_id is not None:
            conditions.append("project_id = ?")
            params.append(project_id)
        if resource_type is not None:
            conditions.append("resource_type = ?")
            params.append(resource_type)
        if resource_id is not None:
            conditions.append("resource_id = ?")
            params.append(resource_id)
        if holder_id is not None:
            conditions.append("holder_id = ?")
            params.append(holder_id)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)

        sql = "SELECT * FROM leases"
        if conditions:
            sql = f"{sql} WHERE {' AND '.join(conditions)}"
        sql = f"{sql} ORDER BY acquired_at ASC"

        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [_row_to_lease(row) for row in rows]

    def get_engine_lock(self, project_id: str) -> EngineLockView | None:
        """Return a token-free view of the project's engine lease, or None.

        This is the read side of :class:`~foreman.engine_lock.EngineLock`: it
        answers "is an engine resident on this project, whose is it, and how
        fresh is its heartbeat" without handing out the token that would let
        the reader release someone else's lock.
        """

        lease = self.get_active_lease(
            project_id=project_id,
            resource_type=ENGINE_RESOURCE_TYPE,
            resource_id=project_id,
        )
        if lease is None:
            return None
        return EngineLockView(
            project_id=lease.project_id,
            holder_id=lease.holder_id,
            acquired_at=lease.acquired_at,
            heartbeat_at=lease.heartbeat_at,
            expires_at=lease.expires_at,
        )
