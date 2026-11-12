"""Choosing the next task in autonomous mode."""

from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from foreman.models import Project, Sprint, Task
from foreman.engine.errors import OrchestratorError
from foreman.orchestrator import ForemanOrchestrator
from foreman.store import ForemanStore

from engine_support import (
    RepoTestCase,
)


class AutonomousTaskSelectionTests(RepoTestCase):
    """Tests for select_next_task in autonomous mode."""

    def _make_store(self) -> tuple[ForemanStore, str]:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        db_path = str(Path(self._tmp.name) / "foreman.db")
        store = ForemanStore(db_path)
        store.initialize()
        return store, db_path

    def _seed(
        self,
        store: ForemanStore,
        *,
        selection_mode: str = "autonomous",
        max_autonomous_tasks: int | None = None,
    ) -> tuple[Project, "Sprint"]:
        settings: dict = {"task_selection_mode": selection_mode}
        if max_autonomous_tasks is not None:
            settings["max_autonomous_tasks"] = max_autonomous_tasks
        project = Project(
            id="proj-auto",
            name="Auto Project",
            repo_path="/tmp/auto",
            workflow_id="development",
            settings=settings,
        )
        sprint = Sprint(
            id="sprint-auto",
            project_id=project.id,
            title="Auto Sprint",
            status="active",
        )
        store.save_project(project)
        store.save_sprint(sprint)
        return project, sprint

    def _orchestrator(self, store: ForemanStore) -> ForemanOrchestrator:
        return ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)

    def test_autonomous_no_sprint_returns_none(self) -> None:
        store, _ = self._make_store()
        project = Project(
            id="proj-nosprint",
            name="No Sprint",
            repo_path="/tmp/nosprint",
            workflow_id="development",
            settings={"task_selection_mode": "autonomous"},
        )
        store.save_project(project)
        orc = self._orchestrator(store)
        result = orc.select_next_task(project)
        self.assertIsNone(result)

    def test_autonomous_creates_placeholder_task(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store)
        orc = self._orchestrator(store)

        selected = orc.select_next_task(project)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.sprint_id, sprint.id)
        self.assertEqual(selected.project_id, project.id)
        self.assertEqual(selected.created_by, "orchestrator")
        self.assertEqual(selected.title, "[autonomous] new task")
        # Task should be persisted.
        persisted = store.get_task(selected.id)
        self.assertIsNotNone(persisted)

    def test_autonomous_resumes_inprogress_before_creating(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store)
        existing = Task(
            id="task-existing",
            sprint_id=sprint.id,
            project_id=project.id,
            title="In-flight task",
            status="in_progress",
            workflow_current_step="develop",
            created_by="orchestrator",
        )
        store.save_task(existing)
        orc = self._orchestrator(store)

        selected = orc.select_next_task(project)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.id, existing.id)
        # No new placeholder should have been created.
        all_tasks = store.list_tasks(sprint_id=sprint.id)
        self.assertEqual(len(all_tasks), 1)

    def test_autonomous_waits_for_live_in_progress_task_before_creating_placeholder(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store)
        existing = Task(
            id="task-existing",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Live native task",
            status="in_progress",
            created_by="orchestrator",
        )
        store.save_task(existing)
        orc = self._orchestrator(store)

        selected = orc.select_next_task(project)

        self.assertIsNone(selected)
        all_tasks = store.list_tasks(sprint_id=sprint.id)
        self.assertEqual(len(all_tasks), 1)

    def test_autonomous_respects_max_autonomous_tasks_limit(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store, max_autonomous_tasks=2)
        for i in range(2):
            store.save_task(Task(
                id=f"task-orc-{i}",
                sprint_id=sprint.id,
                project_id=project.id,
                title=f"Orchestrator task {i}",
                status="done",
                created_by="orchestrator",
            ))
        orc = self._orchestrator(store)

        result = orc.select_next_task(project)

        self.assertIsNone(result)

    def test_autonomous_default_limit_is_five(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store)  # no max_autonomous_tasks override
        for i in range(5):
            store.save_task(Task(
                id=f"task-orc-{i}",
                sprint_id=sprint.id,
                project_id=project.id,
                title=f"Orchestrator task {i}",
                status="done",
                created_by="orchestrator",
            ))
        orc = self._orchestrator(store)

        result = orc.select_next_task(project)

        self.assertIsNone(result)

    def test_autonomous_human_created_tasks_dont_count_toward_limit(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store, max_autonomous_tasks=1)
        # Five human-created tasks — should not count against the autonomous limit.
        for i in range(5):
            store.save_task(Task(
                id=f"task-human-{i}",
                sprint_id=sprint.id,
                project_id=project.id,
                title=f"Human task {i}",
                status="todo",
                created_by="human",
            ))
        orc = self._orchestrator(store)

        selected = orc.select_next_task(project)

        # One placeholder should be created because no orchestrator task exists yet.
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.created_by, "orchestrator")

    def test_directed_mode_unchanged(self) -> None:
        store, _ = self._make_store()
        project = Project(
            id="proj-directed",
            name="Directed",
            repo_path="/tmp/directed",
            workflow_id="development",
            settings={"task_selection_mode": "directed"},
        )
        sprint = Sprint(
            id="sprint-directed",
            project_id=project.id,
            title="Sprint",
            status="active",
        )
        task = Task(
            id="task-d",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Directed task",
            status="todo",
        )
        store.save_project(project)
        store.save_sprint(sprint)
        store.save_task(task)
        orc = self._orchestrator(store)

        selected = orc.select_next_task(project)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.id, task.id)

    def test_unknown_selection_mode_raises(self) -> None:
        store, _ = self._make_store()
        project = Project(
            id="proj-unknown",
            name="Unknown Mode",
            repo_path="/tmp/unknown",
            workflow_id="development",
            settings={"task_selection_mode": "galactic"},
        )
        store.save_project(project)
        orc = self._orchestrator(store)

        with self.assertRaises(OrchestratorError):
            orc.select_next_task(project)


class BacklogIsNeverRunTests(RepoTestCase):
    """The engine runs the active sprint only; the backlog is not one (ADR-0021)."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = ForemanStore(Path(temp.name) / "foreman.db")
        self.addCleanup(self.store.close)
        self.store.initialize()

    def _project(self, *, mode: str = "directed", autonomy: str = "supervised") -> Project:
        project = Project(
            id="p", name="P", repo_path="/tmp/p", workflow_id="development",
            autonomy_level=autonomy,  # type: ignore[arg-type]
            settings={"task_selection_mode": mode},
        )
        self.store.save_project(project)
        return project

    def _backlog_task(self, task_id: str = "accepted", status: str = "todo") -> Task:
        backlog = self.store.ensure_backlog("p", created_at="2026-11-12T00:00:00Z")
        task = Task(id=task_id, sprint_id=backlog.id, project_id="p", title=task_id, status=status)  # type: ignore[arg-type]
        self.store.save_task(task)
        return task

    def _orchestrator(self) -> ForemanOrchestrator:
        return ForemanOrchestrator(self.store, roles=self.roles, workflows=self.workflows)

    def test_an_accepted_backlog_task_is_never_selected(self) -> None:
        project = self._project()
        self._backlog_task()

        self.assertIsNone(self._orchestrator().select_next_task(project))

        # Even beside an active sprint with nothing left to do.
        self.store.save_sprint(Sprint(id="s", project_id="p", title="S", status="active"))
        self.assertIsNone(self._orchestrator().select_next_task(project))

    def test_the_engine_never_activates_the_backlog(self) -> None:
        self._project()
        backlog_task = self._backlog_task()

        self.assertIsNone(self._orchestrator().sprints.activate_first_planned("p"))

        self.assertEqual(self.store.get_sprint(backlog_task.sprint_id).status, "planned")
        self.assertIsNone(self.store.get_active_sprint("p"))
        self.assertIsNone(self.store.get_next_planned_sprint("p"))

    def test_finishing_the_last_sprint_does_not_advance_into_the_backlog(self) -> None:
        project = self._project(autonomy="autonomous")
        self._backlog_task()
        sprint = Sprint(id="s", project_id="p", title="S", status="active")
        self.store.save_sprint(sprint)
        self.store.save_task(Task(id="done", sprint_id="s", project_id="p", title="d", status="done"))

        result = self._orchestrator().sprints.advance(project, self.store.get_sprint("s"))

        self.assertEqual(result, "idle")
        self.assertIsNone(self.store.get_active_sprint("p"))
        self.assertEqual(self.store.get_backlog("p").status, "planned")

    def test_autonomous_mode_creates_nothing_in_the_backlog(self) -> None:
        project = self._project(mode="autonomous")
        self._backlog_task()

        self.assertIsNone(self._orchestrator().select_next_task(project))
        self.assertEqual(len(self.store.list_tasks(project_id="p")), 1)

    def test_planning_a_backlog_task_makes_it_selectable(self) -> None:
        from foreman.mutations import Mutations

        project = self._project()
        task = self._backlog_task()
        self.store.save_sprint(Sprint(id="s", project_id="p", title="S", status="active"))

        Mutations(self.store, via="cli").plan_tasks([task], sprint=self.store.get_sprint("s"))

        selected = self._orchestrator().select_next_task(project)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.id, task.id)


if __name__ == "__main__":
    unittest.main()
