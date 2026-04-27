"""Tests for the first-class lease system."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from foreman.leases import (
    compute_lease_expiry,
    generate_lease_token,
    is_lease_expired,
    is_lease_stale,
    validate_lease_holder,
    DEFAULT_LEASE_DURATION_SECONDS,
)
from foreman.models import Lease
from foreman.store import ForemanStore


class LeaseModelTests(unittest.TestCase):
    """Lease dataclass defaults and field values."""

    def test_lease_defaults_status_to_active(self) -> None:
        token = generate_lease_token()
        lease = Lease(
            id="lease-1",
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        self.assertEqual(lease.status, "active")
        self.assertEqual(lease.fencing_token, 1)
        self.assertIsNone(lease.released_at)
        self.assertIsNotNone(lease.acquired_at)
        self.assertIsNotNone(lease.heartbeat_at)
        self.assertIsNotNone(lease.expires_at)

    def test_lease_can_be_released(self) -> None:
        token = generate_lease_token()
        lease = Lease(
            id="lease-1",
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
            status="released",
            released_at="2026-04-27T12:00:00Z",
        )
        self.assertEqual(lease.status, "released")
        self.assertIsNotNone(lease.released_at)

    def test_lease_can_be_expired(self) -> None:
        token = generate_lease_token()
        lease = Lease(
            id="lease-1",
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
            status="expired",
        )
        self.assertEqual(lease.status, "expired")


class LeaseTokenTests(unittest.TestCase):
    """Token generation and validation."""

    def test_generate_lease_token_returns_unique_hex_strings(self) -> None:
        tokens = {generate_lease_token() for _ in range(100)}
        self.assertEqual(len(tokens), 100)

    def test_validate_lease_holder_accepts_matching_credentials(self) -> None:
        token = generate_lease_token()
        lease = Lease(
            id="lease-1",
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        self.assertTrue(validate_lease_holder(lease, "holder-a", token))

    def test_validate_lease_holder_rejects_wrong_holder(self) -> None:
        token = generate_lease_token()
        lease = Lease(
            id="lease-1",
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        self.assertFalse(validate_lease_holder(lease, "holder-b", token))

    def test_validate_lease_holder_rejects_wrong_token(self) -> None:
        lease = Lease(
            id="lease-1",
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=generate_lease_token(),
        )
        self.assertFalse(validate_lease_holder(lease, "holder-a", "wrong-token"))


class ExpiryTests(unittest.TestCase):
    """Expiry and staleness detection."""

    def test_is_lease_expired_returns_false_for_active_nonexpired(self) -> None:
        token = generate_lease_token()
        future = (
            datetime.now(timezone.utc) + timedelta(seconds=300)
        ).isoformat(timespec="microseconds").replace("+00:00", "Z")
        lease = Lease(
            id="lease-1",
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
            status="active",
            expires_at=future,
        )
        self.assertFalse(is_lease_expired(lease))

    def test_is_lease_expired_returns_true_for_expired_active(self) -> None:
        token = generate_lease_token()
        past = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat(timespec="microseconds").replace("+00:00", "Z")
        lease = Lease(
            id="lease-1",
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
            status="active",
            expires_at=past,
        )
        self.assertTrue(is_lease_expired(lease))

    def test_is_lease_expired_returns_false_for_released(self) -> None:
        token = generate_lease_token()
        past = (
            datetime.now(timezone.utc) - timedelta(seconds=300)
        ).isoformat(timespec="microseconds").replace("+00:00", "Z")
        lease = Lease(
            id="lease-1",
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
            status="released",
            expires_at=past,
        )
        self.assertFalse(is_lease_expired(lease))

    def test_is_lease_expired_returns_false_for_already_expired_status(self) -> None:
        token = generate_lease_token()
        lease = Lease(
            id="lease-1",
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
            status="expired",
        )
        self.assertFalse(is_lease_expired(lease))

    def test_is_lease_stale_returns_true_when_heartbeat_too_old(self) -> None:
        token = generate_lease_token()
        old_heartbeat = (
            datetime.now(timezone.utc) - timedelta(seconds=600)
        ).isoformat(timespec="microseconds").replace("+00:00", "Z")
        lease = Lease(
            id="lease-1",
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
            status="active",
            heartbeat_at=old_heartbeat,
            expires_at=(
                datetime.now(timezone.utc) + timedelta(seconds=300)
            ).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        )
        self.assertTrue(is_lease_stale(lease, stale_after_seconds=300))

    def test_is_lease_stale_returns_false_when_heartbeat_recent(self) -> None:
        token = generate_lease_token()
        recent = (
            datetime.now(timezone.utc) - timedelta(seconds=10)
        ).isoformat(timespec="microseconds").replace("+00:00", "Z")
        lease = Lease(
            id="lease-1",
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
            status="active",
            heartbeat_at=recent,
            expires_at=(
                datetime.now(timezone.utc) + timedelta(seconds=300)
            ).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        )
        self.assertFalse(is_lease_stale(lease, stale_after_seconds=300))

    def test_compute_lease_expiry_returns_future_timestamp(self) -> None:
        now = datetime.now(timezone.utc)
        expiry = compute_lease_expiry(300.0)
        exp = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        # Should be approximately 300 seconds in the future.
        self.assertGreater((exp - now).total_seconds(), 299)
        self.assertLess((exp - now).total_seconds(), 301)


class AcquireLeaseTests(unittest.TestCase):
    """Lease acquisition through the store."""

    def create_store(self) -> ForemanStore:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = Path(temp_dir.name) / "foreman.db"
        store = ForemanStore(db_path)
        store.initialize()
        return store

    def test_a_task_can_be_leased_once(self) -> None:
        store = self.create_store()
        token = generate_lease_token()
        lease = store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        self.assertIsNotNone(lease)
        self.assertEqual(lease.status, "active")
        self.assertEqual(lease.holder_id, "holder-a")
        self.assertEqual(lease.resource_type, "task")
        self.assertEqual(lease.resource_id, "t1")

    def test_second_holder_cannot_lease_the_same_active_task(self) -> None:
        store = self.create_store()
        token_a = generate_lease_token()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token_a,
        )
        token_b = generate_lease_token()
        denied = store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-b",
            lease_token=token_b,
        )
        self.assertIsNone(denied)
        # Original lease is untouched.
        active = store.get_active_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
        )
        assert active is not None
        self.assertEqual(active.holder_id, "holder-a")

    def test_same_holder_can_renew_with_same_token(self) -> None:
        store = self.create_store()
        token = generate_lease_token()
        original = store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        assert original is not None
        renewed = store.renew_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        self.assertIsNotNone(renewed)
        self.assertEqual(renewed.id, original.id)
        self.assertEqual(renewed.status, "active")

    def test_wrong_token_cannot_renew(self) -> None:
        store = self.create_store()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=generate_lease_token(),
        )
        denied = store.renew_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token="wrong-token",
        )
        self.assertIsNone(denied)

    def test_wrong_holder_cannot_renew(self) -> None:
        store = self.create_store()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=generate_lease_token(),
        )
        denied = store.renew_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-b",
            lease_token=generate_lease_token(),
        )
        self.assertIsNone(denied)

    def test_wrong_token_cannot_release(self) -> None:
        store = self.create_store()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=generate_lease_token(),
        )
        released = store.release_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token="wrong-token",
        )
        self.assertFalse(released)

    def test_wrong_holder_cannot_release(self) -> None:
        store = self.create_store()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=generate_lease_token(),
        )
        released = store.release_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-b",
            lease_token=generate_lease_token(),
        )
        self.assertFalse(released)

    def test_correct_holder_and_token_releases(self) -> None:
        store = self.create_store()
        token = generate_lease_token()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        released = store.release_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        self.assertTrue(released)
        self.assertIsNone(
            store.get_active_lease(
                project_id="p1",
                resource_type="task",
                resource_id="t1",
            )
        )

    def test_expired_lease_can_be_reclaimed(self) -> None:
        store = self.create_store()
        token_a = generate_lease_token()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token_a,
            duration_seconds=0.0,  # Immediately expires.
        )
        # Expire all stale leases.
        store.expire_leases(older_than_seconds=0)
        # New holder can now acquire.
        token_b = generate_lease_token()
        reclaimed = store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-b",
            lease_token=token_b,
        )
        self.assertIsNotNone(reclaimed)
        assert reclaimed is not None
        self.assertEqual(reclaimed.holder_id, "holder-b")

    def test_released_lease_can_be_reclaimed(self) -> None:
        store = self.create_store()
        token_a = generate_lease_token()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token_a,
        )
        store.release_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token_a,
        )
        token_b = generate_lease_token()
        reclaimed = store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-b",
            lease_token=token_b,
        )
        self.assertIsNotNone(reclaimed)
        assert reclaimed is not None
        self.assertEqual(reclaimed.holder_id, "holder-b")

    def test_different_resource_types_do_not_conflict(self) -> None:
        store = self.create_store()
        token = generate_lease_token()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        # A run on the same task is a different resource type.
        token2 = generate_lease_token()
        lease2 = store.acquire_lease(
            project_id="p1",
            resource_type="run",
            resource_id="r1",
            holder_id="holder-a",
            lease_token=token2,
        )
        self.assertIsNotNone(lease2)

    def test_different_projects_do_not_conflict(self) -> None:
        store = self.create_store()
        token = generate_lease_token()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        token2 = generate_lease_token()
        lease2 = store.acquire_lease(
            project_id="p2",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token2,
        )
        self.assertIsNotNone(lease2)


class ExpireLeasesTests(unittest.TestCase):
    """Bulk lease expiry."""

    def create_store(self) -> ForemanStore:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = Path(temp_dir.name) / "foreman.db"
        store = ForemanStore(db_path)
        store.initialize()
        return store

    def test_expire_leases_by_heartbeat_age(self) -> None:
        store = self.create_store()
        token = generate_lease_token()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        count = store.expire_leases(older_than_seconds=0)
        self.assertEqual(count, 1)
        leases = store.list_leases(status="expired")
        self.assertEqual(len(leases), 1)

    def test_expire_leases_by_holder(self) -> None:
        store = self.create_store()
        token_a = generate_lease_token()
        token_b = generate_lease_token()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token_a,
        )
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t2",
            holder_id="holder-b",
            lease_token=token_b,
        )
        count = store.expire_leases(holder_id="holder-a")
        self.assertEqual(count, 1)
        remaining = store.list_leases(holder_id="holder-b", status="active")
        self.assertEqual(len(remaining), 1)

    def test_expire_leases_by_project(self) -> None:
        store = self.create_store()
        for pid in ["p1", "p2"]:
            token = generate_lease_token()
            store.acquire_lease(
                project_id=pid,
                resource_type="task",
                resource_id="t1",
                holder_id="holder-a",
                lease_token=token,
            )
        count = store.expire_leases(project_id="p1")
        self.assertEqual(count, 1)
        active = store.list_leases(status="active")
        self.assertEqual(len(active), 1)


class ListLeasesTests(unittest.TestCase):
    """Lease listing and filtering."""

    def create_store(self) -> ForemanStore:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = Path(temp_dir.name) / "foreman.db"
        store = ForemanStore(db_path)
        store.initialize()
        return store

    def test_list_leases_returns_all_by_default(self) -> None:
        store = self.create_store()
        for i in range(3):
            token = generate_lease_token()
            store.acquire_lease(
                project_id="p1",
                resource_type="task",
                resource_id=f"t{i}",
                holder_id="holder-a",
                lease_token=token,
            )
        leases = store.list_leases()
        self.assertEqual(len(leases), 3)

    def test_list_leases_filters_by_status(self) -> None:
        store = self.create_store()
        token = generate_lease_token()
        store.acquire_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        store.release_lease(
            project_id="p1",
            resource_type="task",
            resource_id="t1",
            holder_id="holder-a",
            lease_token=token,
        )
        active = store.list_leases(status="active")
        self.assertEqual(len(active), 0)
        released = store.list_leases(status="released")
        self.assertEqual(len(released), 1)


class MigrationTests(unittest.TestCase):
    """Migration: existing DB without data loss."""

    def test_fresh_db_creates_leases_table(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = Path(temp_dir.name) / "foreman.db"
        store = ForemanStore(db_path)
        store.initialize()
        # Leases table should exist.
        rows = store._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='leases'"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        # Indexes should also exist.
        for idx in ["idx_leases_project_resource", "idx_leases_holder", "idx_leases_expires"]:
            row = store._connection.execute(
                f"SELECT name FROM sqlite_master WHERE type='index' AND name='{idx}'"
            ).fetchone()
            self.assertIsNotNone(row, f"Index {idx} not found")

    def test_leases_migration_upgrades_existing_db(self) -> None:
        # Simulate a pre-migration-6 database with data.
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = Path(temp_dir.name) / "foreman.db"

        # Create store and initialize up to version 5.
        store = ForemanStore(db_path)
        store.initialize()
        # Override schema version to simulate pre-6 state.
        store._connection.execute("DELETE FROM schema_migrations WHERE version = 6")

        # Verify migration 6 is not yet applied.
        version = store.schema_version()
        self.assertLess(version, 6)

        # Re-initialize — should apply migration 6.
        store2 = ForemanStore(db_path)
        store2.initialize()
        version2 = store2.schema_version()
        self.assertEqual(version2, 6)

        # Leases table should now exist.
        rows = store2._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='leases'"
        ).fetchall()
        self.assertEqual(len(rows), 1)
