"""Choosing the next task: what was planned, then (when a project allows it) backlog work."""

from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from foreman.domain.models import Project, Sprint, Task
from foreman.engine.errors import OrchestratorError
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.store import ForemanStore

from engine_support import (
    RepoTestCase,
)


class AutonomousTaskSelectionTests(RepoTestCase):
    """select_next_task when Foreman may start backlog work on its own (ADR-0028)."""

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

    # ── Foreman starts backlog work on its own (ADR-0028) ────────────────

    def _backlog(self, store: ForemanStore, task_id: str, *, status: str = "todo", **fields) -> Task:
        backlog = store.ensure_backlog("proj-auto", created_at="2026-11-16T00:00:00Z")
        task = Task(
            id=task_id,
            sprint_id=backlog.id,
            project_id="proj-auto",
            title=task_id,
            status=status,  # type: ignore[arg-type]
            order_index=store.next_task_order_index(backlog.id),
            **fields,
        )
        return store.save_task(task)

    def _planned(self, store: ForemanStore, task_id: str, status: str = "todo", **fields) -> Task:
        return store.save_task(
            Task(id=task_id, sprint_id="sprint-auto", project_id="proj-auto", title=task_id, status=status, **fields)  # type: ignore[arg-type]
        )

    def test_with_no_active_sprint_nothing_is_taken(self) -> None:
        store, _ = self._make_store()
        project = Project(
            id="proj-auto", name="Auto", repo_path="/tmp/auto", workflow_id="development",
            settings={"task_selection_mode": "autonomous"},
        )
        store.save_project(project)
        waiting = self._backlog(store, "waiting")

        self.assertIsNone(self._orchestrator(store).select_next_task(project))
        self.assertEqual(store.get_task("waiting").sprint_id, waiting.sprint_id)

    def test_what_a_person_planned_runs_first(self) -> None:
        store, _ = self._make_store()
        project, _sprint = self._seed(store)
        self._backlog(store, "from-backlog")
        self._planned(store, "planned")

        selected = self._orchestrator(store).select_next_task(project)

        assert selected is not None
        self.assertEqual(selected.id, "planned")
        self.assertTrue(store.get_sprint(store.get_task("from-backlog").sprint_id).is_backlog)

    def test_with_nothing_planned_to_run_the_next_accepted_backlog_task_is_taken(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store)
        self._planned(store, "finished", "done")
        self._planned(store, "waits-for-a-person", "blocked", blocked_reason="Awaiting human approval")
        self._backlog(store, "from-backlog")

        selected = self._orchestrator(store).select_next_task(project)

        assert selected is not None
        self.assertEqual((selected.id, selected.sprint_id, selected.status), ("from-backlog", sprint.id, "todo"))
        (pulled,) = [e for e in store.list_events(task_id="from-backlog") if e.event_type == "engine.task_pulled"]
        self.assertEqual((pulled.payload["via"], pulled.payload["by"]), ("policy", "foreman"))
        self.assertEqual(pulled.payload["sprint_id"], sprint.id)
        # It is leased like any task the engine is about to run.
        self.assertIsNotNone(
            store.get_active_lease(project_id=project.id, resource_type="task", resource_id="from-backlog")
        )

    def test_higher_priority_goes_first_then_the_order_it_was_filed_in(self) -> None:
        store, _ = self._make_store()
        project, _sprint = self._seed(store)
        self._backlog(store, "first-filed")
        self._backlog(store, "second-filed")
        self._backlog(store, "urgent", priority=5)

        taken = []
        for _ in range(3):
            selected = self._orchestrator(store).select_next_task(project)
            assert selected is not None
            taken.append(selected.id)
            selected.status = "done"
            store.save_task(selected)

        self.assertEqual(taken, ["urgent", "first-filed", "second-filed"])

    def test_a_request_no_person_has_accepted_is_never_taken(self) -> None:
        store, _ = self._make_store()
        project, _sprint = self._seed(store)
        request = self._backlog(store, "request", status="triage", created_by="agent:developer")

        self.assertIsNone(self._orchestrator(store).select_next_task(project))

        stored = store.get_task("request")
        self.assertEqual((stored.status, stored.sprint_id), ("triage", request.sprint_id))

    def test_it_stops_at_the_limit_per_sprint(self) -> None:
        store, _ = self._make_store()
        project, _sprint = self._seed(store, max_autonomous_tasks=1)
        self._backlog(store, "one")
        self._backlog(store, "two")

        first = self._orchestrator(store).select_next_task(project)
        assert first is not None
        first.status = "done"
        store.save_task(first)

        self.assertIsNone(self._orchestrator(store).select_next_task(project))
        self.assertTrue(store.get_sprint(store.get_task("two").sprint_id).is_backlog)

    def test_the_default_limit_is_five(self) -> None:
        store, _ = self._make_store()
        project, sprint = self._seed(store)
        for n in range(7):
            self._backlog(store, f"task-{n}")

        taken = 0
        while True:
            selected = self._orchestrator(store).select_next_task(project)
            if selected is None:
                break
            taken += 1
            selected.status = "done"
            store.save_task(selected)

        self.assertEqual(taken, 5)

    def test_what_a_person_planned_from_the_backlog_does_not_use_up_the_limit(self) -> None:
        from foreman.mutations import Mutations

        store, _ = self._make_store()
        project, sprint = self._seed(store, max_autonomous_tasks=1)
        mine = self._backlog(store, "planned-by-a-person")
        Mutations(store, via="cli", actor="alice").plan_tasks([mine], sprint=sprint)
        done = store.get_task("planned-by-a-person")
        done.status = "done"
        store.save_task(done)
        self._backlog(store, "for-foreman")

        selected = self._orchestrator(store).select_next_task(project)

        assert selected is not None
        self.assertEqual(selected.id, "for-foreman")

    def test_backlog_work_that_waits_for_unfinished_work_is_not_taken(self) -> None:
        store, _ = self._make_store()
        project, _sprint = self._seed(store)
        self._planned(store, "prerequisite", "blocked", blocked_reason="Parked")
        self._backlog(store, "needs-it", depends_on_task_ids=["prerequisite"])
        self._backlog(store, "free")

        selected = self._orchestrator(store).select_next_task(project)

        assert selected is not None
        self.assertEqual(selected.id, "free")

    def test_a_task_in_progress_is_resumed_before_anything_is_taken(self) -> None:
        store, _ = self._make_store()
        project, _sprint = self._seed(store)
        self._planned(store, "resumable", "in_progress", workflow_current_step="develop")
        self._backlog(store, "from-backlog")

        selected = self._orchestrator(store).select_next_task(project)

        assert selected is not None
        self.assertEqual(selected.id, "resumable")
        self.assertTrue(store.get_sprint(store.get_task("from-backlog").sprint_id).is_backlog)

    def test_a_project_that_does_not_let_foreman_start_backlog_work_takes_nothing(self) -> None:
        store, _ = self._make_store()
        project, _sprint = self._seed(store, selection_mode="directed")
        self._backlog(store, "from-backlog")

        self.assertIsNone(self._orchestrator(store).select_next_task(project))
        self.assertTrue(store.get_sprint(store.get_task("from-backlog").sprint_id).is_backlog)

    def test_nothing_is_invented_when_the_backlog_is_empty(self) -> None:
        store, _ = self._make_store()
        project, _sprint = self._seed(store)

        self.assertIsNone(self._orchestrator(store).select_next_task(project))
        self.assertEqual(store.list_tasks(project_id=project.id), [])

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
    """The backlog is not a sprint (ADR-0021): the engine runs the active sprint, and only
    a project that lets Foreman start backlog work has tasks taken from it (ADR-0028)."""

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

        result = self._orchestrator().sprints.resolve(project, self.store.get_sprint("s"))

        self.assertEqual(result, "idle")
        self.assertIsNone(self.store.get_active_sprint("p"))
        self.assertEqual(self.store.get_backlog("p").status, "planned")

    def test_with_no_active_sprint_backlog_work_stays_where_it_is(self) -> None:
        project = self._project(mode="autonomous")
        task = self._backlog_task()

        self.assertIsNone(self._orchestrator().select_next_task(project))
        self.assertEqual(self.store.get_task(task.id).sprint_id, task.sprint_id)
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
