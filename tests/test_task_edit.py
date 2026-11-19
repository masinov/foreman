"""Changing a task's size, priority and what it waits for, after it is filed."""

from __future__ import annotations

import asyncio
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import httpx

from foreman.cli import main
from foreman.api.app import create_dashboard_app
from foreman.domain.models import Project, Sprint, Task
from foreman.mutations import MutationError, Mutations
from foreman.store import ForemanStore


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = Path(self._temp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(
            Project(id="p1", name="P", repo_path=self._temp.name, workflow_id="development")
        )
        self.store.save_project(
            Project(id="p2", name="Other", repo_path=self._temp.name, workflow_id="development")
        )
        self.store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        self.store.save_sprint(Sprint(id="s2", project_id="p2", title="S", status="active"))

    def task(self, task_id: str, *, sprint: str = "s1", project: str = "p1", **fields: object) -> Task:
        task = Task(id=task_id, sprint_id=sprint, project_id=project, title=task_id, **fields)  # type: ignore[arg-type]
        self.store.save_task(task)
        return task

    def stored(self, task_id: str) -> Task:
        task = self.store.get_task(task_id)
        assert task is not None
        return task


class EditMutationTests(_Workspace):
    def setUp(self) -> None:
        super().setUp()
        self.mutations = Mutations(self.store, via="cli", actor="alice")

    def test_size_can_be_set_changed_and_cleared(self) -> None:
        task = self.task("t1")

        self.assertEqual(self.mutations.edit_task(task, {"complexity": "large"}), {"complexity": "large"})
        self.assertEqual(self.stored("t1").complexity, "large")
        self.assertEqual(self.mutations.edit_task(task, {"complexity": None}), {"complexity": None})
        self.assertIsNone(self.stored("t1").complexity)
        with self.assertRaises(MutationError):
            self.mutations.edit_task(task, {"complexity": "huge"})

    def test_what_a_task_waits_for_can_be_replaced_and_cleared(self) -> None:
        self.task("a")
        self.task("b")
        task = self.task("t1", depends_on_task_ids=["a"])

        changed = self.mutations.edit_task(task, {"depends_on_task_ids": ["b", "a", "b"]})

        self.assertEqual(changed, {"depends_on_task_ids": ["b", "a"]})
        self.assertEqual(self.stored("t1").depends_on_task_ids, ["b", "a"])
        self.mutations.edit_task(task, {"depends_on_task_ids": []})
        self.assertEqual(self.stored("t1").depends_on_task_ids, [])

    def test_a_task_cannot_wait_for_itself_a_stranger_or_one_that_waits_for_it(self) -> None:
        self.task("far", sprint="s2", project="p2")
        self.task("c", depends_on_task_ids=["t1"])
        self.task("d", depends_on_task_ids=["c"])
        task = self.task("t1")

        for bad, words in (
            (["t1"], "cannot wait for itself"),
            (["nope"], "not found in this project"),
            (["far"], "not found in this project"),
            (["c"], "already waits for"),
            # Through another task: d waits for c, which waits for t1.
            (["d"], "already waits for"),
            ("a", "must be a list"),
        ):
            with self.assertRaises(MutationError) as caught:
                self.mutations.edit_task(task, {"depends_on_task_ids": bad})
            self.assertIn(words, str(caught.exception))
        self.assertEqual(self.stored("t1").depends_on_task_ids, [])

    def test_what_a_started_task_waits_for_cannot_change_but_the_rest_can(self) -> None:
        self.task("a")
        task = self.task("t1", status="in_progress", workflow_current_step="develop")

        with self.assertRaises(MutationError) as caught:
            self.mutations.edit_task(task, {"depends_on_task_ids": ["a"]})
        self.assertIn("only change before it starts", str(caught.exception))

        # Sending back what it already waits for is not a change.
        self.assertEqual(self.mutations.edit_task(task, {"depends_on_task_ids": [], "complexity": "small"}), {"complexity": "small"})
        events = [e for e in self.store.list_events(task_id="t1") if e.event_type == "human.task_edited"]
        self.assertEqual(events[-1].payload["changed_fields"], {"complexity": "small"})


class EditApiTests(_Workspace):
    def patch(self, task_id: str, body: dict) -> httpx.Response:
        async def send() -> httpx.Response:
            app = create_dashboard_app(str(self.db_path))
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.patch(f"/api/v1/tasks/{task_id}", json=body)

        return asyncio.run(send())

    def test_the_task_page_can_change_size_priority_and_what_it_waits_for(self) -> None:
        self.task("a")
        self.task("t1")

        response = self.patch("t1", {"complexity": "medium", "priority": 3, "depends_on_task_ids": ["a"]})

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["complexity"], body["priority"], body["depends_on_task_ids"]), ("medium", 3, ["a"]))

    def test_a_loop_is_refused_with_the_reason(self) -> None:
        self.task("a", depends_on_task_ids=["t1"])
        self.task("t1")

        response = self.patch("t1", {"depends_on_task_ids": ["a"]})

        self.assertEqual(response.status_code, 400)
        self.assertIn("already waits for", response.text)


class EditCommandTests(_Workspace):
    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([*argv, "--db", str(self.db_path)])
        return code, out.getvalue(), err.getvalue()

    def test_foreman_task_edit_changes_what_it_is_asked_to(self) -> None:
        self.task("a")
        self.task("b")
        self.task("t1")

        code, out, err = self.run_cli(
            "task", "edit", "t1", "--size", "large", "--priority", "2",
            "--depends-on", "a", "--depends-on", "b",
        )

        self.assertEqual(code, 0, err)
        self.assertIn("Size: large | Priority: 2", out)
        self.assertIn("Waits for: a, b", out)
        stored = ForemanStore(self.db_path)
        self.addCleanup(stored.close)
        task = stored.get_task("t1")
        self.assertEqual((task.complexity, task.priority, task.depends_on_task_ids), ("large", 2, ["a", "b"]))

        code, out, _ = self.run_cli("task", "edit", "t1", "--size", "none", "--no-dependencies")
        self.assertEqual(code, 0)
        self.assertIn("Size: not said", out)
        self.assertIn("Waits for: nothing", out)

    def test_it_says_when_there_is_nothing_to_change_or_the_change_is_refused(self) -> None:
        self.task("t1")

        code, _, err = self.run_cli("task", "edit", "t1")
        self.assertEqual(code, 1)
        self.assertIn("Nothing to change", err)

        code, _, err = self.run_cli("task", "edit", "t1", "--depends-on", "t1")
        self.assertEqual(code, 1)
        self.assertIn("cannot wait for itself", err)

        code, _, err = self.run_cli("task", "edit", "t1", "--depends-on", "a", "--no-dependencies")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
