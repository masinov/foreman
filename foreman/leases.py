"""Lease token generation, expiry computation, and validation helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Lease

DEFAULT_LEASE_DURATION_SECONDS = 300.0


def generate_lease_token() -> str:
    """Generate a cryptographically random lease token.

    Uses UUID4 hex (32 characters) for uniqueness.
    """
    from uuid import uuid4

    return uuid4().hex


def compute_lease_expiry(duration_seconds: float = DEFAULT_LEASE_DURATION_SECONDS) -> str:
    """Return an ISO 8601 UTC expiry timestamp for a lease of the given duration."""
    return (
        datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")


def is_lease_expired(lease: Lease, utc_now: datetime | None = None) -> bool:
    """Return True if the given lease has passed its expires_at time.

    Only active leases can be expired. Released or already-expired leases
    return False.
    """
    if lease.status != "active":
        return False
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)
    normalized = lease.expires_at.replace("Z", "+00:00")
    try:
        expires = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return utc_now > expires


def is_lease_stale(
    lease: Lease,
    stale_after_seconds: float,
    utc_now: datetime | None = None,
) -> bool:
    """Return True if the lease heartbeat is older than the stale threshold."""
    if lease.status != "active":
        return False
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)
    normalized = lease.heartbeat_at.replace("Z", "+00:00")
    try:
        heartbeat = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
    return (utc_now - heartbeat).total_seconds() > stale_after_seconds


def validate_lease_holder(lease: Lease, holder_id: str, lease_token: str) -> bool:
    """Return True if the given holder_id and lease_token match the lease."""
    return lease.holder_id == holder_id and lease.lease_token == lease_token
