"""Coverage for notification destinations and the delivery path.

The acceptance criterion this file exists to prove: a project with a webhook
destination and ``notification=attention`` gets one delivery per attention turn
and per human gate and none for a completion; ``all`` adds completions;
``none`` delivers nothing. A destination that is down is retried and then
recorded, and never blocks or fails a task.

Every test stubs the transport. Nothing here opens a socket.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

from foreman.migrations import MIGRATIONS
from foreman.models import (
    Event,
    NotificationDelivery,
    NotificationDestination,
    Project,
    Run,
    Sprint,
    Task,
)
from foreman.notifications import (
    ATTENTION,
    _iso,
    DEFAULT_MAX_ATTEMPTS,
    HUMAN_GATE,
    NotificationDeliveryWorker,
    NotificationDispatcher,
    NotificationError,
    TASK_COMPLETED,
    TransportError,
    WebhookTransport,
    build_payload,
    kind_for_event,
    notify_decision,
    policy_allows,
    resolve_notification_policy,
    retry_delay_seconds,
    validate_target,
)
from foreman.orchestrator import AgentEventRecord, ForemanOrchestrator
from foreman.runner import AgentRunConfig
from foreman.runner.base import AgentEvent
from foreman.settings import ProjectSettings, SettingsError
from foreman.store import ForemanStore

from test_cli import cli_argv, cli_env


# ── helpers ──────────────────────────────────────────────────────────────


class _StubTransport:
    """A transport that records what it was asked to send.

    ``fail_times`` makes the first N attempts fail, which is how the retry
    schedule is exercised without waiting for one.
    """

    def __init__(self, *, fail_times: int = 0, error: str = "connection refused") -> None:
        self.sent: list[NotificationDelivery] = []
        self.fail_times = fail_times
        self.error = error
        self.attempts = 0

    def send(
        self, destination: NotificationDestination, delivery: NotificationDelivery
    ) -> str:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise TransportError(self.error)
        self.sent.append(delivery)
        return "HTTP 200"


class _Clock:
    """A clock the delivery worker is driven by, so backoff is instant.

    Starts at the real now so it is comparable with the timestamps the store
    writes on its own, and only ever moves when a test says so.
    """

    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _project(**settings: object) -> Project:
    return Project(
        id="p1",
        name="Foreman",
        repo_path="/tmp/repo",
        workflow_id="development",
        settings=dict(settings),
    )


def _destination(name: str = "ops", **kwargs: object) -> NotificationDestination:
    return NotificationDestination(
        id=kwargs.pop("id", f"dst-{name}"),
        project_id="p1",
        name=name,
        target="https://example.test/hook",
        **kwargs,
    )


def _event(event_type: str, payload: dict | None = None, **kwargs: object) -> Event:
    return Event(
        id=kwargs.pop("id", "event-1"),
        run_id=kwargs.pop("run_id", "run-1"),
        task_id=kwargs.pop("task_id", "t1"),
        project_id="p1",
        event_type=event_type,
        payload=payload or {},
    )


# ── policy ───────────────────────────────────────────────────────────────


class NotificationPolicyTests(unittest.TestCase):
    """Which kinds each policy value delivers, and where the value comes from."""

    def test_the_policy_ladder_is_inclusive(self) -> None:
        for kind in (ATTENTION, HUMAN_GATE, TASK_COMPLETED):
            self.assertFalse(policy_allows("none", kind), kind)
            self.assertTrue(policy_allows("all", kind), kind)
        self.assertTrue(policy_allows("attention", ATTENTION))
        self.assertTrue(policy_allows("attention", HUMAN_GATE))
        self.assertFalse(policy_allows("attention", TASK_COMPLETED))

    def test_an_unknown_or_missing_policy_delivers_nothing(self) -> None:
        for value in (None, "", "loud", 3):
            self.assertFalse(policy_allows(value, ATTENTION), value)

    def test_resolution_prefers_the_task_override_then_the_project(self) -> None:
        project = _project(notification="all")
        task = Task(
            id="t1",
            sprint_id="s1",
            project_id="p1",
            title="T",
            executor_overrides={"policy": {"notification": "none"}},
        )
        self.assertEqual(resolve_notification_policy(project, task), "none")
        self.assertEqual(resolve_notification_policy(project, None), "all")
        self.assertEqual(resolve_notification_policy(_project(), None), "attention")
        self.assertEqual(resolve_notification_policy(None, None), "attention")

    def test_resolution_uses_the_canonical_task_type_rule(self) -> None:
        project = _project(
            notification="none",
            policy_rules={"feature": {"notification": "all"}},
        )
        task = Task(
            id="t1",
            sprint_id="s1",
            project_id="p1",
            title="T",
            task_type="feature",
        )

        self.assertEqual(resolve_notification_policy(project, task), "all")

    def test_a_malformed_setting_falls_back_rather_than_raising(self) -> None:
        # Settings are validated at write time; a row edited by hand must
        # still yield a safe answer mid-run.
        self.assertEqual(resolve_notification_policy(_project(notification=7)), "attention")
        self.assertEqual(
            resolve_notification_policy(_project(notification="loud")), "attention"
        )

    def test_the_stamped_decision_on_the_event_wins(self) -> None:
        project = _project(notification="none")
        self.assertEqual(
            notify_decision({"notify": "all"}, project=project), "all"
        )
        # No stamp: an event written before the field existed still resolves.
        self.assertEqual(notify_decision({}, project=project), "none")

    def test_only_a_human_gate_pause_is_announceable(self) -> None:
        self.assertEqual(
            kind_for_event("workflow.paused", {"reason": "human_gate"}), HUMAN_GATE
        )
        self.assertIsNone(kind_for_event("workflow.paused", {"reason": "quota"}))
        self.assertIsNone(kind_for_event("workflow.step_started", {}))
        self.assertEqual(kind_for_event("engine.attention_needed", {}), ATTENTION)
        self.assertEqual(kind_for_event("task.completed", {}), TASK_COMPLETED)

    def test_the_setting_is_validated_and_shares_one_vocabulary(self) -> None:
        self.assertEqual(ProjectSettings.from_raw({}).notification, "attention")
        self.assertEqual(
            ProjectSettings.from_raw({"notification": "all"}).notification, "all"
        )
        with self.assertRaises(SettingsError):
            ProjectSettings.from_raw({"notification": "sometimes"})

    def test_retry_delays_double_and_cap(self) -> None:
        self.assertEqual(retry_delay_seconds(1), 30.0)
        self.assertEqual(retry_delay_seconds(2), 60.0)
        self.assertEqual(retry_delay_seconds(3), 120.0)
        self.assertEqual(retry_delay_seconds(99), 1800.0)


# ── schema and store ─────────────────────────────────────────────────────


class NotificationMigrationTests(unittest.TestCase):
    """Migration 18 must reach a database that stopped at version 17."""

    def test_applies_cleanly_to_a_version_17_database(self) -> None:
        from foreman.store import _SCHEMA_MIGRATIONS_DDL

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "old.db"
            connection = sqlite3.connect(db_path)
            connection.executescript(_SCHEMA_MIGRATIONS_DDL)
            for version, description, sql in MIGRATIONS:
                if version > 17:
                    continue
                connection.executescript(sql)
                connection.execute(
                    "INSERT INTO schema_migrations (version, description, applied_at) "
                    "VALUES (?, ?, datetime('now'))",
                    (version, description),
                )
            connection.commit()
            connection.close()

            with ForemanStore(db_path) as store:
                self.assertIn(18, store.migrate())
                tables = {
                    row["name"]
                    for row in store._connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertLessEqual(
                    {"notification_destinations", "notification_deliveries"}, tables
                )


class NotificationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = ForemanStore(":memory:")
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(_project())

    def test_destinations_round_trip_and_are_named_uniquely(self) -> None:
        self.store.save_notification_destination(
            _destination(config={"secret_env": "HOOK_KEY"})
        )
        loaded = self.store.find_notification_destination("p1", "ops")
        self.assertEqual(loaded.target, "https://example.test/hook")
        self.assertEqual(loaded.config, {"secret_env": "HOOK_KEY"})
        self.assertTrue(loaded.enabled)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save_notification_destination(_destination(id="dst-other"))

    def test_disabled_destinations_are_excluded_on_request(self) -> None:
        self.store.save_notification_destination(_destination("ops"))
        self.store.save_notification_destination(_destination("quiet", enabled=False))
        self.assertEqual(len(self.store.list_notification_destinations("p1")), 2)
        self.assertEqual(
            [
                destination.name
                for destination in self.store.list_notification_destinations(
                    "p1", include_disabled=False
                )
            ],
            ["ops"],
        )

    def test_the_same_event_queues_once_per_destination(self) -> None:
        self.store.save_notification_destination(_destination())
        first = self.store.enqueue_notification_delivery(
            project_id="p1",
            destination_id="dst-ops",
            kind=ATTENTION,
            payload={"a": 1},
            event_id="event-1",
        )
        second = self.store.enqueue_notification_delivery(
            project_id="p1",
            destination_id="dst-ops",
            kind=ATTENTION,
            payload={"a": 1},
            event_id="event-1",
        )
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(self.store.count_notification_deliveries("p1")["pending"], 1)

    def test_only_due_deliveries_are_listed(self) -> None:
        self.store.save_notification_destination(_destination())
        self.store.enqueue_notification_delivery(
            project_id="p1",
            destination_id="dst-ops",
            kind=ATTENTION,
            payload={},
            event_id="e1",
            next_attempt_at="2030-01-01T00:00:00.000000Z",
        )
        self.assertEqual(
            self.store.list_due_notification_deliveries(
                "p1", now="2026-01-01T00:00:00.000000Z"
            ),
            [],
        )
        self.assertEqual(
            len(
                self.store.list_due_notification_deliveries(
                    "p1", now="2031-01-01T00:00:00.000000Z"
                )
            ),
            1,
        )

    def test_removing_a_destination_takes_its_deliveries(self) -> None:
        self.store.save_notification_destination(_destination())
        self.store.enqueue_notification_delivery(
            project_id="p1", destination_id="dst-ops", kind=ATTENTION, payload={}
        )
        self.assertTrue(self.store.delete_notification_destination("dst-ops"))
        self.assertEqual(self.store.list_notification_deliveries("p1"), [])
        self.assertFalse(self.store.delete_notification_destination("dst-ops"))

    def test_settling_records_the_outcome_of_one_attempt(self) -> None:
        self.store.save_notification_destination(_destination())
        delivery = self.store.enqueue_notification_delivery(
            project_id="p1", destination_id="dst-ops", kind=ATTENTION, payload={}
        )
        settled = self.store.settle_notification_delivery(
            delivery.id,
            status="delivered",
            attempts=2,
            last_error=None,
            now="2026-09-08T12:00:00.000000Z",
        )
        self.assertEqual(settled.status, "delivered")
        self.assertEqual(settled.delivered_at, "2026-09-08T12:00:00.000000Z")
        with self.assertRaises(ValueError):
            self.store.settle_notification_delivery(
                delivery.id, status="lost", attempts=1, last_error=None, now="x"
            )


# ── dispatch ─────────────────────────────────────────────────────────────


class DispatcherTests(unittest.TestCase):
    """What the engine chooses to queue, from one persisted event."""

    def setUp(self) -> None:
        self.store = ForemanStore(":memory:")
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(_project(notification="attention"))
        self.store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        self.store.save_task(Task(id="t1", sprint_id="s1", project_id="p1", title="Ship it"))
        self.store.save_notification_destination(_destination())
        self.dispatcher = NotificationDispatcher(self.store)

    def test_an_attention_turn_queues_one_delivery_per_destination(self) -> None:
        self.store.save_notification_destination(_destination("second"))
        queued = self.dispatcher.consider(
            _event("engine.attention_needed", {"trigger": "task_blocked", "task_id": "t1", "notify": "attention"})
        )
        self.assertEqual(len(queued), 2)
        self.assertEqual({d.kind for d in queued}, {ATTENTION})
        payload = queued[0].payload
        self.assertEqual(payload["task"]["title"], "Ship it")
        self.assertEqual(payload["project"]["name"], "Foreman")
        self.assertEqual(payload["event"]["type"], "engine.attention_needed")

    def test_the_same_event_offered_twice_queues_once(self) -> None:
        event = _event("engine.attention_needed", {"task_id": "t1", "notify": "attention"})
        self.assertEqual(len(self.dispatcher.consider(event)), 1)
        self.assertEqual(self.dispatcher.consider(event), [])

    def test_attention_policy_skips_completions_and_all_takes_them(self) -> None:
        completion = _event("task.completed", {"task_id": "t1", "notify": "attention"})
        self.assertEqual(self.dispatcher.consider(completion), [])
        louder = _event(
            "task.completed", {"task_id": "t1", "notify": "all"}, id="event-2"
        )
        self.assertEqual(len(self.dispatcher.consider(louder)), 1)

    def test_none_delivers_nothing(self) -> None:
        for event_type in ("engine.attention_needed", "task.completed"):
            self.assertEqual(
                self.dispatcher.consider(
                    _event(event_type, {"notify": "none"}, id=f"event-{event_type}")
                ),
                [],
            )
        self.assertEqual(
            self.dispatcher.consider(
                _event(
                    "workflow.paused",
                    {"reason": "human_gate", "notify": "none"},
                    id="event-gate",
                )
            ),
            [],
        )

    def test_a_project_with_no_destination_queues_nothing(self) -> None:
        self.store.delete_notification_destination("dst-ops")
        self.assertEqual(
            self.dispatcher.consider(_event("engine.attention_needed", {"notify": "all"})),
            [],
        )

    def test_a_disabled_destination_accumulates_no_queue(self) -> None:
        destination = self.store.get_notification_destination("dst-ops")
        destination.enabled = False
        self.store.save_notification_destination(destination)
        self.assertEqual(
            self.dispatcher.consider(_event("engine.attention_needed", {"notify": "all"})),
            [],
        )

    def test_uninteresting_events_cost_no_lookup(self) -> None:
        self.assertEqual(self.dispatcher.consider(_event("agent.tool_use", {})), [])

    def test_a_sprint_handoff_does_not_claim_the_anchor_task(self) -> None:
        # `engine.attention_needed` names its subject in the payload: a sprint
        # handoff is raised against an anchor task it is not about.
        queued = self.dispatcher.consider(
            _event(
                "engine.attention_needed",
                {"trigger": "sprint_resolved", "task_id": None, "notify": "attention"},
            )
        )
        self.assertEqual(len(queued), 1)
        self.assertIsNone(queued[0].payload["task"])
        self.assertIsNone(queued[0].task_id)

    def test_dispatch_never_raises_into_the_engine(self) -> None:
        class _BrokenStore:
            def list_notification_destinations(self, *args, **kwargs):
                raise sqlite3.OperationalError("database is locked")

        dispatcher = NotificationDispatcher(_BrokenStore())
        with self.assertLogs("foreman.notifications", level="WARNING"):
            self.assertEqual(
                dispatcher.consider(_event("engine.attention_needed", {"notify": "all"})),
                [],
            )


# ── delivery ─────────────────────────────────────────────────────────────


class DeliveryWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = ForemanStore(":memory:")
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(_project())
        self.store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        self.store.save_task(Task(id="t1", sprint_id="s1", project_id="p1", title="T"))
        self.store.save_run(
            Run(
                id="r1",
                task_id="t1",
                project_id="p1",
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
            )
        )
        self.store.save_notification_destination(_destination())
        self.clock = _Clock()

    def _worker(self, transport: _StubTransport) -> NotificationDeliveryWorker:
        return NotificationDeliveryWorker(
            self.store,
            transport_factory=lambda destination: transport,
            utc_now=self.clock,
        )

    def _queue(self, event_id: str = "event-1") -> NotificationDelivery:
        return self.store.enqueue_notification_delivery(
            project_id="p1",
            destination_id="dst-ops",
            kind=ATTENTION,
            # The run behind the moment being announced: `notification.failed`
            # is written against it when a delivery is finally given up on.
            payload={"summary": "something happened", "event": {"run_id": "r1"}},
            task_id="t1",
            event_id=event_id,
            next_attempt_at=_iso(self.clock.now),
        )

    def test_a_reachable_destination_is_delivered_once(self) -> None:
        delivery = self._queue()
        transport = _StubTransport()
        result = self._worker(transport).drain("p1")

        self.assertEqual((result.attempted, result.delivered), (1, 1))
        self.assertEqual(len(transport.sent), 1)
        stored = self.store.get_notification_delivery(delivery.id)
        self.assertEqual(stored.status, "delivered")
        self.assertEqual(stored.attempts, 1)
        self.assertIsNotNone(stored.delivered_at)
        # A delivered row is not due again.
        self.assertEqual(self._worker(transport).drain("p1").attempted, 0)

    def test_a_failing_destination_is_retried_on_a_backoff(self) -> None:
        delivery = self._queue()
        transport = _StubTransport(fail_times=1)
        worker = self._worker(transport)

        first = worker.drain("p1")
        self.assertEqual((first.retrying, first.delivered), (1, 0))
        stored = self.store.get_notification_delivery(delivery.id)
        self.assertEqual(stored.status, "pending")
        self.assertEqual(stored.attempts, 1)
        self.assertIn("connection refused", stored.last_error)

        # Not due yet: a retry that ignored its own backoff would hammer a
        # destination that is down.
        self.assertEqual(worker.drain("p1").attempted, 0)

        self.clock.advance(retry_delay_seconds(1) + 1)
        second = worker.drain("p1")
        self.assertEqual((second.attempted, second.delivered), (1, 1))
        self.assertEqual(
            self.store.get_notification_delivery(delivery.id).status, "delivered"
        )

    def test_a_destination_that_stays_down_is_recorded_not_retried_forever(self) -> None:
        delivery = self._queue()
        transport = _StubTransport(fail_times=99)
        worker = self._worker(transport)

        for _ in range(DEFAULT_MAX_ATTEMPTS + 3):
            worker.drain("p1")
            self.clock.advance(3600)

        stored = self.store.get_notification_delivery(delivery.id)
        self.assertEqual(stored.status, "failed")
        self.assertEqual(stored.attempts, DEFAULT_MAX_ATTEMPTS)
        self.assertIn("connection refused", stored.last_error)
        # Given up, so no further attempts are made.
        self.assertEqual(transport.attempts, DEFAULT_MAX_ATTEMPTS)

        failures = [
            event
            for event in self.store.list_events(project_id="p1")
            if event.event_type == "notification.failed"
        ]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].payload["destination"], "ops")
        self.assertEqual(failures[0].payload["attempts"], DEFAULT_MAX_ATTEMPTS)

    def test_a_transport_that_explodes_is_a_retry_not_a_crash(self) -> None:
        self._queue()

        class _Exploding:
            def send(self, destination, delivery):
                raise RuntimeError("the transport itself is broken")

        worker = NotificationDeliveryWorker(
            self.store,
            transport_factory=lambda destination: _Exploding(),
            utc_now=self.clock,
        )
        with self.assertLogs("foreman.notifications", level="INFO"):
            result = worker.drain("p1")
        self.assertEqual(result.retrying, 1)

    def test_a_destination_disabled_after_queueing_fails_its_deliveries(self) -> None:
        delivery = self._queue()
        destination = self.store.get_notification_destination("dst-ops")
        destination.enabled = False
        self.store.save_notification_destination(destination)

        result = self._worker(_StubTransport()).drain("p1")
        self.assertEqual(result.failed, 1)
        stored = self.store.get_notification_delivery(delivery.id)
        self.assertEqual(stored.status, "failed")
        self.assertIn("no longer enabled", stored.last_error)

    def test_one_drain_is_bounded(self) -> None:
        for index in range(5):
            self._queue(event_id=f"event-{index}")
        transport = _StubTransport()
        result = self._worker(transport).drain("p1", limit=2)
        self.assertEqual(result.attempted, 2)
        self.assertEqual(self.store.count_notification_deliveries("p1")["pending"], 3)


# ── webhook transport ────────────────────────────────────────────────────


class _StubResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _StubResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class WebhookTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requests: list[object] = []
        self.delivery = NotificationDelivery(
            id="ntf-1",
            project_id="p1",
            destination_id="dst-ops",
            kind=ATTENTION,
            payload={"summary": "Foreman needs attention: Ship it"},
        )

    def _opener(self, status: int = 200):
        def _open(request, timeout=None):
            self.requests.append(request)
            return _StubResponse(status)

        return _open

    def test_it_posts_the_payload_as_json_with_identifying_headers(self) -> None:
        transport = WebhookTransport(opener=self._opener())
        detail = transport.send(
            _destination(config={"headers": {"X-Team": "ops"}}), self.delivery
        )

        self.assertEqual(detail, "HTTP 200")
        request = self.requests[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, "https://example.test/hook")
        self.assertEqual(json.loads(request.data)["summary"], self.delivery.payload["summary"])
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(request.get_header("X-foreman-event"), ATTENTION)
        self.assertEqual(request.get_header("X-foreman-delivery"), "ntf-1")
        self.assertEqual(request.get_header("X-team"), "ops")
        self.assertIsNone(request.get_header("X-foreman-signature"))

    def test_a_named_secret_signs_the_exact_bytes_sent(self) -> None:
        import hashlib
        import hmac

        transport = WebhookTransport(
            opener=self._opener(), environ={"HOOK_KEY": "s3cret"}
        )
        transport.send(_destination(config={"secret_env": "HOOK_KEY"}), self.delivery)

        request = self.requests[0]
        expected = hmac.new(b"s3cret", request.data, hashlib.sha256).hexdigest()
        self.assertEqual(request.get_header("X-foreman-signature"), f"sha256={expected}")

    def test_a_missing_secret_sends_unsigned_rather_than_dropping(self) -> None:
        transport = WebhookTransport(opener=self._opener(), environ={})
        with self.assertLogs("foreman.notifications", level="WARNING"):
            transport.send(_destination(config={"secret_env": "HOOK_KEY"}), self.delivery)
        self.assertIsNone(self.requests[0].get_header("X-foreman-signature"))

    def test_an_error_response_is_a_transport_error(self) -> None:
        transport = WebhookTransport(opener=self._opener(status=503))
        with self.assertRaises(TransportError):
            transport.send(_destination(), self.delivery)

    def test_an_http_error_and_a_network_error_are_transport_errors(self) -> None:
        def _raise_http(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 500, "boom", {}, None)

        def _raise_url(request, timeout=None):
            raise urllib.error.URLError("name or service not known")

        for opener in (_raise_http, _raise_url):
            with self.assertRaises(TransportError):
                WebhookTransport(opener=opener).send(_destination(), self.delivery)

    def test_a_webhook_target_must_be_an_http_url(self) -> None:
        self.assertEqual(
            validate_target("webhook", " https://example.test/hook "),
            "https://example.test/hook",
        )
        with self.assertRaises(NotificationError):
            validate_target("webhook", "example.test/hook")


# ── the engine end to end ────────────────────────────────────────────────


class _ScriptedRunner:
    def __init__(self, behaviours) -> None:
        self._behaviours = list(behaviours)

    def run(self, config: AgentRunConfig):
        yield from self._behaviours.pop(0)(config)


def _reviewer_approves(config: AgentRunConfig):
    yield AgentEvent("agent.started", payload={"command": "fake"})
    yield AgentEvent(
        "agent.message",
        payload={"text": "Tests passed and the diff is sound.\n\nAPPROVE", "phase": "result"},
    )
    yield AgentEvent("agent.completed", payload={"session_id": "s"})


def _developer_commits(config: AgentRunConfig):
    work_dir = Path(config.working_dir)
    (work_dir / "feature.py").write_text("def feature():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: implement the feature"],
        cwd=work_dir,
        check=True,
        capture_output=True,
    )
    yield AgentEvent("agent.started", payload={"command": "fake"})
    yield AgentEvent(
        "agent.message",
        payload={"text": "Implemented the feature with tests.\nTASK_COMPLETE", "phase": "result"},
    )
    yield AgentEvent("agent.completed", payload={"session_id": "s"})


class EngineDeliveryTests(unittest.TestCase):
    """The acceptance criterion, driven through a real workflow run."""

    def _workspace(self) -> tuple[Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        repo = root / "repo"
        repo.mkdir()
        for args in (
            ("init",),
            ("checkout", "-b", "main"),
            ("config", "user.email", "t@example.com"),
            ("config", "user.name", "T"),
        ):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
        (repo / "README.md").write_text("# r\n", encoding="utf-8")
        (repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
        return repo, root / "foreman.db"

    def _seed(self, store: ForemanStore, repo: Path, **settings: object) -> Project:
        project = Project(
            id="p1",
            name="Foreman",
            repo_path=str(repo),
            workflow_id="development",
            default_branch="main",
            settings={
                "task_selection_mode": "directed",
                "test_command": "true",
                "default_model": "m",
                **settings,
            },
        )
        store.save_project(project)
        store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        store.save_task(
            Task(
                id="t1",
                sprint_id="s1",
                project_id="p1",
                title="Implement",
                status="todo",
                acceptance_criteria="Implemented the feature with tests.",
            )
        )
        store.save_notification_destination(_destination())
        return project

    def _run(self, store: ForemanStore, project: Project) -> None:
        """Run the one seeded task.

        Scoped to the task on purpose: an unscoped pass would also find the
        sprint fully resolved and raise a `sprint_resolved` attention turn,
        which is a second (correct) delivery this test is not about.
        """

        orchestrator = ForemanOrchestrator(
            store,
            agent_runners={
                "claude_code": _ScriptedRunner([_developer_commits, _reviewer_approves])
            },
        )
        orchestrator.run_project(project.id, task_id="t1")

    def _kinds(self, store: ForemanStore) -> list[str]:
        return [
            delivery.kind
            for delivery in store.list_notification_deliveries("p1")
        ]

    def test_attention_delivers_the_human_gate_and_not_the_completion(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project = self._seed(
                store, repo, notification="attention", merge_approval="human"
            )
            self._run(store, project)

            self.assertEqual(store.get_task("t1").workflow_current_step, "merge_approval")
            self.assertEqual(self._kinds(store), [HUMAN_GATE])
            paused = next(
                event
                for event in store.list_events(task_id="t1")
                if event.event_type == "workflow.paused"
            )
            self.assertEqual(paused.payload["notify"], "attention")

    def test_attention_delivers_an_attention_turn_but_not_a_completion(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project = self._seed(store, repo, notification="attention")
            self._run(store, project)

            self.assertEqual(store.get_task("t1").status, "done")
            completions = [
                event
                for event in store.list_events(task_id="t1")
                if event.event_type == "task.completed"
            ]
            self.assertEqual(len(completions), 1)
            self.assertEqual(completions[0].payload["notify"], "attention")
            self.assertEqual(self._kinds(store), [])

            # An attention turn on the same project does deliver.
            orchestrator = ForemanOrchestrator(store)
            run = store.save_run(
                Run(
                    id="r-att",
                    task_id="t1",
                    project_id="p1",
                    role_id="developer",
                    workflow_step="develop",
                    agent_backend="claude_code",
                    status="running",
                )
            )
            orchestrator._emit_attention_needed(run, "t1", "task_blocked")
            self.assertEqual(self._kinds(store), [ATTENTION])

    def test_all_adds_the_completion(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project = self._seed(store, repo, notification="all")
            self._run(store, project)

            self.assertEqual(store.get_task("t1").status, "done")
            self.assertEqual(self._kinds(store), [TASK_COMPLETED])

    def test_none_delivers_nothing(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project = self._seed(store, repo, notification="none", merge_approval="human")
            self._run(store, project)

            self.assertEqual(self._kinds(store), [])

    def test_an_unreachable_destination_never_fails_the_task(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project = self._seed(store, repo, notification="all")
            self._run(store, project)

            self.assertEqual(store.get_task("t1").status, "done")
            clock = _Clock()
            worker = NotificationDeliveryWorker(
                store,
                transport_factory=lambda destination: _StubTransport(fail_times=99),
                utc_now=clock,
            )
            for _ in range(DEFAULT_MAX_ATTEMPTS):
                worker.drain("p1")
                clock.advance(3600)

            self.assertEqual(store.get_task("t1").status, "done")
            self.assertEqual(
                store.count_notification_deliveries("p1"),
                {"pending": 0, "delivered": 0, "failed": 1},
            )


class ServeDeliveryTests(unittest.TestCase):
    """The resident engine is what works the retry schedule."""

    def test_each_pass_drains_what_is_due(self) -> None:
        from foreman.serve import ResidentEngine

        store = ForemanStore(":memory:")
        self.addCleanup(store.close)
        store.initialize()
        store.save_project(_project())
        store.save_notification_destination(_destination())
        store.enqueue_notification_delivery(
            project_id="p1", destination_id="dst-ops", kind=ATTENTION, payload={}
        )

        class _IdleOrchestrator:
            holder_id = "h"
            command_poll = None

            def run_project(self, project_id, *, task_id=None, maintenance=True):
                from foreman.orchestrator import ProjectRunResult

                return ProjectRunResult(
                    project_id=project_id,
                    executed_task_ids=(),
                    blocked_task_ids=(),
                    stop_reason="idle",
                )

        transport = _StubTransport()
        engine = ResidentEngine(
            store=store,
            project_id="p1",
            orchestrator=_IdleOrchestrator(),
            notification_worker=NotificationDeliveryWorker(
                store, transport_factory=lambda destination: transport
            ),
        )
        engine.run(once=True)

        self.assertEqual(len(transport.sent), 1)
        self.assertEqual(store.count_notification_deliveries("p1")["delivered"], 1)


# ── CLI ──────────────────────────────────────────────────────────────────


class NotifyCliTests(unittest.TestCase):
    """`foreman notify add|list|remove|test|deliveries`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(
            Project(
                id="project-1",
                name="Foreman Demo",
                repo_path=self._tmp.name,
                workflow_id="development",
                settings={"notification": "all"},
            )
        )

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cli_argv(*args, "--db", str(self.db_path)),
            env=cli_env(),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_add_then_list_shows_the_destination_and_the_policy(self) -> None:
        added = self.run_cli(
            "notify",
            "add",
            "project-1",
            "--name",
            "ops",
            "--url",
            "https://example.test/hook",
            "--secret-env",
            "HOOK_KEY",
        )
        self.assertEqual(added.returncode, 0, added.stderr)

        destination = self.store.find_notification_destination("project-1", "ops")
        self.assertEqual(destination.target, "https://example.test/hook")
        self.assertEqual(destination.config, {"secret_env": "HOOK_KEY"})

        listed = self.run_cli("notify", "list", "project-1")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("notification=all", listed.stdout)
        self.assertIn("https://example.test/hook", listed.stdout)
        self.assertIn("signed=yes", listed.stdout)

    def test_add_refuses_a_bad_url_a_bad_header_and_a_duplicate_name(self) -> None:
        bad_url = self.run_cli(
            "notify", "add", "project-1", "--name", "ops", "--url", "example.test"
        )
        self.assertEqual(bad_url.returncode, 1)
        self.assertIn("http", bad_url.stderr)

        bad_header = self.run_cli(
            "notify",
            "add",
            "project-1",
            "--name",
            "ops",
            "--url",
            "https://example.test/hook",
            "--header",
            "nocolon",
        )
        self.assertEqual(bad_header.returncode, 1)

        first = self.run_cli(
            "notify", "add", "project-1", "--name", "ops", "--url", "https://example.test/hook"
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        duplicate = self.run_cli(
            "notify", "add", "project-1", "--name", "ops", "--url", "https://other.test/hook"
        )
        self.assertEqual(duplicate.returncode, 1)
        self.assertIn("already has a destination", duplicate.stderr)

    def test_deliveries_reports_what_failed_and_why(self) -> None:
        self.store.save_notification_destination(
            NotificationDestination(
                id="dst-1",
                project_id="project-1",
                name="ops",
                target="https://example.test/hook",
            )
        )
        delivery = self.store.enqueue_notification_delivery(
            project_id="project-1",
            destination_id="dst-1",
            kind=ATTENTION,
            payload={},
        )
        self.store.settle_notification_delivery(
            delivery.id,
            status="failed",
            attempts=5,
            last_error="TransportError: connection refused",
            now="2026-09-08T12:00:00.000000Z",
        )

        result = self.run_cli("notify", "deliveries", "project-1", "--status", "failed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("connection refused", result.stdout)
        self.assertIn("attempts=5/5", result.stdout)

    def test_remove_takes_the_destination_and_its_deliveries(self) -> None:
        self.run_cli(
            "notify", "add", "project-1", "--name", "ops", "--url", "https://example.test/hook"
        )
        removed = self.run_cli("notify", "remove", "project-1", "ops")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertIsNone(self.store.find_notification_destination("project-1", "ops"))

        missing = self.run_cli("notify", "remove", "project-1", "ops")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("Unknown notification destination", missing.stderr)


class PayloadTests(unittest.TestCase):
    def test_the_payload_carries_enough_to_read_without_calling_back(self) -> None:
        task = Task(
            id="t1",
            sprint_id="s1",
            project_id="p1",
            title="Ship it",
            status="blocked",
            branch_name="feat/t1",
        )
        payload = build_payload(
            kind=ATTENTION,
            event=_event("engine.attention_needed", {"trigger": "task_blocked"}),
            project=_project(),
            task=task,
        )
        self.assertEqual(payload["summary"], "Foreman needs attention: Ship it")
        self.assertEqual(payload["task"]["branch"], "feat/t1")
        self.assertEqual(payload["event"]["payload"]["trigger"], "task_blocked")
        # Must survive the JSON round trip a webhook body is.
        self.assertEqual(json.loads(json.dumps(payload))["kind"], ATTENTION)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
