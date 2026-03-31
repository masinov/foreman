"""Tests for run and prompt retention — sprint-26 history lifecycle expansion."""

from __future__ import annotations

import unittest

from foreman.models import Event, Project, Run, Sprint, Task, utc_now_text
from foreman.store import ForemanStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PAST = "2020-01-01T00:00:00.000000Z"
_CUTOFF = "2025-01-01T00:00:00.000000Z"
_RECENT = "2026-01-01T00:00:00.000000Z"

_TERMINAL_STATUSES = ("completed", "failed", "killed", "timeout")
_ACTIVE_STATUSES = ("pending", "running")


def _make_store() -> ForemanStore:
    store = ForemanStore(":memory:")
    store.initialize()
    return store


def _project(store: ForemanStore, pid: str = "proj-1") -> Project:
    p = Project(
        id=pid,
        name="Test",
        repo_path="/tmp/test",
        workflow_id="development",
        created_at=_PAST,
        updated_at=_PAST,
    )
    store.save_project(p)
    return p


def _sprint(store: ForemanStore, project_id: str, sid: str = "sprint-1") -> Sprint:
    s = Sprint(
        id=sid,
        project_id=project_id,
        title="Sprint",
        status="active",
        created_at=_PAST,
        started_at=_PAST,
    )
    store.save_sprint(s)
    return s


def _task(
    store: ForemanStore,
    project_id: str,
    sprint_id: str,
    tid: str = "task-1",
    status: str = "done",
) -> Task:
    t = Task(
        id=tid,
        sprint_id=sprint_id,
        project_id=project_id,
        title="Task",
        status=status,  # type: ignore[arg-type]
        created_at=_PAST,
    )
    store.save_task(t)
    return t


def _run(
    store: ForemanStore,
    task: Task,
    rid: str,
    status: str = "completed",
    completed_at: str = _PAST,
    prompt_text: str | None = "the prompt",
) -> Run:
    r = Run(
        id=rid,
        task_id=task.id,
        project_id=task.project_id,
        role_id="developer",
        workflow_step="develop",
        agent_backend="claude",
        status=status,  # type: ignore[arg-type]
        cost_usd=0.05,
        token_count=100,
        duration_ms=5000,
        prompt_text=prompt_text,
        completed_at=completed_at,
        created_at=completed_at,
    )
    store.save_run(r)
    return r


def _event(store: ForemanStore, run: Run, eid: str, ts: str = _PAST) -> Event:
    e = Event(
        id=eid,
        run_id=run.id,
        task_id=run.task_id,
        project_id=run.project_id,
        event_type="agent.output",
        timestamp=ts,
    )
    store.save_event(e)
    return e


# ---------------------------------------------------------------------------
# prune_old_runs — basic deletion
# ---------------------------------------------------------------------------

class PruneOldRunsBasicTests(unittest.TestCase):

    def setUp(self) -> None:
        self.store = _make_store()
        p = _project(self.store)
        s = _sprint(self.store, p.id)
        self.task = _task(self.store, p.id, s.id)
        self.project_id = p.id

    def tearDown(self) -> None:
        self.store.close()

    def test_deletes_old_terminal_run(self) -> None:
        _run(self.store, self.task, "run-old", status="completed", completed_at=_PAST)
        n = self.store.prune_old_runs(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 1)
        self.assertIsNone(self.store.get_run("run-old"))

    def test_deletes_all_terminal_statuses(self) -> None:
        for i, status in enumerate(_TERMINAL_STATUSES):
            _run(self.store, self.task, f"run-{i}", status=status, completed_at=_PAST)
        n = self.store.prune_old_runs(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, len(_TERMINAL_STATUSES))

    def test_preserves_recent_runs(self) -> None:
        _run(self.store, self.task, "run-recent", status="completed", completed_at=_RECENT)
        n = self.store.prune_old_runs(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 0)
        self.assertIsNotNone(self.store.get_run("run-recent"))

    def test_preserves_active_status_runs(self) -> None:
        for i, status in enumerate(_ACTIVE_STATUSES):
            _run(self.store, self.task, f"run-active-{i}", status=status, completed_at=_PAST)
        n = self.store.prune_old_runs(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 0)

    def test_returns_zero_when_nothing_qualifies(self) -> None:
        n = self.store.prune_old_runs(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 0)

    def test_scoped_to_project(self) -> None:
        p2 = _project(self.store, "proj-2")
        s2 = _sprint(self.store, p2.id, "sprint-2")
        t2 = _task(self.store, p2.id, s2.id, "task-2")
        _run(self.store, self.task, "run-p1", status="completed", completed_at=_PAST)
        _run(self.store, t2, "run-p2", status="completed", completed_at=_PAST)
        n = self.store.prune_old_runs(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 1)
        self.assertIsNone(self.store.get_run("run-p1"))
        self.assertIsNotNone(self.store.get_run("run-p2"))


# ---------------------------------------------------------------------------
# prune_old_runs — active-work protection
# ---------------------------------------------------------------------------

class PruneOldRunsProtectionTests(unittest.TestCase):

    def setUp(self) -> None:
        self.store = _make_store()
        p = _project(self.store)
        s = _sprint(self.store, p.id)
        self.project_id = p.id
        self.sprint = s

    def tearDown(self) -> None:
        self.store.close()

    def test_preserves_runs_on_blocked_task(self) -> None:
        t = _task(self.store, self.project_id, self.sprint.id, "task-b", status="blocked")
        _run(self.store, t, "run-b", status="completed", completed_at=_PAST)
        n = self.store.prune_old_runs(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 0)
        self.assertIsNotNone(self.store.get_run("run-b"))

    def test_preserves_runs_on_in_progress_task(self) -> None:
        t = _task(self.store, self.project_id, self.sprint.id, "task-ip", status="in_progress")
        _run(self.store, t, "run-ip", status="completed", completed_at=_PAST)
        n = self.store.prune_old_runs(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 0)

    def test_prunes_runs_on_done_task(self) -> None:
        t = _task(self.store, self.project_id, self.sprint.id, "task-done", status="done")
        _run(self.store, t, "run-done", status="completed", completed_at=_PAST)
        n = self.store.prune_old_runs(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 1)


# ---------------------------------------------------------------------------
# prune_old_runs — cascade event deletion
# ---------------------------------------------------------------------------

class PruneOldRunsCascadeTests(unittest.TestCase):

    def setUp(self) -> None:
        self.store = _make_store()
        p = _project(self.store)
        s = _sprint(self.store, p.id)
        self.task = _task(self.store, p.id, s.id)
        self.project_id = p.id

    def tearDown(self) -> None:
        self.store.close()

    def test_cascade_deletes_events_for_pruned_run(self) -> None:
        run = _run(self.store, self.task, "run-old", completed_at=_PAST)
        _event(self.store, run, "evt-1", ts=_PAST)
        _event(self.store, run, "evt-2", ts=_PAST)
        self.store.prune_old_runs(project_id=self.project_id, older_than=_CUTOFF)
        self.assertIsNone(self.store.get_event("evt-1"))
        self.assertIsNone(self.store.get_event("evt-2"))

    def test_preserved_run_events_are_not_deleted(self) -> None:
        old_run = _run(self.store, self.task, "run-old", completed_at=_PAST)
        new_run = _run(self.store, self.task, "run-new", completed_at=_RECENT)
        _event(self.store, old_run, "evt-old", ts=_PAST)
        _event(self.store, new_run, "evt-new", ts=_RECENT)
        self.store.prune_old_runs(project_id=self.project_id, older_than=_CUTOFF)
        self.assertIsNone(self.store.get_event("evt-old"))
        self.assertIsNotNone(self.store.get_event("evt-new"))


# ---------------------------------------------------------------------------
# strip_old_run_prompts
# ---------------------------------------------------------------------------

class StripOldRunPromptsTests(unittest.TestCase):

    def setUp(self) -> None:
        self.store = _make_store()
        p = _project(self.store)
        s = _sprint(self.store, p.id)
        self.task = _task(self.store, p.id, s.id)
        self.project_id = p.id

    def tearDown(self) -> None:
        self.store.close()

    def test_nulls_prompt_on_old_terminal_run(self) -> None:
        _run(self.store, self.task, "run-old", completed_at=_PAST, prompt_text="big prompt")
        n = self.store.strip_old_run_prompts(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 1)
        run = self.store.get_run("run-old")
        assert run is not None
        self.assertIsNone(run.prompt_text)

    def test_preserves_run_record_and_telemetry(self) -> None:
        _run(self.store, self.task, "run-old", completed_at=_PAST, prompt_text="big prompt")
        self.store.strip_old_run_prompts(project_id=self.project_id, older_than=_CUTOFF)
        run = self.store.get_run("run-old")
        assert run is not None
        self.assertEqual(run.cost_usd, 0.05)
        self.assertEqual(run.token_count, 100)
        self.assertEqual(run.duration_ms, 5000)
        self.assertEqual(run.status, "completed")

    def test_preserves_recent_run_prompts(self) -> None:
        _run(self.store, self.task, "run-new", completed_at=_RECENT, prompt_text="new prompt")
        n = self.store.strip_old_run_prompts(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 0)
        run = self.store.get_run("run-new")
        assert run is not None
        self.assertEqual(run.prompt_text, "new prompt")

    def test_skips_already_null_prompts(self) -> None:
        _run(self.store, self.task, "run-null", completed_at=_PAST, prompt_text=None)
        n = self.store.strip_old_run_prompts(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 0)

    def test_strips_all_terminal_statuses(self) -> None:
        for i, status in enumerate(_TERMINAL_STATUSES):
            _run(
                self.store, self.task, f"run-{i}",
                status=status, completed_at=_PAST, prompt_text="text"
            )
        n = self.store.strip_old_run_prompts(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, len(_TERMINAL_STATUSES))

    def test_preserves_active_run_prompts(self) -> None:
        for i, status in enumerate(_ACTIVE_STATUSES):
            _run(
                self.store, self.task, f"run-active-{i}",
                status=status, completed_at=_PAST, prompt_text="text"
            )
        n = self.store.strip_old_run_prompts(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 0)

    def test_scoped_to_project(self) -> None:
        p2 = _project(self.store, "proj-2")
        s2 = _sprint(self.store, p2.id, "sprint-2")
        t2 = _task(self.store, p2.id, s2.id, "task-2")
        _run(self.store, self.task, "run-p1", completed_at=_PAST, prompt_text="text")
        _run(self.store, t2, "run-p2", completed_at=_PAST, prompt_text="text")
        n = self.store.strip_old_run_prompts(project_id=self.project_id, older_than=_CUTOFF)
        self.assertEqual(n, 1)
        run_p2 = self.store.get_run("run-p2")
        assert run_p2 is not None
        self.assertEqual(run_p2.prompt_text, "text")


# ---------------------------------------------------------------------------
# Migration 2 — index exists after fresh install
# ---------------------------------------------------------------------------

class Migration2IndexTests(unittest.TestCase):

    def test_idx_runs_project_completed_exists(self) -> None:
        with _make_store() as store:
            rows = store._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                ("idx_runs_project_completed",),
            ).fetchall()
            self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
