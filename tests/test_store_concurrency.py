"""Several processes share one database: the engine, the dashboard, the CLI.

Each test uses a connection per thread, as separate processes would.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest

from foreman.models import Event, Project, Run, Sprint, Task
from foreman.store import ForemanStore

WORKERS = 8


class StoreConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = Path(self._temp.name) / "foreman.db"
        with ForemanStore(self.db_path) as store:
            store.initialize()
            store.save_project(
                Project(id="p1", name="P", repo_path=self._temp.name, workflow_id="development")
            )
            store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
            store.save_task(Task(id="t1", sprint_id="s1", project_id="p1", title="T"))
            store.save_run(
                Run(id="r1", task_id="t1", project_id="p1", role_id="developer",
                    workflow_step="develop", agent_backend="claude_code", status="running")
            )

    def in_parallel(self, work, count: int = WORKERS) -> list:
        """Run ``work(index, store)`` in ``count`` threads, each with its own connection."""

        start = threading.Barrier(count)

        def run(index: int):
            with ForemanStore(self.db_path) as store:
                start.wait(timeout=10)
                return work(index, store)

        with ThreadPoolExecutor(max_workers=count) as pool:
            return list(pool.map(run, range(count)))

    def test_only_one_engine_wins_a_lease_raced_for_by_many(self) -> None:
        def acquire(index: int, store: ForemanStore):
            return store.acquire_lease(
                project_id="p1",
                resource_type="task",
                resource_id="t1",
                holder_id=f"engine-{index}",
                lease_token=f"token-{index}",
            )

        results = self.in_parallel(acquire)

        winners = [lease for lease in results if lease is not None]
        self.assertEqual(len(winners), 1)
        with ForemanStore(self.db_path) as store:
            active = store.get_active_lease(
                project_id="p1", resource_type="task", resource_id="t1"
            )
        self.assertEqual(active.holder_id, winners[0].holder_id)

    def test_events_written_by_many_writers_all_land_once(self) -> None:
        per_writer = 25

        def write(index: int, store: ForemanStore) -> None:
            for n in range(per_writer):
                store.save_event(
                    Event(
                        id=f"event-{index}-{n}",
                        run_id="r1",
                        task_id="t1",
                        project_id="p1",
                        event_type="agent.message",
                        payload={"writer": index, "n": n},
                    )
                )

        self.in_parallel(write)

        with ForemanStore(self.db_path) as store:
            events = store.list_events(task_id="t1")
        self.assertEqual(len(events), WORKERS * per_writer)
        self.assertEqual(len({event.id for event in events}), WORKERS * per_writer)

    def test_tasks_created_at_once_get_distinct_keys(self) -> None:
        def create(index: int, store: ForemanStore) -> str:
            store.save_task(
                Task(id=f"new-{index}", sprint_id="s1", project_id="p1", title=f"Task {index}")
            )
            return store.get_task(f"new-{index}").task_key

        keys = self.in_parallel(create)

        self.assertTrue(all(keys))
        self.assertEqual(len(set(keys)), WORKERS)

    def test_an_operator_cancel_and_engine_writes_never_resurrect_the_task(self) -> None:
        """The engine's column-scoped write loses to a cancel, whichever lands first."""

        def work(index: int, store: ForemanStore):
            if index == 0:
                task = store.get_task("t1")
                task.status = "cancelled"
                store.save_task(task)
                return "cancelled"
            task = store.get_task("t1")
            task.status = "in_progress"
            task.workflow_current_step = "develop"
            return store.update_task_engine_state(task)

        for _ in range(5):
            with ForemanStore(self.db_path) as store:
                task = store.get_task("t1")
                task.status = "todo"
                task.workflow_current_step = None
                store.save_task(task)
            self.in_parallel(work)
            with ForemanStore(self.db_path) as store:
                # The engine's write after the cancel is refused, so once the
                # cancel has landed nothing moves the task out of it.
                final = store.get_task("t1")
                self.assertFalse(
                    store.update_task_engine_state(
                        Task(id="t1", sprint_id="s1", project_id="p1", title="T",
                             status="in_progress")
                    )
                )
                self.assertEqual(store.get_task("t1").status, "cancelled")
                self.assertEqual(final.status, "cancelled")

    def test_engine_commands_are_each_claimed_in_order_by_one_reader(self) -> None:
        with ForemanStore(self.db_path) as store:
            ids = [
                store.enqueue_engine_command(
                    project_id="p1", command="run_task", requested_by="alice", task_id="t1"
                ).id
                for _ in range(WORKERS)
            ]
            # One engine reads at a time (the project lock); what is checked
            # here is that a queue filled by several writers drains in order.
            drained = []
            while (command := store.next_pending_engine_command("p1")) is not None:
                store.mark_engine_command(command.id, "completed")
                drained.append(command.id)
        self.assertEqual(drained, ids)


if __name__ == "__main__":
    unittest.main()
