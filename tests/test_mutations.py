"""The one implementation of operator changes to tasks and sprints."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from foreman.models import Project, Run, Sprint, Task
from foreman.mutations import MutationError, Mutations
from foreman.store import ENGINE_RESOURCE_TYPE, ForemanStore


class MutationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.store = ForemanStore(Path(self._temp.name) / "foreman.db")
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(
            Project(id="p1", name="P", repo_path=self._temp.name, workflow_id="development")
        )
        self.store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        self.mutations = Mutations(self.store, via="cli", actor="alice")

    def task(self, task_id: str = "t1", **fields: object) -> Task:
        task = Task(id=task_id, sprint_id="s1", project_id="p1", title="T", **fields)  # type: ignore[arg-type]
        self.store.save_task(task)
        return self.store.get_task(task_id)

    def events(self, task_id: str, event_type: str):
        return [e for e in self.store.list_events(task_id=task_id) if e.event_type == event_type]

    def running_under_an_engine(self, task: Task) -> None:
        self.store.save_run(
            Run(
                id="run-live",
                task_id=task.id,
                project_id="p1",
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
            )
        )
        self.store.acquire_lease(
            project_id="p1",
            resource_type=ENGINE_RESOURCE_TYPE,
            resource_id="p1",
            holder_id="engine-a",
            lease_token="tok",
        )

    # ── every change leaves a trace naming who and from where ────────────

    def test_each_task_change_records_an_audit_event(self) -> None:
        task = self.task(status="triage")
        self.mutations.accept_task(task)
        self.mutations.block_task(task, "waiting on design")
        self.mutations.unblock_task(task)
        self.mutations.cancel_task(task)

        for event_type, from_status in (
            ("human.task_accepted", "triage"),
            ("human.task_blocked", "todo"),
            ("human.task_unblocked", "blocked"),
            ("human.task_cancelled", "todo"),
        ):
            with self.subTest(event_type=event_type):
                recorded = self.events("t1", event_type)
                self.assertEqual(len(recorded), 1)
                self.assertEqual(recorded[0].payload["via"], "cli")
                self.assertEqual(recorded[0].payload["by"], "alice")
                self.assertEqual(recorded[0].payload["from_status"], from_status)
        self.assertEqual(
            self.events("t1", "human.task_blocked")[0].payload["reason"], "waiting on design"
        )
        self.assertEqual(self.store.get_task("t1").status, "cancelled")

    # ── rules ────────────────────────────────────────────────────────────

    def test_only_a_triage_task_can_be_accepted(self) -> None:
        with self.assertRaises(MutationError):
            self.mutations.accept_task(self.task(status="todo"))

    def test_a_resolved_task_cannot_be_blocked(self) -> None:
        for status in ("done", "cancelled"):
            with self.subTest(status=status), self.assertRaises(MutationError):
                self.mutations.block_task(self.task(f"t-{status}", status=status), "why")

    def test_a_task_waiting_at_a_gate_is_not_unblocked_but_decided(self) -> None:
        task = self.task(status="blocked", workflow_current_step="merge_approval")

        with self.assertRaises(MutationError) as caught:
            self.mutations.unblock_task(task)

        self.assertIn("foreman approve", str(caught.exception))
        self.assertEqual(self.store.get_task("t1").status, "blocked")

    def test_unblocking_starts_the_workflow_over(self) -> None:
        task = self.task(status="blocked", blocked_reason="stuck", step_visit_counts={"develop": 5})

        self.mutations.unblock_task(task)

        stored = self.store.get_task("t1")
        self.assertEqual(stored.status, "todo")
        self.assertIsNone(stored.blocked_reason)
        self.assertEqual(stored.step_visit_counts, {})

    def test_cancelling_twice_changes_nothing_and_a_done_task_is_refused(self) -> None:
        task = self.task()
        self.assertTrue(self.mutations.cancel_task(task).changed)
        self.assertFalse(self.mutations.cancel_task(self.store.get_task("t1")).changed)
        self.assertEqual(len(self.events("t1", "human.task_cancelled")), 1)

        with self.assertRaises(MutationError):
            self.mutations.cancel_task(self.task("t2", status="done"))

    # ── what a running engine owns ───────────────────────────────────────

    def test_a_task_an_engine_is_running_cannot_be_cancelled_or_deleted(self) -> None:
        task = self.task(status="in_progress")
        self.running_under_an_engine(task)

        for change in (self.mutations.cancel_task, self.mutations.delete_task):
            with self.subTest(change=change.__name__):
                with self.assertRaises(MutationError) as caught:
                    change(task)
                self.assertIn("stop-task", str(caught.exception))
        self.assertEqual(self.store.get_task("t1").status, "in_progress")

    def test_a_sprint_with_a_running_task_cannot_be_deleted(self) -> None:
        self.running_under_an_engine(self.task(status="in_progress"))

        with self.assertRaises(MutationError):
            self.mutations.delete_sprint(self.store.get_sprint("s1"))

        self.assertIsNotNone(self.store.get_sprint("s1"))

    def test_a_stale_running_run_without_an_engine_does_not_block_the_change(self) -> None:
        task = self.task(status="in_progress")
        self.store.save_run(
            Run(
                id="run-left-behind",
                task_id=task.id,
                project_id="p1",
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude_code",
                status="running",
            )
        )

        self.assertTrue(self.mutations.cancel_task(task).changed)

    # ── sprints ──────────────────────────────────────────────────────────

    def test_sprint_lifecycle_follows_one_table(self) -> None:
        self.store.save_sprint(Sprint(id="s2", project_id="p1", title="Next", status="planned"))
        planned = self.store.get_sprint("s2")

        with self.assertRaises(MutationError) as caught:
            self.mutations.transition_sprint(planned, "active")
        self.assertIn("already active", str(caught.exception))
        with self.assertRaises(MutationError):
            self.mutations.transition_sprint(planned, "completed")

        active = self.store.get_sprint("s1")
        self.assertIs(self.mutations.transition_sprint(active, "active"), active)
        self.mutations.transition_sprint(active, "completed")
        self.assertEqual(self.store.get_sprint("s1").status, "completed")
        self.assertIsNotNone(self.store.get_sprint("s1").completed_at)

        self.mutations.transition_sprint(planned, "active")
        self.assertIsNotNone(self.store.get_sprint("s2").started_at)
        with self.assertRaises(MutationError):
            self.mutations.transition_sprint(self.store.get_sprint("s1"), "active")

    def test_a_sprint_with_unresolved_tasks_cannot_be_completed(self) -> None:
        self.task("open", status="todo")
        self.task("finished", status="done")

        with self.assertRaises(MutationError) as caught:
            self.mutations.transition_sprint(self.store.get_sprint("s1"), "completed")

        self.assertIn("unresolved tasks remain", str(caught.exception))
        self.assertEqual(self.store.get_sprint("s1").status, "active")
        # Cancelling the sprint is the way to abandon what is left.
        self.mutations.transition_sprint(self.store.get_sprint("s1"), "cancelled")
        self.assertEqual(self.store.get_sprint("s1").status, "cancelled")


if __name__ == "__main__":
    unittest.main()
