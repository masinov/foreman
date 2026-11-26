"""A record belongs to a run, a sprint or the project (ADR-0037)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from foreman.domain.models import Project, Run, Sprint, Task, sprint_ready_to_finish
from foreman.engine.sprints import SprintFlow
from foreman.history.records import RunRecords
from foreman.notifications.delivery import NotificationDispatcher
from foreman.services.sprints import SprintService
from foreman.store import ForemanStore
from foreman.store.base import _SCHEMA_MIGRATIONS_DDL
from foreman.store.migrations import MIGRATIONS


def now() -> datetime:
    return datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)


class RecordsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db_path = Path(temp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.store.initialize()
        self.addCleanup(self.store.close)
        self.store.save_project(
            Project(id="p", name="P", repo_path=temp.name, workflow_id="development")
        )
        self.records = RunRecords(self.store, NotificationDispatcher(self.store))

    def sprint(self, sprint_id: str = "s", *, status: str = "active", order_index: int = 0) -> Sprint:
        sprint = Sprint(id=sprint_id, project_id="p", title=f"Sprint {sprint_id}", status=status, order_index=order_index)  # type: ignore[arg-type]
        self.store.save_sprint(sprint)
        return sprint

    def task(self, task_id: str, sprint_id: str, status: str = "done") -> Task:
        task = Task(id=task_id, sprint_id=sprint_id, project_id="p", title=task_id, status=status)  # type: ignore[arg-type]
        self.store.save_task(task)
        return task


class SprintRecordsTests(RecordsTestCase):
    def test_a_sprint_ready_to_finish_is_the_sprints_own_record(self) -> None:
        sprint = self.sprint()
        self.task("t1", "s")
        flow = SprintFlow(self.store, self.records, now)
        self.assertEqual(flow.resolve(self.store.get_project("p"), sprint), "sprint_resolved")
        events = self.store.list_sprint_events("s")
        self.assertEqual(
            [e.event_type for e in events], ["engine.sprint_ready", "engine.attention_needed"]
        )
        for event in events:
            self.assertEqual((event.sprint_id, event.run_id, event.task_id), ("s", None, None))
        self.assertEqual(events[1].payload["trigger"], "sprint_resolved")
        self.assertEqual(events[1].payload["sprint_id"], "s")
        # No run was made up on the task for it.
        self.assertEqual(self.store.list_runs(task_id="t1"), [])

    def test_a_sprints_records_stay_with_it_when_its_first_task_moves(self) -> None:
        sprint = self.sprint()
        self.sprint("other", status="planned", order_index=1)
        first = self.task("t1", "s")
        self.task("t2", "s")
        self.records.emit_sprint_event(
            sprint, "engine.sprint_completed", {"sprint_id": "s", "sprint_title": sprint.title}
        )
        first.sprint_id = "other"
        self.store.save_task(first)
        self.assertEqual(
            [e.event_type for e in self.store.list_sprint_events("s")], ["engine.sprint_completed"]
        )
        self.assertEqual(self.store.list_sprint_events("other"), [])

    def test_a_sprint_with_no_task_keeps_its_records(self) -> None:
        sprint = self.sprint()
        self.records.emit_sprint_event(sprint, "engine.sprint_started", {"sprint_id": "s"})
        self.assertEqual(len(self.store.list_sprint_events("s")), 1)

    def test_its_tasks_events_and_its_own_come_in_one_order_with_cursors(self) -> None:
        sprint = self.sprint()
        task = self.task("t1", "s", status="in_progress")
        run = self.records.create_running_run(task, role_id="developer", workflow_step="develop", agent_backend="claude")
        first = self.records.emit_event(run, "agent.started", {}, timestamp="2026-11-24T10:00:00+00:00")
        own = self.records.emit_sprint_event(sprint, "engine.sprint_ready", {"sprint_id": "s"})
        own_event = self.store.get_event(own.id)
        assert own_event is not None
        later = self.records.emit_event(run, "agent.message", {"text": "x"}, timestamp="2999-01-01T00:00:00+00:00")
        ids = [e.id for e in self.store.list_sprint_events("s")]
        self.assertEqual(ids, [first.id, own.id, later.id])
        self.assertEqual([e.id for e in self.store.list_sprint_events("s", after_event_id=first.id)], [own.id, later.id])
        self.assertEqual([e.id for e in self.store.list_sprint_events("s", before_event_id=later.id, limit=1)], [own.id])
        self.assertEqual([e.id for e in self.store.list_recent_sprint_events("s", limit=2)], [own.id, later.id])
        self.assertEqual(
            [e.id for e in self.store.list_sprint_events("s", event_types=["engine.sprint_ready"])], [own.id]
        )

    def test_pruning_keeps_a_sprints_records_and_deleting_the_sprint_removes_them(self) -> None:
        sprint = self.sprint()
        self.records.emit_sprint_event(sprint, "engine.checkpoint", {"sprint_id": "s"})
        self.records.emit_project_event("p", "engine.command_applied", {"command": "pause", "task_id": None})
        removed = self.store.prune_old_events(project_id="p", older_than="2999-01-01T00:00:00+00:00")
        self.assertEqual(removed, 1)
        self.assertEqual([e.event_type for e in self.store.list_sprint_events("s")], ["engine.checkpoint"])
        self.store.delete_sprint("s")
        self.assertEqual(self.store.list_events(project_id="p"), [])

    def test_a_record_with_a_run_has_no_sprint_and_a_run_has_a_task(self) -> None:
        sprint = self.sprint()
        task = self.task("t1", "s")
        run = self.records.create_system_run(task, workflow_step="develop", outcome="success", detail="x")
        connection = self.store._connection
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO events (id, run_id, task_id, sprint_id, project_id, event_type, timestamp)"
                " VALUES ('e1', ?, 't1', ?, 'p', 'x', 'now')",
                (run.id, sprint.id),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO events (id, run_id, task_id, project_id, event_type, timestamp)"
                " VALUES ('e2', NULL, 't1', 'p', 'x', 'now')"
            )
        connection.rollback()


class SprintPageTests(RecordsTestCase):
    def test_the_sprint_says_it_is_ready_to_finish_when_every_task_is_finished(self) -> None:
        self.sprint()
        self.task("t1", "s", status="done")
        blocked = self.task("t2", "s", status="blocked")
        service = SprintService(self.store)
        self.assertFalse(service.get_sprint("s")["ready_to_finish"])
        blocked.status = "cancelled"
        self.store.save_task(blocked)
        self.assertTrue(service.get_sprint("s")["ready_to_finish"])
        # An empty sprint and a sprint not active are not.
        self.assertFalse(sprint_ready_to_finish("active", {"done": 0, "todo": 0}))
        self.sprint("later", status="planned", order_index=1)
        self.task("t3", "later", status="done")
        self.assertFalse(service.get_sprint("later")["ready_to_finish"])

    def test_the_projects_finished_row_carries_the_tag_of_that_completion(self) -> None:
        sprint = self.sprint(status="completed")
        sprint.completed_at = "2026-11-24T10:00:00+00:00"
        self.store.save_sprint(sprint)
        # An earlier completion's tag (the sprint was reopened) is not this one's.
        self.records.emit_sprint_event(sprint, "engine.checkpoint", {
            "sprint_id": "s", "completed_at": "2026-11-20T10:00:00+00:00", "tag": "old", "sha": "1" * 40,
        })
        self.records.emit_sprint_event(sprint, "engine.checkpoint", {
            "sprint_id": "s", "completed_at": sprint.completed_at, "tag": "checkpoint-20261124-sprint-s", "sha": "6f79f4a" + "0" * 33,
        })
        rows, _ = self.store.page_milestones(project_id="p", kinds=["sprint_finished"])
        self.assertEqual(
            rows[0].checkpoint,
            {"tag": "checkpoint-20261124-sprint-s", "sha": "6f79f4a" + "0" * 33, "problem": None},
        )

    def test_a_finished_sprint_that_could_not_be_tagged_says_why(self) -> None:
        sprint = self.sprint(status="completed")
        sprint.completed_at = "2026-11-24T10:00:00+00:00"
        self.store.save_sprint(sprint)
        self.records.emit_sprint_event(sprint, "engine.checkpoint_failed", {
            "sprint_id": "s", "completed_at": sprint.completed_at, "reason": "no commits",
        })
        rows, _ = self.store.page_milestones(project_id="p", kinds=["sprint_finished"])
        self.assertEqual(rows[0].checkpoint, {"tag": None, "sha": None, "problem": "no commits"})


class ProjectRecordsTests(RecordsTestCase):
    def test_a_command_naming_no_task_is_the_projects_even_with_no_task(self) -> None:
        event = self.records.emit_project_event(
            "p", "engine.command_applied", {"command": "shutdown", "task_id": None}
        )
        kept = self.store.get_event(event.id)
        assert kept is not None
        self.assertEqual((kept.run_id, kept.task_id, kept.sprint_id), (None, None, None))
        self.assertEqual([e.id for e in self.store.list_events(project_id="p")], [event.id])


class MovingOldRecordsTests(unittest.TestCase):
    """Migration 29 moves what was pinned to a task through a made-up run."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db_path = Path(temp.name) / "foreman.db"
        store = ForemanStore(db_path)
        store._connection.executescript(_SCHEMA_MIGRATIONS_DDL)
        store.migrate([m for m in MIGRATIONS if m[0] <= 28])
        store.save_project(Project(id="p", name="P", repo_path=temp.name, workflow_id="development"))
        store.save_sprint(Sprint(id="s", project_id="p", title="S", status="active"))
        store.save_sprint(Sprint(id="s2", project_id="p", title="S2", status="planned", order_index=1))
        for task in (
            Task(id="t1", sprint_id="s", project_id="p", title="T1", status="done"),
            Task(id="t2", sprint_id="s2", project_id="p", title="T2", status="in_progress"),
        ):
            # Raw, as the runs below: the store writes the current tasks
            # columns, and this database is at migration 28.
            store._connection.execute(
                "INSERT INTO tasks (id, sprint_id, project_id, title, task_key, status,"
                " task_type, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (task.id, task.sprint_id, task.project_id, task.title, task.id,
                 task.status, task.task_type, task.created_by, task.created_at),
            )

        def save_run(run: Run) -> None:
            # Raw: the store writes the current runs columns, and this database
            # is at migration 28, before migration 29 moves these records.
            store._connection.execute(
                "INSERT INTO runs (id, task_id, project_id, role_id, workflow_step,"
                " agent_backend, status, outcome, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run.id, run.task_id, run.project_id, run.role_id, run.workflow_step,
                 run.agent_backend, run.status, run.outcome, run.created_at),
            )

        def made_up(run_id: str, task_id: str, step: str = "orchestrator") -> None:
            save_run(Run(
                id=run_id, task_id=task_id, project_id="p", role_id="_builtin:orchestrator",
                workflow_step=step, agent_backend="orchestrator", status="completed",
                outcome="success", created_at="2026-11-01T00:00:00+00:00",
            ))

        def event(event_id: str, run_id: str, task_id: str, event_type: str, payload: dict) -> None:
            store._connection.execute(
                "INSERT INTO events (id, run_id, task_id, project_id, event_type, role_id, timestamp, payload_json)"
                " VALUES (?, ?, ?, 'p', ?, '_builtin:orchestrator', '2026-11-01T00:00:00+00:00', ?)",
                (event_id, run_id, task_id, event_type, json.dumps(payload)),
            )

        # The sprint's records, pinned to its first task, and one of another
        # sprint pinned to a task of this one.
        made_up("r-ready", "t1")
        event("e-ready", "r-ready", "t1", "engine.sprint_ready", {"sprint_id": "s"})
        made_up("r-turn", "t1")
        event("e-turn", "r-turn", "t1", "engine.attention_needed", {"trigger": "sprint_resolved", "task_id": None})
        made_up("r-check", "t1")
        event("e-check", "r-check", "t1", "engine.checkpoint", {"sprint_id": "s2"})
        event("e-push", "r-check", "t1", "engine.push", {"ref": "tag"})
        # A command naming no task, pinned at the step of the task at hand,
        # beside one naming its task.
        made_up("r-cmd", "t2", step="develop")
        event("e-cmd", "r-cmd", "t2", "engine.command_applied", {"command": "shutdown", "task_id": None})
        made_up("r-own", "t2", step="develop")
        event("e-own", "r-own", "t2", "engine.command_applied", {"command": "stop_task", "task_id": "t2"})
        # A real run's event that happens to share a type stays.
        save_run(Run(
            id="r-merge", task_id="t1", project_id="p", role_id="_builtin:merge",
            workflow_step="merge", agent_backend="builtin", status="completed",
            outcome="success", created_at="2026-11-01T00:00:00+00:00",
        ))
        event("e-merge-push", "r-merge", "t1", "engine.push", {"ref": "main"})
        store._connection.commit()
        store.close()
        self.store = ForemanStore(db_path)
        self.addCleanup(self.store.close)
        self.assertEqual(self.store.initialize()[0], 29)

    def owner(self, event_id: str) -> tuple[str | None, str | None, str | None]:
        event = self.store.get_event(event_id)
        assert event is not None
        return (event.run_id, event.task_id, event.sprint_id)

    def test_sprint_records_go_to_their_sprint(self) -> None:
        self.assertEqual(self.owner("e-ready"), (None, None, "s"))
        # A sprint_resolved turn names no sprint: the sprint of its task, now named.
        self.assertEqual(self.owner("e-turn"), (None, None, "s"))
        turn = self.store.get_event("e-turn")
        assert turn is not None
        self.assertEqual(turn.payload["sprint_id"], "s")
        # A checkpoint and its push go to the checkpoint's sprint.
        self.assertEqual(self.owner("e-check"), (None, None, "s2"))
        self.assertEqual(self.owner("e-push"), (None, None, "s2"))

    def test_project_records_lose_their_run_and_task(self) -> None:
        self.assertEqual(self.owner("e-cmd"), (None, None, None))
        self.assertEqual(self.owner("e-own"), ("r-own", "t2", None))
        self.assertEqual(self.owner("e-merge-push"), ("r-merge", "t1", None))

    def test_made_up_runs_left_empty_are_deleted(self) -> None:
        runs = {run.id for run in self.store.list_runs(project_id="p")}
        self.assertEqual(runs, {"r-own", "r-merge"})


if __name__ == "__main__":
    unittest.main()
