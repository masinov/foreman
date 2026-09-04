"""Coverage for the resident engine, the project engine lock, and JSON logs."""

from __future__ import annotations

import io
import json
import logging
import re
import subprocess
import threading
import unittest
import unittest.mock
from pathlib import Path
import tempfile

from foreman.engine_lock import (
    EngineBusyError,
    EngineLock,
    EngineLockLostError,
)
import foreman
from foreman.logs import (
    AGENT_LIFECYCLE_EVENT_TYPES,
    HIGH_VOLUME_EVENT_TYPES,
    JsonLinesFormatter,
    configure_json_logging,
    event_log_level,
    log_event,
)
from foreman.models import Project, Run, Sprint, Task
from foreman.orchestrator import (
    ForemanOrchestrator,
    OrchestratorError,
    ProjectRunResult,
)
from foreman.runner.base import AgentEvent, AgentRunConfig
from foreman.runner.process import EngineShutdown
from foreman.serve import ResidentEngine, ServeResult, serve_project
from foreman.store import ForemanStore


def _seed_project(store: ForemanStore, repo_path: str, *, tasks: int = 0) -> Project:
    """Persist a project with an active sprint and ``tasks`` todo tasks."""

    project = Project(
        id="project-1",
        name="Foreman Demo",
        repo_path=repo_path,
        workflow_id="development",
    )
    sprint = Sprint(
        id="sprint-1",
        project_id=project.id,
        title="Resident engine",
        status="active",
        order_index=0,
    )
    store.save_project(project)
    store.save_sprint(sprint)
    for index in range(tasks):
        store.save_task(
            Task(
                id=f"task-{index + 1}",
                sprint_id=sprint.id,
                project_id=project.id,
                title=f"Task {index + 1}",
                status="todo",
                order_index=index,
            )
        )
    return project


class _StubOrchestrator:
    """Orchestrator stand-in that replays scripted pass results.

    The loop under test only needs ``run_project`` and ``holder_id``; using a
    stub keeps timing assertions deterministic and never launches an agent.
    """

    def __init__(self, results, holder_id: str = "holder-stub") -> None:
        self._results = list(results)
        self.holder_id = holder_id
        self.calls: list[bool] = []
        self.targets: list[str | None] = []
        self.blocked: list[tuple[str, str]] = []
        self.stopped: list[tuple[str, str]] = []
        self.released: list[str] = []
        self.engine_events: list[tuple[str, dict]] = []
        self.command_poll = None

    def run_project(
        self, project_id: str, *, task_id: str | None = None, maintenance: bool = True
    ):
        self.calls.append(maintenance)
        self.targets.append(task_id)
        if not self._results:
            raise EngineShutdown("SIGTERM")
        outcome = self._results.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def block_task_for_error(self, task_id: str, reason: str, **_: object) -> None:
        self.blocked.append((task_id, reason))

    def stop_task(self, task_id: str, *, reason: str) -> None:
        self.stopped.append((task_id, reason))

    def release_task(self, task_id: str) -> None:
        self.released.append(task_id)

    def record_engine_event(self, *, project_id, event_type, payload, **_: object):
        self.engine_events.append((event_type, payload))
        return None


def _idle(project_id: str = "project-1") -> ProjectRunResult:
    return ProjectRunResult(
        project_id=project_id,
        executed_task_ids=(),
        blocked_task_ids=(),
        stop_reason="idle",
    )


def _executed(*task_ids: str, project_id: str = "project-1") -> ProjectRunResult:
    return ProjectRunResult(
        project_id=project_id,
        executed_task_ids=tuple(task_ids),
        blocked_task_ids=(),
        stop_reason="idle",
    )


class _FakeClock:
    """Monotonic clock advanced only by the sleeps the engine performs."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now

    @property
    def total_slept(self) -> float:
        return sum(self.sleeps)


class EngineLockTests(unittest.TestCase):
    """The per-project engine lease: refusal, renewal, loss, release."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.repo_path = self._temp.name
        self.db_path = Path(self._temp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.project = _seed_project(self.store, self.repo_path)

    def _lock(self, holder_id: str, **kwargs: object) -> EngineLock:
        kwargs.setdefault("heartbeat_seconds", 0)
        kwargs.setdefault("on_lost", lambda _lock: None)
        return EngineLock(
            store=self.store,
            project_id=self.project.id,
            holder_id=holder_id,
            **kwargs,  # type: ignore[arg-type]
        )

    def test_second_engine_is_refused_and_told_who_holds_the_lock(self) -> None:
        first = self._lock("holder-a")
        first.acquire()
        self.addCleanup(first.release)

        with self.assertRaises(EngineBusyError) as caught:
            self._lock("holder-b").acquire()

        self.assertEqual(caught.exception.holder_id, "holder-a")
        self.assertIn("holder-a", str(caught.exception))
        self.assertIn(self.project.id, str(caught.exception))

    def test_lock_is_reacquirable_after_release(self) -> None:
        first = self._lock("holder-a")
        first.acquire()
        self.assertTrue(first.release())

        second = self._lock("holder-b")
        second.acquire()
        self.addCleanup(second.release)
        self.assertTrue(second.held)

    def test_expired_lock_can_be_taken_over(self) -> None:
        # A crashed engine leaves an active lease behind; it must not hold the
        # project past its expiry.
        first = self._lock("holder-crashed", duration_seconds=-1.0)
        first.acquire()

        second = self._lock("holder-b")
        second.acquire()
        self.addCleanup(second.release)
        self.assertTrue(second.held)

    def test_heartbeat_thread_renews_on_its_own_connection(self) -> None:
        opened: list[ForemanStore] = []

        def factory() -> ForemanStore:
            store = ForemanStore(self.db_path)
            opened.append(store)
            return store

        renewed = threading.Event()
        original_renew = ForemanStore.renew_lease

        def observed_renew(self_store, **kwargs):  # type: ignore[no-untyped-def]
            result = original_renew(self_store, **kwargs)
            if kwargs.get("resource_type") == "engine":
                renewed.set()
            return result

        lock = self._lock(
            "holder-a",
            heartbeat_seconds=0.01,
            store_factory=factory,
        )
        with unittest.mock.patch.object(ForemanStore, "renew_lease", observed_renew):
            lock.acquire()
            self.addCleanup(lock.release)
            self.assertTrue(renewed.wait(timeout=5.0), "heartbeat never renewed the lease")

        self.assertEqual(len(opened), 1, "heartbeat must open exactly one own connection")
        self.assertIsNot(opened[0], self.store)
        self.assertFalse(lock.lost)

        lease = self.store.get_active_lease(
            project_id=self.project.id,
            resource_type="engine",
            resource_id=self.project.id,
        )
        assert lease is not None
        self.assertEqual(lease.holder_id, "holder-a")

    def test_refused_renewal_marks_the_lock_lost_and_calls_back(self) -> None:
        lost = threading.Event()
        lock = self._lock(
            "holder-a",
            heartbeat_seconds=0.01,
            on_lost=lambda _lock: lost.set(),
        )
        lock.acquire()
        self.addCleanup(lock.release)

        # Force-expire the lease out from under the heartbeat, exactly as a
        # takeover by a second engine would.
        self.store.expire_resource_leases(
            project_id=self.project.id,
            resource_type="engine",
            resource_id=self.project.id,
            force=True,
        )

        self.assertTrue(lost.wait(timeout=5.0), "lock loss was never signalled")
        self.assertTrue(lock.lost)
        self.assertFalse(lock.held)
        self.assertIn("refused on renewal", lock.lost_reason or "")
        with self.assertRaises(EngineLockLostError):
            lock.check()

    def test_lost_lock_release_does_not_steal_a_successor(self) -> None:
        lost = threading.Event()
        lock = self._lock(
            "holder-a",
            heartbeat_seconds=0.01,
            on_lost=lambda _lock: lost.set(),
        )
        lock.acquire()
        self.store.expire_resource_leases(
            project_id=self.project.id,
            resource_type="engine",
            resource_id=self.project.id,
            force=True,
        )
        self.assertTrue(lost.wait(timeout=5.0))

        successor = self._lock("holder-b")
        successor.acquire()
        self.addCleanup(successor.release)

        self.assertFalse(lock.release())
        lease = self.store.get_active_lease(
            project_id=self.project.id,
            resource_type="engine",
            resource_id=self.project.id,
        )
        assert lease is not None
        self.assertEqual(lease.holder_id, "holder-b")

    def test_context_manager_releases_on_unhandled_error(self) -> None:
        with self.assertRaises(RuntimeError):
            with self._lock("holder-a"):
                raise RuntimeError("boom")

        self.assertIsNone(
            self.store.get_active_lease(
                project_id=self.project.id,
                resource_type="engine",
                resource_id=self.project.id,
            )
        )


class ResidentEngineLoopTests(unittest.TestCase):
    """Pass sequencing, maintenance gating, idle waking, and backoff."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = Path(self._temp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.project = _seed_project(self.store, self._temp.name)
        self.clock = _FakeClock()

    def _engine(self, orchestrator, **kwargs: object) -> ResidentEngine:
        kwargs.setdefault("poll_seconds", 5.0)
        return ResidentEngine(
            store=self.store,
            project_id=self.project.id,
            orchestrator=orchestrator,  # type: ignore[arg-type]
            sleep=self.clock.sleep,
            monotonic=self.clock.monotonic,
            **kwargs,  # type: ignore[arg-type]
        )

    def test_once_runs_exactly_one_pass_and_exits_zero(self) -> None:
        orchestrator = _StubOrchestrator([_idle()])
        result = self._engine(orchestrator).run(once=True)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stop_reason, "once")
        self.assertEqual(result.passes, 1)
        self.assertEqual(orchestrator.calls, [True], "startup pass must run maintenance")
        self.assertEqual(self.clock.sleeps, [], "--once must not wait")

    def test_maintenance_runs_at_startup_and_after_work_but_not_on_idle_wakes(self) -> None:
        orchestrator = _StubOrchestrator(
            [_idle(), _idle(), _executed("task-1"), _idle()]
        )
        self._engine(orchestrator).run()

        # startup, idle wake, idle wake, pass after work executed, then the
        # scripted results run out and the stub raises EngineShutdown.
        self.assertEqual(orchestrator.calls, [True, False, False, True, False])

    def test_idle_engine_only_polls_data_version_between_wakes(self) -> None:
        orchestrator = _StubOrchestrator([_idle()])
        reads = {"count": 0}
        real_data_version = self.store.data_version

        def counting_data_version() -> int:
            reads["count"] += 1
            return real_data_version()

        engine = self._engine(orchestrator, poll_seconds=5.0, tick_seconds=0.5)
        with unittest.mock.patch.object(
            self.store, "data_version", counting_data_version
        ):
            engine.run()

        # One idle wait of 5s in 0.5s ticks: one baseline read plus ten ticks.
        # No task selection happens in between — the stub was called twice, once
        # for the idle pass and once for the shutdown that ends the loop.
        self.assertEqual(len(orchestrator.calls), 2)
        self.assertEqual(reads["count"], 11)
        self.assertAlmostEqual(self.clock.total_slept, 5.0, places=6)

    def test_idle_wake_is_immediate_when_another_connection_commits(self) -> None:
        orchestrator = _StubOrchestrator([_idle()])
        writer = ForemanStore(self.db_path)
        self.addCleanup(writer.close)

        engine = self._engine(orchestrator, poll_seconds=60.0, tick_seconds=0.5)

        original_sleep = self.clock.sleep
        state = {"ticks": 0}

        def sleep_then_write(seconds: float) -> None:
            original_sleep(seconds)
            state["ticks"] += 1
            if state["ticks"] == 2:
                # Another process queues work while this engine is idle.
                writer.save_task(
                    Task(
                        id="task-late",
                        sprint_id="sprint-1",
                        project_id=self.project.id,
                        title="Arrived after the engine went idle",
                        status="todo",
                    )
                )

        engine._sleep = sleep_then_write
        engine.run()

        # The engine woke on the commit at 1.0s, far inside the 60s poll, and
        # ran another pass immediately.
        self.assertAlmostEqual(self.clock.total_slept, 1.0, places=6)
        self.assertEqual(len(orchestrator.calls), 2)

    def test_poll_interval_bounds_the_idle_wait_without_any_commit(self) -> None:
        orchestrator = _StubOrchestrator([_idle(), _idle()])
        engine = self._engine(orchestrator, poll_seconds=2.0, tick_seconds=0.5)
        engine.run()

        self.assertAlmostEqual(self.clock.total_slept, 4.0, places=6)

    def test_task_failure_is_isolated_with_a_doubling_backoff(self) -> None:
        from foreman.orchestrator import TaskExecutionError

        orchestrator = _StubOrchestrator(
            [
                TaskExecutionError("task-1", OrchestratorError("first boom")),
                TaskExecutionError("task-2", RuntimeError("second boom")),
                TaskExecutionError("task-3", RuntimeError("third boom")),
            ]
        )
        result = self._engine(orchestrator, tick_seconds=1.0).run()

        self.assertEqual(
            orchestrator.blocked,
            [
                ("task-1", "first boom"),
                ("task-2", "second boom"),
                ("task-3", "third boom"),
            ],
        )
        self.assertAlmostEqual(self.clock.total_slept, 5.0 + 10.0 + 20.0, places=6)
        self.assertEqual(
            result.blocked_task_ids, ("task-1", "task-2", "task-3")
        )

    def test_backoff_resets_after_a_successful_pass(self) -> None:
        from foreman.orchestrator import TaskExecutionError

        orchestrator = _StubOrchestrator(
            [
                TaskExecutionError("task-1", RuntimeError("boom")),
                TaskExecutionError("task-2", RuntimeError("boom")),
                _executed("task-3"),
                TaskExecutionError("task-4", RuntimeError("boom")),
            ]
        )
        self._engine(orchestrator, poll_seconds=0.0, tick_seconds=1.0).run()

        # 5 + 10 (doubling), then a clean pass resets, so the fourth failure
        # waits 5 again rather than 20.
        self.assertAlmostEqual(self.clock.total_slept, 5.0 + 10.0 + 5.0, places=6)

    def test_backoff_is_capped(self) -> None:
        from foreman.serve import MAX_BACKOFF_SECONDS, _Backoff

        backoff = _Backoff()
        delays = [backoff.record_failure() for _ in range(12)]
        self.assertEqual(delays[:4], [5.0, 10.0, 20.0, 40.0])
        self.assertTrue(all(delay <= MAX_BACKOFF_SECONDS for delay in delays))
        self.assertEqual(delays[-1], MAX_BACKOFF_SECONDS)

    def test_shutdown_stops_cleanly_with_exit_zero(self) -> None:
        orchestrator = _StubOrchestrator([_idle(), EngineShutdown("SIGTERM")])
        result = self._engine(orchestrator, poll_seconds=0.0).run()

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stop_reason, "stopped")
        self.assertIn("SIGTERM", result.detail or "")

    def test_keyboard_interrupt_stops_cleanly(self) -> None:
        orchestrator = _StubOrchestrator([KeyboardInterrupt()])
        result = self._engine(orchestrator).run()

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stop_reason, "stopped")

    def test_project_level_error_ends_the_service_non_zero(self) -> None:
        orchestrator = _StubOrchestrator([OrchestratorError("Unknown project 'x'.")])
        result = self._engine(orchestrator).run()

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stop_reason, "error")

    def test_lost_lock_stops_the_loop_non_zero(self) -> None:
        class _LostLock:
            lost = True
            lost_reason = "Engine lock was taken over."

        orchestrator = _StubOrchestrator([_idle()])
        engine = self._engine(orchestrator, lock=_LostLock())
        result = engine.run()

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stop_reason, "lock_lost")
        self.assertEqual(orchestrator.calls, [], "no pass may start without the lock")


class ResidentEngineIsolationTests(unittest.TestCase):
    """The real orchestrator path: a failing task is blocked, not fatal."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = Path(self._temp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.project = _seed_project(self.store, self._temp.name, tasks=2)

    def _orchestrator(self, error: BaseException) -> ForemanOrchestrator:
        outer = self

        class _FailingOrchestrator(ForemanOrchestrator):
            """Real selection, leasing, and blocking; the step itself explodes.

            Nothing here launches an agent: ``run_task`` is replaced before any
            runner or executor is reached.
            """

            def run_task(self, project, workflow, task):  # type: ignore[override]
                outer.attempted.append(task.id)
                raise error

        self.attempted: list[str] = []
        return _FailingOrchestrator(self.store)

    def test_failed_task_is_blocked_with_reason_and_attention_event(self) -> None:
        orchestrator = self._orchestrator(OrchestratorError("git checkout failed"))
        clock = _FakeClock()
        engine = ResidentEngine(
            store=self.store,
            project_id=self.project.id,
            orchestrator=orchestrator,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        result = engine.run(once=True)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(self.attempted, ["task-1"])

        blocked = self.store.get_task("task-1")
        assert blocked is not None
        self.assertEqual(blocked.status, "blocked")
        self.assertEqual(blocked.blocked_reason, "git checkout failed")

        attention = [
            event
            for event in self.store.list_events(task_id="task-1")
            if event.event_type == "engine.attention_needed"
        ]
        self.assertEqual(len(attention), 1)
        self.assertEqual(attention[0].payload["trigger"], "task_blocked")

        system_runs = self.store.list_runs(task_id="task-1")
        self.assertTrue(
            any(run.outcome == "blocked" for run in system_runs),
            "the block must leave a system run behind for the digest",
        )

    def test_service_continues_with_the_next_task_after_a_failure(self) -> None:
        orchestrator = self._orchestrator(RuntimeError("agent exploded"))
        clock = _FakeClock()
        engine = ResidentEngine(
            store=self.store,
            project_id=self.project.id,
            orchestrator=orchestrator,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        # Two todo tasks, both failing. Once both are parked, end the loop the
        # way a takeover would, so the test does not depend on a signal.
        class _Lock:
            def __init__(self) -> None:
                self.lost = False
                self.lost_reason = None

            def trip(self) -> None:
                self.lost = True
                self.lost_reason = "test stop"

        lock = _Lock()
        engine.lock = lock  # type: ignore[assignment]

        def sleeper(seconds: float) -> None:
            clock.sleep(seconds)
            if len(self.attempted) >= 2:
                lock.trip()

        engine._sleep = sleeper
        engine.run()

        self.assertEqual(self.attempted, ["task-1", "task-2"])
        for task_id in ("task-1", "task-2"):
            task = self.store.get_task(task_id)
            assert task is not None
            self.assertEqual(task.status, "blocked")
            self.assertEqual(task.blocked_reason, "agent exploded")

    def test_blocking_a_failed_task_releases_its_lease(self) -> None:
        orchestrator = self._orchestrator(RuntimeError("boom"))
        clock = _FakeClock()
        ResidentEngine(
            store=self.store,
            project_id=self.project.id,
            orchestrator=orchestrator,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        ).run(once=True)

        self.assertIsNone(
            self.store.get_active_lease(
                project_id=self.project.id,
                resource_type="task",
                resource_id="task-1",
            )
        )


class ServeProjectTests(unittest.TestCase):
    """`serve_project` acquires, holds, and always releases the engine lock."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = Path(self._temp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.project = _seed_project(self.store, self._temp.name)

    def _engine_lease(self):
        return self.store.get_active_lease(
            project_id=self.project.id,
            resource_type="engine",
            resource_id=self.project.id,
        )

    def _lock(self, holder_id: str) -> EngineLock:
        return EngineLock(
            store=self.store,
            project_id=self.project.id,
            holder_id=holder_id,
            heartbeat_seconds=0,
            on_lost=lambda _lock: None,
        )

    def test_once_pass_releases_the_lock_on_exit(self) -> None:
        orchestrator = _StubOrchestrator([_idle()], holder_id="holder-serve")
        result = serve_project(
            store=self.store,
            project_id=self.project.id,
            orchestrator=orchestrator,  # type: ignore[arg-type]
            once=True,
            lock=self._lock("holder-serve"),
        )

        self.assertIsInstance(result, ServeResult)
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(self._engine_lease(), "the lock must be released on exit")

    def test_shutdown_releases_the_lock(self) -> None:
        orchestrator = _StubOrchestrator([EngineShutdown("SIGTERM")])
        result = serve_project(
            store=self.store,
            project_id=self.project.id,
            orchestrator=orchestrator,  # type: ignore[arg-type]
            lock=self._lock("holder-serve"),
        )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stop_reason, "stopped")
        self.assertIsNone(self._engine_lease())

    def test_unhandled_error_releases_the_lock(self) -> None:
        class _Exploding(_StubOrchestrator):
            def run_project(self, project_id, *, task_id=None, maintenance=True):
                raise ValueError("unexpected")

        with self.assertRaises(ValueError):
            serve_project(
                store=self.store,
                project_id=self.project.id,
                orchestrator=_Exploding([]),  # type: ignore[arg-type]
                lock=self._lock("holder-serve"),
            )

        self.assertIsNone(self._engine_lease())

    def test_second_serve_is_refused_while_the_first_holds_the_lock(self) -> None:
        held = self._lock("holder-resident")
        held.acquire()
        self.addCleanup(held.release)

        stream = io.StringIO()
        logger = logging.getLogger("foreman.serve.busytest")
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonLinesFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        self.addCleanup(logger.removeHandler, handler)

        with self.assertRaises(EngineBusyError) as caught:
            serve_project(
                store=self.store,
                project_id=self.project.id,
                orchestrator=_StubOrchestrator([_idle()]),  # type: ignore[arg-type]
                once=True,
                lock=self._lock("holder-second"),
                logger=logger,
            )

        self.assertIn("holder-resident", str(caught.exception))

        # A supervisor reading only the process log must be able to tell a
        # refused start from a crash.
        logged = [
            json.loads(line) for line in stream.getvalue().splitlines() if line
        ]
        self.assertEqual([entry["event"] for entry in logged], ["serve.lock_busy"])
        self.assertEqual(logged[0]["level"], "ERROR")
        self.assertEqual(logged[0]["project_id"], self.project.id)
        self.assertEqual(logged[0]["holder_id"], "holder-resident")
        self.assertTrue(logged[0]["expires_at"])

    def test_run_project_is_refused_while_a_resident_engine_holds_the_lock(self) -> None:
        held = self._lock("holder-resident")
        held.acquire()
        self.addCleanup(held.release)

        orchestrator = ForemanOrchestrator(self.store)
        lock = EngineLock(
            store=self.store,
            project_id=self.project.id,
            holder_id=orchestrator.holder_id,
            heartbeat_seconds=0,
            on_lost=lambda _lock: None,
        )
        with self.assertRaises(EngineBusyError) as caught:
            lock.acquire()

        self.assertIn("holder-resident", str(caught.exception))


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _git_workspace(test: unittest.TestCase) -> tuple[Path, Path]:
    """A committed git repo and a database path beside it, cleaned up with the test."""

    temp_dir = tempfile.TemporaryDirectory()
    test.addCleanup(temp_dir.cleanup)
    root = Path(temp_dir.name)
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "main")
    _git(repo, "config", "user.email", "foreman-tests@example.com")
    _git(repo, "config", "user.name", "Foreman Tests")
    (repo / "README.md").write_text("# repo\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    return repo, root / "foreman.db"


class ServeShutdownTests(unittest.TestCase):
    """SIGTERM during an agent step: settle, release, exit 0."""

    def _workspace(self) -> tuple[Path, Path]:
        return _git_workspace(self)

    def test_shutdown_mid_step_settles_the_run_and_releases_the_lock(self) -> None:
        repo, db_path = self._workspace()

        class _ShutdownRunner:
            """Fake agent runner: starts, then the engine is told to stop."""

            def run(self, config: AgentRunConfig):
                yield AgentEvent("agent.started", payload={"command": "fake"})
                raise EngineShutdown("SIGTERM")

        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="project-1",
                name="Resident",
                repo_path=str(repo),
                workflow_id="development",
                default_branch="main",
                settings={
                    "task_selection_mode": "directed",
                    "test_command": "true",
                    "default_model": "m",
                },
            )
            store.save_project(project)
            store.save_sprint(
                Sprint(id="sprint-1", project_id=project.id, title="S", status="active")
            )
            store.save_task(
                Task(
                    id="task-1",
                    sprint_id="sprint-1",
                    project_id=project.id,
                    title="Implement",
                    status="todo",
                    acceptance_criteria="Implemented.",
                )
            )

            orchestrator = ForemanOrchestrator(
                store,
                agent_runners={"claude_code": _ShutdownRunner()},
                native_step_heartbeat_seconds=0.0001,
            )
            lock = EngineLock(
                store=store,
                project_id=project.id,
                holder_id=orchestrator.holder_id,
                heartbeat_seconds=0,
                on_lost=lambda _lock: None,
            )

            with unittest.mock.patch(
                "foreman.serve.terminate_all", return_value=0
            ) as terminated:
                result = serve_project(
                    store=store,
                    project_id=project.id,
                    orchestrator=orchestrator,
                    lock=lock,
                )

            # A requested stop is not a failure.
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stop_reason, "stopped")
            terminated.assert_called_once()

            runs = [
                run
                for run in store.list_runs(task_id="task-1")
                if run.role_id != "_builtin:orchestrator"
            ]
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].status, "killed")
            killed = [
                event
                for event in store.list_events(run_id=runs[0].id)
                if event.event_type == "agent.killed"
            ]
            self.assertEqual(killed[0].payload["gate_type"], "shutdown")

            resumable = store.get_task("task-1")
            assert resumable is not None
            self.assertEqual(resumable.status, "in_progress")
            self.assertEqual(resumable.workflow_current_step, "develop")

            self.assertIsNone(
                store.get_active_lease(
                    project_id=project.id,
                    resource_type="engine",
                    resource_id=project.id,
                ),
                "the engine lock must be released on a shutdown",
            )


class JsonLogFormatterTests(unittest.TestCase):
    """One JSON object per line on stderr, with the engine's identity fields."""

    def _capture(self, name: str = "foreman.test") -> tuple[logging.Logger, io.StringIO]:
        stream = io.StringIO()
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonLinesFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        self.addCleanup(logger.removeHandler, handler)
        return logger, stream

    def _lines(self, stream: io.StringIO) -> list[dict]:
        return [json.loads(line) for line in stream.getvalue().splitlines() if line]

    def test_each_event_is_one_json_object_with_the_expected_fields(self) -> None:
        logger, stream = self._capture()
        log_event(
            logger,
            "serve.pass_completed",
            project_id="project-1",
            task_id="task-1",
            run_id="run-1",
            step="develop",
            stop_reason="idle",
        )

        lines = self._lines(stream)
        self.assertEqual(len(lines), 1)
        entry = lines[0]
        self.assertEqual(entry["event"], "serve.pass_completed")
        self.assertEqual(entry["level"], "INFO")
        self.assertEqual(entry["project_id"], "project-1")
        self.assertEqual(entry["task_id"], "task-1")
        self.assertEqual(entry["run_id"], "run-1")
        self.assertEqual(entry["step"], "develop")
        self.assertEqual(entry["stop_reason"], "idle")
        self.assertTrue(entry["ts"].endswith("Z"))

    def test_unknown_identity_fields_are_omitted_not_null(self) -> None:
        logger, stream = self._capture()
        log_event(logger, "serve.started", project_id="project-1")

        entry = self._lines(stream)[0]
        self.assertNotIn("task_id", entry)
        self.assertNotIn("run_id", entry)
        self.assertNotIn("step", entry)

    def test_multiline_and_oversized_values_stay_on_one_line(self) -> None:
        logger, stream = self._capture()
        log_event(
            logger,
            "serve.task_failed",
            level=logging.ERROR,
            project_id="project-1",
            reason="line one\nline two\n" + ("x" * 5000),
        )

        raw = stream.getvalue().strip()
        self.assertEqual(len(raw.splitlines()), 1)
        entry = json.loads(raw)
        self.assertEqual(entry["level"], "ERROR")
        self.assertLess(len(entry["reason"]), 700)
        self.assertIn("+", entry["reason"])

    def test_unserializable_values_do_not_lose_the_line(self) -> None:
        logger, stream = self._capture()
        log_event(logger, "serve.started", project_id="p", weird=object())

        entry = self._lines(stream)[0]
        self.assertIn("object object at", entry["weird"])

    def test_configure_json_logging_is_idempotent(self) -> None:
        stream = io.StringIO()
        configure_json_logging(stream=stream, logger_name="foreman.configtest")
        configure_json_logging(stream=stream, logger_name="foreman.configtest")
        logger = logging.getLogger("foreman.configtest")
        self.addCleanup(lambda: [logger.removeHandler(h) for h in list(logger.handlers)])

        log_event(logger, "serve.started", project_id="project-1")

        self.assertEqual(len(stream.getvalue().splitlines()), 1)

    def test_orchestrator_mirrors_persisted_events_to_the_process_log(self) -> None:
        stream = io.StringIO()
        configure_json_logging(stream=stream, logger_name="foreman.orchestrator")
        logger = logging.getLogger("foreman.orchestrator")
        self.addCleanup(lambda: [logger.removeHandler(h) for h in list(logger.handlers)])

        with tempfile.TemporaryDirectory() as temp_dir:
            with ForemanStore(Path(temp_dir) / "foreman.db") as store:
                store.initialize()
                project = _seed_project(store, temp_dir, tasks=1)
                orchestrator = ForemanOrchestrator(store)
                task = store.get_task("task-1")
                assert task is not None
                orchestrator.block_task_for_error(task.id, "database was unreachable")

        events = [
            entry
            for entry in self._lines(stream)
            if entry["event"] == "engine.attention_needed"
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["project_id"], project.id)
        self.assertEqual(events[0]["task_id"], "task-1")
        self.assertEqual(events[0]["payload"]["trigger"], "task_blocked")


class EventLogLevelTests(unittest.TestCase):
    """The narrative is mirrored at INFO; the agent firehose at DEBUG."""

    def test_narrative_families_are_info(self) -> None:
        for event_type in (
            "engine.attention_needed",
            "engine.merge",
            "workflow.step_started",
            "workflow.model_selected",
            "gate.cost_exceeded",
            "signal.task_created",
        ):
            with self.subTest(event_type=event_type):
                self.assertEqual(event_log_level(event_type), logging.INFO)

    def test_agent_lifecycle_events_are_info(self) -> None:
        for event_type in (
            "agent.started",
            "agent.session",
            "agent.message",
            "agent.command",
            "agent.file_change",
            "agent.completed",
            "agent.error",
            "agent.infra_error",
            "agent.killed",
            "agent.rate_limit",
        ):
            with self.subTest(event_type=event_type):
                self.assertEqual(event_log_level(event_type), logging.INFO)

    def test_high_volume_agent_events_are_debug(self) -> None:
        for event_type in (
            "agent.raw_output",
            "agent.prompt",
            "agent.tool_use",
            "agent.tool_result",
            "agent.cost_update",
            "agent.tick",
        ):
            with self.subTest(event_type=event_type):
                self.assertEqual(event_log_level(event_type), logging.DEBUG)

    def test_unknown_event_types_default_to_debug(self) -> None:
        self.assertEqual(event_log_level("something.unheard_of"), logging.DEBUG)

    def test_every_emitted_agent_event_is_classified_explicitly(self) -> None:
        """`agent.*` is enumerated, so a new one must be placed deliberately.

        The other four families are prefix-matched and need no maintenance. This
        one does: a runner change that adds an `agent.*` event would otherwise
        fall through to the DEBUG default and quietly vanish from the resident
        engine's log. `fix/runner-progress-lines` added three
        (`agent.session`, `agent.tick`, `agent.tool_result`) — this test is what
        makes the next three deliberate too.
        """

        package = Path(foreman.__file__).parent
        emitted: set[str] = set()
        for source in package.rglob("*.py"):
            emitted.update(
                re.findall(r'"(agent\.[a-z_]+)"', source.read_text(encoding="utf-8"))
            )

        self.assertTrue(emitted, "found no agent event literals to check")
        classified = AGENT_LIFECYCLE_EVENT_TYPES | HIGH_VOLUME_EVENT_TYPES
        self.assertEqual(
            emitted - classified,
            set(),
            "unclassified agent event types: add each to AGENT_LIFECYCLE_EVENT_TYPES "
            "(the step narrative) or HIGH_VOLUME_EVENT_TYPES (the output firehose) "
            "in foreman/logs.py",
        )

    def test_raw_output_is_not_mirrored_at_info_but_a_workflow_event_is(self) -> None:
        """A resident engine's log must not drown in agent output."""

        stream = io.StringIO()
        configure_json_logging(
            stream=stream, level=logging.INFO, logger_name="foreman.orchestrator"
        )
        logger = logging.getLogger("foreman.orchestrator")
        self.addCleanup(lambda: [logger.removeHandler(h) for h in list(logger.handlers)])

        with tempfile.TemporaryDirectory() as temp_dir:
            with ForemanStore(Path(temp_dir) / "foreman.db") as store:
                store.initialize()
                project = _seed_project(store, temp_dir, tasks=1)
                orchestrator = ForemanOrchestrator(store)
                run = Run(
                    id="run-1",
                    task_id="task-1",
                    project_id=project.id,
                    role_id="developer",
                    workflow_step="develop",
                    agent_backend="claude_code",
                    status="running",
                )
                store.save_run(run)

                orchestrator._emit_event(
                    run, "agent.raw_output", {"text": "chatter " * 50}
                )
                orchestrator._emit_event(
                    run, "workflow.step_started", {"step": "develop"}
                )

                # Both are still persisted in full; only the mirroring differs.
                persisted = {
                    event.event_type for event in store.list_events(run_id=run.id)
                }
                self.assertEqual(
                    persisted, {"agent.raw_output", "workflow.step_started"}
                )

        logged = [
            json.loads(line) for line in stream.getvalue().splitlines() if line
        ]
        self.assertEqual([entry["event"] for entry in logged], ["workflow.step_started"])
        self.assertEqual(logged[0]["level"], "INFO")

    def test_raw_output_is_mirrored_when_the_handler_drops_to_debug(self) -> None:
        stream = io.StringIO()
        configure_json_logging(
            stream=stream, level=logging.DEBUG, logger_name="foreman.orchestrator"
        )
        logger = logging.getLogger("foreman.orchestrator")
        self.addCleanup(lambda: [logger.removeHandler(h) for h in list(logger.handlers)])

        with tempfile.TemporaryDirectory() as temp_dir:
            with ForemanStore(Path(temp_dir) / "foreman.db") as store:
                store.initialize()
                project = _seed_project(store, temp_dir, tasks=1)
                orchestrator = ForemanOrchestrator(store)
                run = Run(
                    id="run-1",
                    task_id="task-1",
                    project_id=project.id,
                    role_id="developer",
                    workflow_step="develop",
                    agent_backend="claude_code",
                    status="running",
                )
                store.save_run(run)
                orchestrator._emit_event(run, "agent.raw_output", {"text": "chatter"})

        logged = [
            json.loads(line) for line in stream.getvalue().splitlines() if line
        ]
        self.assertEqual([entry["event"] for entry in logged], ["agent.raw_output"])
        self.assertEqual(logged[0]["level"], "DEBUG")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class EngineCommandStartupTests(unittest.TestCase):
    """What a starting engine does with commands left behind by a dead one."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = Path(self._temp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.project = _seed_project(self.store, self._temp.name, tasks=1)
        self.clock = _FakeClock()

    def _engine(self, orchestrator, **kwargs: object) -> ResidentEngine:
        kwargs.setdefault("poll_seconds", 5.0)
        return ResidentEngine(
            store=self.store,
            project_id=self.project.id,
            orchestrator=orchestrator,  # type: ignore[arg-type]
            sleep=self.clock.sleep,
            monotonic=self.clock.monotonic,
            **kwargs,  # type: ignore[arg-type]
        )

    def _enqueue(self, command: str, **kwargs: object):
        return self.store.enqueue_engine_command(
            project_id=self.project.id,
            command=command,
            requested_by=kwargs.pop("requested_by", "alice"),
            **kwargs,  # type: ignore[arg-type]
        )

    def test_stale_pause_stop_task_and_shutdown_are_rejected_at_startup(self) -> None:
        pause = self._enqueue("pause")
        stop = self._enqueue("stop_task", task_id="task-1")
        shutdown = self._enqueue("shutdown")

        self._engine(_StubOrchestrator([_idle()])).run(once=True)

        for command in (pause, stop, shutdown):
            settled = self.store.get_engine_command(command.id)
            assert settled is not None
            self.assertEqual(settled.status, "rejected", command.command)
            self.assertEqual(settled.result_detail, "no engine was resident")
            self.assertTrue(settled.completed_at)

    def test_a_rejected_stale_command_does_not_pause_the_starting_engine(self) -> None:
        self._enqueue("pause")
        orchestrator = _StubOrchestrator([_idle()])

        result = self._engine(orchestrator).run(once=True)

        self.assertEqual(result.passes, 1, "the engine must still run its pass")
        self.assertEqual(len(orchestrator.calls), 1)

    def test_a_pending_resume_survives_startup_and_is_applied(self) -> None:
        resume = self._enqueue("resume")

        self._engine(_StubOrchestrator([_idle()])).run(once=True)

        settled = self.store.get_engine_command(resume.id)
        assert settled is not None
        self.assertEqual(settled.status, "completed")

    def test_a_pending_run_task_survives_startup_and_targets_the_first_pass(self) -> None:
        command = self._enqueue("run_task", task_id="task-1")
        orchestrator = _StubOrchestrator([_executed("task-1")])

        self._engine(orchestrator).run(once=True)

        settled = self.store.get_engine_command(command.id)
        assert settled is not None
        self.assertEqual(settled.status, "completed")
        self.assertEqual(orchestrator.targets, ["task-1"])

    def test_rejection_is_recorded_as_an_engine_event(self) -> None:
        self._enqueue("pause")
        orchestrator = _StubOrchestrator([_idle()])

        self._engine(orchestrator).run(once=True)

        kinds = [event_type for event_type, _ in orchestrator.engine_events]
        self.assertIn("engine.command_rejected", kinds)


class EngineCommandLoopTests(unittest.TestCase):
    """Command semantics against an idle engine, with a scripted orchestrator."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = Path(self._temp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.project = _seed_project(self.store, self._temp.name, tasks=2)
        self.clock = _FakeClock()

    def _engine(self, orchestrator, **kwargs: object) -> ResidentEngine:
        kwargs.setdefault("poll_seconds", 5.0)
        return ResidentEngine(
            store=self.store,
            project_id=self.project.id,
            orchestrator=orchestrator,  # type: ignore[arg-type]
            sleep=self.clock.sleep,
            monotonic=self.clock.monotonic,
            **kwargs,  # type: ignore[arg-type]
        )

    def _enqueue(self, command: str, *, store=None, **kwargs: object):
        return (store or self.store).enqueue_engine_command(
            project_id=self.project.id,
            command=command,
            requested_by=kwargs.pop("requested_by", "alice"),
            **kwargs,  # type: ignore[arg-type]
        )

    def _settled(self, command):
        settled = self.store.get_engine_command(command.id)
        assert settled is not None
        return settled

    def _schedule(self, engine, schedule: dict) -> dict:
        """Queue commands from another connection at given idle ticks.

        `pause`, `stop_task`, and `shutdown` only mean something to an engine
        that is already resident — queued beforehand they are rejected as
        stale — so these tests hand them to the engine mid-loop, exactly as a
        dashboard or a second terminal would.
        """

        writer = ForemanStore(self.db_path)
        self.addCleanup(writer.close)
        state: dict = {"ticks": 0, "queued": []}
        original_sleep = engine._sleep

        def sleeper(seconds: float) -> None:
            original_sleep(seconds)
            state["ticks"] += 1
            entry = schedule.get(state["ticks"])
            if entry is not None:
                name, kwargs = entry
                state["queued"].append(self._enqueue(name, store=writer, **kwargs))

        engine._sleep = sleeper
        return state

    def test_pause_stops_the_engine_picking_up_new_work(self) -> None:
        """A paused engine runs no further passes but stays in its loop."""

        orchestrator = _StubOrchestrator([_idle(), _idle(), _idle(), _idle()])
        engine = self._engine(orchestrator, poll_seconds=60.0, tick_seconds=0.5)
        # Pause at the first idle tick; shut down later so the loop can end.
        state = self._schedule(
            engine,
            {1: ("pause", {}), 5: ("shutdown", {"requested_by": "bob"})},
        )

        result = engine.run()

        pause, shutdown = state["queued"]
        self.assertEqual(self._settled(pause).status, "completed")
        self.assertEqual(self._settled(shutdown).status, "completed")
        self.assertEqual(
            result.passes,
            1,
            "only the pass before the pause may run",
        )
        self.assertEqual(len(orchestrator.calls), 1)
        self.assertEqual(result.exit_code, 0)

    def test_a_paused_engine_still_answers_shutdown(self) -> None:
        orchestrator = _StubOrchestrator([_idle(), _idle(), _idle(), _idle()])
        engine = self._engine(orchestrator, poll_seconds=60.0, tick_seconds=0.5)
        state = self._schedule(
            engine,
            {1: ("pause", {}), 3: ("shutdown", {"requested_by": "bob"})},
        )

        result = engine.run()

        _pause, shutdown = state["queued"]
        self.assertEqual(result.stop_reason, "stopped")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(self._settled(shutdown).status, "completed")

    def test_a_paused_engine_keeps_heartbeating_its_lock(self) -> None:
        """Pausing is not releasing: the project stays owned by this engine."""

        lock = EngineLock(
            store=self.store,
            project_id=self.project.id,
            holder_id="holder-paused",
            heartbeat_seconds=0,
            on_lost=lambda _lock: None,
        )
        lock.acquire()
        self.addCleanup(lock.release)

        orchestrator = _StubOrchestrator([_idle(), _idle(), _idle(), _idle()])
        engine = self._engine(orchestrator, poll_seconds=60.0, tick_seconds=0.5)
        engine.lock = lock
        self._schedule(
            engine,
            {1: ("pause", {}), 3: ("shutdown", {"requested_by": "bob"})},
        )

        engine.run()

        self.assertIsNotNone(
            self.store.get_engine_lock(self.project.id),
            "a paused engine must keep holding the project",
        )

    def test_resume_lets_the_engine_run_a_pass_again(self) -> None:
        orchestrator = _StubOrchestrator([_idle(), _idle(), _idle(), _idle()])
        engine = self._engine(orchestrator, poll_seconds=60.0, tick_seconds=0.5)
        state = self._schedule(
            engine,
            {
                1: ("pause", {}),
                3: ("resume", {"requested_by": "bob"}),
                5: ("shutdown", {"requested_by": "bob"}),
            },
        )

        result = engine.run()

        _pause, resume, _shutdown = state["queued"]
        self.assertEqual(self._settled(resume).status, "completed")
        self.assertGreaterEqual(
            result.passes, 2, "the engine must run again after the resume"
        )

    def test_resume_on_a_running_engine_is_completed_as_a_no_op(self) -> None:
        resume = self._enqueue("resume")

        self._engine(_StubOrchestrator([_idle()])).run(once=True)

        settled = self._settled(resume)
        self.assertEqual(settled.status, "completed")
        self.assertIn("already running", settled.result_detail or "")

    def test_shutdown_while_idle_exits_zero_and_stops_the_loop(self) -> None:
        orchestrator = _StubOrchestrator([_idle(), _idle(), _idle()])
        engine = self._engine(orchestrator, poll_seconds=60.0, tick_seconds=0.5)
        state = self._schedule(engine, {1: ("shutdown", {})})

        result = engine.run()

        (shutdown,) = state["queued"]
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stop_reason, "stopped")
        self.assertEqual(
            result.passes, 1, "the shutdown must end the loop, not start a pass"
        )
        settled = self._settled(shutdown)
        self.assertEqual(settled.status, "completed")
        self.assertIn("shutting down", settled.result_detail or "")

    def test_run_task_targets_the_next_pass_regardless_of_sprint_order(self) -> None:
        command = self._enqueue("run_task", task_id="task-2")
        orchestrator = _StubOrchestrator([_executed("task-2"), _idle()])

        self._engine(orchestrator).run(once=True)

        self.assertEqual(orchestrator.targets, ["task-2"])
        settled = self._settled(command)
        self.assertEqual(settled.status, "completed")
        self.assertIn("task-2", settled.result_detail or "")

    def test_a_targeted_task_is_only_run_once(self) -> None:
        self._enqueue("run_task", task_id="task-2")
        orchestrator = _StubOrchestrator([_executed("task-2"), _idle()])

        self._engine(orchestrator).run()

        self.assertEqual(
            orchestrator.targets[:2],
            ["task-2", None],
            "the second pass must fall back to normal sprint selection",
        )

    def test_run_task_is_rejected_for_a_task_in_another_project(self) -> None:
        self.store.save_project(
            Project(
                id="project-2",
                name="Other",
                repo_path=self._temp.name,
                workflow_id="development",
            )
        )
        self.store.save_sprint(
            Sprint(id="sprint-2", project_id="project-2", title="S", status="active")
        )
        self.store.save_task(
            Task(
                id="foreign-task",
                sprint_id="sprint-2",
                project_id="project-2",
                title="Not ours",
                status="todo",
            )
        )
        command = self._enqueue("run_task", task_id="foreign-task")
        orchestrator = _StubOrchestrator([_idle()])

        self._engine(orchestrator).run(once=True)

        settled = self._settled(command)
        self.assertEqual(settled.status, "rejected")
        self.assertIn("project-2", settled.result_detail or "")
        self.assertEqual(orchestrator.targets, [None])

    def test_run_task_is_rejected_for_a_blocked_task(self) -> None:
        task = self.store.get_task("task-1")
        assert task is not None
        task.status = "blocked"
        task.blocked_reason = "needs a human"
        self.store.save_task(task)
        command = self._enqueue("run_task", task_id="task-1")

        self._engine(_StubOrchestrator([_idle()])).run(once=True)

        settled = self._settled(command)
        self.assertEqual(settled.status, "rejected")
        self.assertIn("blocked", settled.result_detail or "")

    def test_run_task_is_rejected_for_an_unknown_task(self) -> None:
        command = self.store.enqueue_engine_command(
            project_id=self.project.id,
            command="run_task",
            requested_by="alice",
            task_id=None,
        )

        self._engine(_StubOrchestrator([_idle()])).run(once=True)

        self.assertEqual(self._settled(command).status, "rejected")

    def test_run_task_accepts_a_resumable_in_progress_task(self) -> None:
        task = self.store.get_task("task-1")
        assert task is not None
        task.status = "in_progress"
        task.workflow_current_step = "develop"
        self.store.save_task(task)
        command = self._enqueue("run_task", task_id="task-1")

        orchestrator = _StubOrchestrator([_executed("task-1")])
        self._engine(orchestrator).run(once=True)

        self.assertEqual(self._settled(command).status, "completed")
        self.assertEqual(orchestrator.targets, ["task-1"])

    def test_run_task_is_rejected_for_an_in_progress_task_with_no_resume_point(self) -> None:
        task = self.store.get_task("task-1")
        assert task is not None
        task.status = "in_progress"
        task.workflow_current_step = None
        self.store.save_task(task)
        command = self._enqueue("run_task", task_id="task-1")

        self._engine(_StubOrchestrator([_idle()])).run(once=True)

        self.assertEqual(self._settled(command).status, "rejected")

    def test_stop_task_is_rejected_when_the_engine_is_idle(self) -> None:
        orchestrator = _StubOrchestrator([_idle(), _idle(), _idle()])
        engine = self._engine(orchestrator, poll_seconds=60.0, tick_seconds=0.5)
        state = self._schedule(
            engine,
            {
                1: ("stop_task", {"task_id": "task-1"}),
                3: ("shutdown", {"requested_by": "bob"}),
            },
        )

        engine.run()

        command = state["queued"][0]
        settled = self._settled(command)
        self.assertEqual(settled.status, "rejected")
        self.assertIn("idle", settled.result_detail or "")
        task = self.store.get_task("task-1")
        assert task is not None
        self.assertEqual(task.status, "todo", "a rejected stop must not touch the task")

    def test_every_command_is_acknowledged_before_it_is_applied(self) -> None:
        command = self._enqueue("resume")

        self._engine(_StubOrchestrator([_idle()])).run(once=True)

        settled = self._settled(command)
        self.assertTrue(
            settled.acknowledged_at,
            "the engine must record that it picked the command up",
        )
        self.assertTrue(settled.completed_at)

    def test_an_applied_command_is_recorded_as_an_engine_event(self) -> None:
        self._enqueue("resume")
        orchestrator = _StubOrchestrator([_idle()])

        self._engine(orchestrator).run(once=True)

        applied = [
            payload
            for event_type, payload in orchestrator.engine_events
            if event_type == "engine.command_applied"
        ]
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0]["command"], "resume")
        self.assertEqual(applied[0]["requested_by"], "alice")

    def test_commands_are_applied_oldest_first(self) -> None:
        self._enqueue("pause")
        self._enqueue("resume")
        orchestrator = _StubOrchestrator([_idle()])

        result = self._engine(orchestrator).run(once=True)

        # pause then resume leaves the engine running, so the pass happens.
        self.assertEqual(result.passes, 1)
        self.assertEqual(len(orchestrator.calls), 1)

    def test_enqueuing_from_another_connection_wakes_an_idle_engine(self) -> None:
        """The insert commits elsewhere, so the data_version wait sees it."""

        writer = ForemanStore(self.db_path)
        self.addCleanup(writer.close)
        orchestrator = _StubOrchestrator([_idle(), _idle()])
        engine = self._engine(orchestrator, poll_seconds=60.0, tick_seconds=0.5)

        state = {"ticks": 0, "command": None}
        original_sleep = self.clock.sleep

        def sleep_then_enqueue(seconds: float) -> None:
            original_sleep(seconds)
            state["ticks"] += 1
            if state["ticks"] == 2:
                state["command"] = self._enqueue(
                    "shutdown", store=writer, requested_by="dashboard"
                )

        engine._sleep = sleep_then_enqueue
        result = engine.run()

        # Woken at 1.0s — two 0.5s ticks — not at the 60s poll deadline.
        self.assertAlmostEqual(self.clock.total_slept, 1.0, places=6)
        self.assertEqual(result.stop_reason, "stopped")
        settled = self.store.get_engine_command(state["command"].id)
        assert settled is not None
        self.assertEqual(settled.status, "completed")


class _StepNeverInterrupted(BaseException):
    """Raised when the command poll failed to stop a blocked agent step.

    A ``BaseException`` so the orchestrator's ``except Exception`` fallbacks
    cannot turn a broken command poll into a quietly failed agent step: the
    test must fail loudly instead.
    """


class _CommandingRunner:
    """Fake agent runner that blocks on ticks until a command stops it.

    The agent step never finishes on its own: it emits ``agent.tick`` events,
    which is what a real backend does while an agent works quietly. On a
    scheduled tick it queues a command *from another connection*, the way a
    dashboard or a second terminal would, and the engine's ``command_poll``
    picks it up on the next tick. No `claude` or `codex` binary is launched.
    """

    #: Enough ticks to prove the poll fired, few enough to fail fast if it did not.
    MAX_TICKS = 30

    def __init__(
        self,
        db_path: Path,
        *,
        project_id: str,
        schedule: dict[int, tuple[str, str | None, str]],
    ) -> None:
        self.db_path = db_path
        self.project_id = project_id
        self.schedule = schedule
        #: Commands queued so far, in order, across every step of every task.
        self.queued: list = []
        self.ticks = 0

    @classmethod
    def for_command(
        cls,
        db_path: Path,
        *,
        project_id: str,
        command: str,
        requested_by: str,
        task_id: str | None = None,
    ) -> "_CommandingRunner":
        """A runner that queues exactly one command on its first tick."""

        return cls(
            db_path,
            project_id=project_id,
            schedule={0: (command, task_id, requested_by)},
        )

    @property
    def command_id(self) -> str | None:
        return self.queued[0].id if self.queued else None

    def run(self, config: AgentRunConfig):
        yield AgentEvent("agent.started", payload={"command": "fake"})
        for index in range(self.MAX_TICKS):
            entry = self.schedule.pop(index, None)
            if entry is not None:
                name, task_id, requested_by = entry
                with ForemanStore(self.db_path) as writer:
                    self.queued.append(
                        writer.enqueue_engine_command(
                            project_id=self.project_id,
                            command=name,
                            requested_by=requested_by,
                            task_id=task_id,
                        )
                    )
            self.ticks += 1
            yield AgentEvent("agent.tick", payload={"elapsed_seconds": index})
        raise _StepNeverInterrupted(
            f"the command poll never stopped the agent step ({self.MAX_TICKS} ticks)"
        )


class EngineCommandDuringAgentStepTests(unittest.TestCase):
    """pause, stop_task, and shutdown against a running agent step."""

    def _serve(self, runner: _CommandingRunner, db_path: Path, store: ForemanStore, **kwargs):
        orchestrator = ForemanOrchestrator(
            store,
            agent_runners={"claude_code": runner},
            native_step_heartbeat_seconds=0.0001,
        )
        lock = EngineLock(
            store=store,
            project_id="project-1",
            holder_id=orchestrator.holder_id,
            heartbeat_seconds=0,
            on_lost=lambda _lock: None,
        )
        return serve_project(
            store=store,
            project_id="project-1",
            orchestrator=orchestrator,
            lock=lock,
            **kwargs,
        )

    def _seed(self, store: ForemanStore, repo: Path) -> None:
        store.initialize()
        project = Project(
            id="project-1",
            name="Resident",
            repo_path=str(repo),
            workflow_id="development",
            default_branch="main",
            settings={
                "task_selection_mode": "directed",
                "test_command": "true",
                "default_model": "m",
            },
        )
        store.save_project(project)
        store.save_sprint(
            Sprint(id="sprint-1", project_id=project.id, title="S", status="active")
        )
        store.save_task(
            Task(
                id="task-1",
                sprint_id="sprint-1",
                project_id=project.id,
                title="Implement",
                status="todo",
                acceptance_criteria="Implemented.",
            )
        )

    @staticmethod
    def _agent_runs(store: ForemanStore) -> list[Run]:
        return [
            run
            for run in store.list_runs(task_id="task-1")
            if run.role_id != "_builtin:orchestrator"
        ]

    def test_pause_kills_the_agent_step_and_leaves_the_task_resumable(self) -> None:
        repo, db_path = _git_workspace(self)
        with ForemanStore(db_path) as store:
            self._seed(store, repo)
            runner = _CommandingRunner.for_command(
                db_path, project_id="project-1", command="pause", requested_by="alice"
            )

            with unittest.mock.patch(
                "foreman.serve.terminate_all", return_value=1
            ) as terminated:
                result = self._serve(runner, db_path, store, once=True)

            terminated.assert_called()
            self.assertEqual(result.exit_code, 0)

            runs = self._agent_runs(store)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].status, "killed")
            killed = [
                event
                for event in store.list_events(run_id=runs[0].id)
                if event.event_type == "agent.killed"
            ]
            self.assertEqual(killed[0].payload["gate_type"], "command")

            # A paused engine changes no task status.
            task = store.get_task("task-1")
            assert task is not None
            self.assertEqual(task.status, "in_progress")
            self.assertEqual(task.workflow_current_step, "develop")
            self.assertIsNone(task.blocked_reason)

            assert runner.command_id is not None
            command = store.get_engine_command(runner.command_id)
            assert command is not None
            self.assertEqual(command.status, "completed")
            self.assertTrue(command.acknowledged_at)
            self.assertIn("resumable", command.result_detail or "")

            applied = [
                event
                for event in store.list_events(task_id="task-1")
                if event.event_type == "engine.command_applied"
            ]
            self.assertEqual(len(applied), 1)
            self.assertEqual(applied[0].payload["command"], "pause")

    def test_pause_releases_the_task_lease_so_the_task_is_not_pinned(self) -> None:
        repo, db_path = _git_workspace(self)
        with ForemanStore(db_path) as store:
            self._seed(store, repo)
            runner = _CommandingRunner.for_command(
                db_path, project_id="project-1", command="pause", requested_by="alice"
            )
            with unittest.mock.patch("foreman.serve.terminate_all", return_value=1):
                self._serve(runner, db_path, store, once=True)

            self.assertIsNone(
                store.get_active_lease(
                    project_id="project-1", resource_type="task", resource_id="task-1"
                )
            )

    def test_stop_task_kills_the_step_and_blocks_the_task_naming_the_requester(self) -> None:
        repo, db_path = _git_workspace(self)
        with ForemanStore(db_path) as store:
            self._seed(store, repo)
            runner = _CommandingRunner.for_command(
                db_path,
                project_id="project-1",
                command="stop_task",
                requested_by="dana",
                task_id="task-1",
            )

            with unittest.mock.patch(
                "foreman.serve.terminate_all", return_value=1
            ) as terminated:
                result = self._serve(runner, db_path, store, once=True)

            terminated.assert_called()
            self.assertEqual(result.exit_code, 0)

            runs = self._agent_runs(store)
            self.assertEqual(runs[0].status, "killed")

            task = store.get_task("task-1")
            assert task is not None
            self.assertEqual(task.status, "blocked")
            self.assertEqual(task.blocked_reason, "Stopped by dana")

            assert runner.command_id is not None
            command = store.get_engine_command(runner.command_id)
            assert command is not None
            self.assertEqual(command.status, "completed")
            self.assertIn("dana", command.result_detail or "")

            applied = [
                event
                for event in store.list_events(task_id="task-1")
                if event.event_type == "engine.command_applied"
            ]
            self.assertEqual(applied[0].payload["command"], "stop_task")

    def test_stop_task_for_a_different_task_is_rejected_and_the_step_continues(self) -> None:
        repo, db_path = _git_workspace(self)
        with ForemanStore(db_path) as store:
            self._seed(store, repo)
            store.save_task(
                Task(
                    id="task-2",
                    sprint_id="sprint-1",
                    project_id="project-1",
                    title="Other",
                    status="todo",
                    order_index=1,
                )
            )
            # Ask to stop a task the engine is *not* running; then pause, so
            # the step ends on the engine's terms rather than by running out of
            # ticks. The gap between the two proves the step kept going.
            runner = _CommandingRunner(
                db_path,
                project_id="project-1",
                schedule={
                    0: ("stop_task", "task-2", "dana"),
                    5: ("pause", None, "dana"),
                },
            )
            with unittest.mock.patch("foreman.serve.terminate_all", return_value=1):
                self._serve(runner, db_path, store, once=True)

            stop, _pause = runner.queued
            command = store.get_engine_command(stop.id)
            assert command is not None
            self.assertEqual(command.status, "rejected")
            self.assertIn("task-1", command.result_detail or "")

            untouched = store.get_task("task-2")
            assert untouched is not None
            self.assertEqual(untouched.status, "todo")
            self.assertGreater(
                runner.ticks, 5, "a rejected stop must not end the agent step"
            )

            rejected = [
                event
                for event in store.list_events(project_id="project-1")
                if event.event_type == "engine.command_rejected"
            ]
            self.assertTrue(rejected, "a rejection must leave an event behind")

    def test_shutdown_kills_the_step_releases_the_lock_and_exits_zero(self) -> None:
        repo, db_path = _git_workspace(self)
        with ForemanStore(db_path) as store:
            self._seed(store, repo)
            runner = _CommandingRunner.for_command(
                db_path, project_id="project-1", command="shutdown", requested_by="ops"
            )

            with unittest.mock.patch("foreman.serve.terminate_all", return_value=1):
                result = self._serve(runner, db_path, store)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stop_reason, "stopped")

            runs = self._agent_runs(store)
            self.assertEqual(runs[0].status, "killed")

            task = store.get_task("task-1")
            assert task is not None
            self.assertEqual(task.status, "in_progress")
            self.assertEqual(task.workflow_current_step, "develop")

            self.assertIsNone(
                store.get_engine_lock("project-1"),
                "shutdown must release the engine lock",
            )
            assert runner.command_id is not None
            command = store.get_engine_command(runner.command_id)
            assert command is not None
            self.assertEqual(command.status, "completed")
