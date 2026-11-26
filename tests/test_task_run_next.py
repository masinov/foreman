"""A pending "Run next" is told on the task and on the sprint's task list."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from foreman.domain.models import Project, Sprint, Task
from foreman.services.sprints import SprintService
from foreman.services.tasks import TaskService, decision_sentence
from foreman.store import ForemanStore


class RunNextTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = ForemanStore(str(Path(temp.name) / "foreman.db"))
        self.store.initialize()
        self.addCleanup(self.store.close)
        self.store.save_project(
            Project(id="p1", name="P", repo_path=temp.name, workflow_id="development")
        )
        self.store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        self.store.save_task(
            Task(id="t1", sprint_id="s1", project_id="p1", title="One", status="todo")
        )
        self.tasks = TaskService(self.store)
        self.sprints = SprintService(self.store)

    def _flags(self) -> tuple[bool, bool]:
        listed = self.sprints.list_sprint_tasks("s1")["tasks"][0]["run_next"]
        return self.tasks.get_task("t1")["run_next"], listed

    def test_run_next_is_true_while_the_request_waits_and_false_after(self) -> None:
        self.assertEqual(self._flags(), (False, False))
        command = self.store.enqueue_engine_command(
            project_id="p1", command="run_task", task_id="t1", requested_by="ana"
        )
        self.assertEqual(self._flags(), (True, True))
        self.store.mark_engine_command(command.id, "acknowledged", detail="will run next")
        self.assertEqual(self._flags(), (True, True))
        self.store.mark_engine_command(command.id, "completed", detail="started")
        self.assertEqual(self._flags(), (False, False))

    def test_a_rejected_request_is_not_pending(self) -> None:
        command = self.store.enqueue_engine_command(
            project_id="p1", command="run_task", task_id="t1", requested_by="ana"
        )
        self.store.mark_engine_command(command.id, "rejected", detail="no")
        self.assertEqual(self._flags(), (False, False))


class DecisionSentenceTests(unittest.TestCase):
    def test_the_sentences(self) -> None:
        task = Task(id="t", sprint_id="s", project_id="p", title="Do it", task_key="FOR-51")
        say = lambda **kw: decision_sentence(task, **kw)  # noqa: E731
        self.assertEqual(
            say(sent_back=False, next_step="merge", engine_resident=True),
            "Approved FOR-51. Foreman goes on with Merge.",
        )
        self.assertEqual(
            say(sent_back=False, next_step="merge", engine_resident=False),
            "Approved FOR-51. It waits at Merge until a worker runs.",
        )
        self.assertEqual(
            say(sent_back=True, next_step="develop", engine_resident=True),
            "Sent FOR-51 back to Develop.",
        )
        task.task_key = None
        self.assertEqual(
            say(sent_back=True, next_step="code_review", engine_resident=True),
            "Sent Do it back to Code review.",
        )


if __name__ == "__main__":
    unittest.main()
