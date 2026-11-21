"""Moving from one sprint to the next."""

from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from foreman.domain.models import Project, Sprint, Task
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.definitions.roles import default_roles_dir, load_roles
from foreman.store import ForemanStore
from foreman.definitions.workflows import (
    default_workflows_dir,
    load_workflows,
)



class SprintAdvancementTests(unittest.TestCase):
    """Tests for sprint-41: orchestrator sprint completion and auto-advancement."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.store.initialize()

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _make_project(self, autonomy_level: str = "directed", *, foreman_finishes: bool = False) -> Project:
        p = Project(
            id=f"proj-adv-{autonomy_level}{'-auto' if foreman_finishes else ''}",
            name=f"Test {autonomy_level}",
            repo_path=self.tmp.name,
            workflow_id="development",
            autonomy_level=autonomy_level,  # type: ignore[arg-type]
            settings={"sprint_completion": "auto"} if foreman_finishes else {},
        )
        self.store.save_project(p)
        return p

    def _make_sprint(self, project_id: str, *, order_index: int = 0, status: str = "planned") -> Sprint:
        s = Sprint(
            id=f"sprint-adv-{project_id}-{order_index}",
            project_id=project_id,
            title=f"Sprint {order_index}",
            status=status,  # type: ignore[arg-type]
            order_index=order_index,
        )
        self.store.save_sprint(s)
        return s

    def _make_done_task(self, sprint: Sprint) -> Task:
        t = Task(
            id=f"task-adv-{sprint.id}",
            sprint_id=sprint.id,
            project_id=sprint.project_id,
            title="Done task",
            status="done",
        )
        self.store.save_task(t)
        return t

    def _orchestrator(self) -> ForemanOrchestrator:
        roles = load_roles(default_roles_dir())
        workflows = load_workflows(default_workflows_dir(), available_role_ids=set(roles))
        return ForemanOrchestrator(self.store, roles=roles, workflows=workflows)

    def _sprint(self, sprint_id: str):
        return self.store.get_sprint(sprint_id)

    def _event_types(self, project_id: str) -> list[str]:
        return [e.event_type for e in self.store.list_events(project_id=project_id)]

    def _attention(self, project_id: str) -> list[str]:
        return [
            e.payload.get("trigger")
            for e in self.store.list_events(project_id=project_id)
            if e.event_type == "engine.attention_needed"
        ]

    def _orchestrator_running_tasks(self) -> ForemanOrchestrator:
        """An orchestrator whose run_task marks the task done and records it."""
        orchestrator = self._orchestrator()
        self.ran: list[str] = []

        def run_task(project, workflow, task):
            task.status = "done"
            self.store.save_task(task)
            self.ran.append(task.id)
            return task

        orchestrator.run_task = run_task  # type: ignore[method-assign]
        return orchestrator

    def _todo_task(self, sprint: Sprint, task_id: str) -> Task:
        t = Task(
            id=task_id, sprint_id=sprint.id, project_id=sprint.project_id,
            title=task_id, status="todo",
        )
        self.store.save_task(t)
        return t

    def test_directed_leaves_resolved_sprint_active(self) -> None:
        project = self._make_project("directed")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        self._make_done_task(sprint)
        self.store.save_task(Task(
            id="task-adv-cancelled", sprint_id=sprint.id, project_id=project.id,
            title="Cancelled", status="cancelled",
        ))

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "sprint_resolved")
        s = self._sprint(sprint.id)
        self.assertEqual(s.status, "active")
        self.assertIsNone(s.completed_at)
        self.assertNotIn("engine.sprint_completed", self._event_types(project.id))
        self.assertEqual(self._attention(project.id), ["sprint_resolved"])

    def test_supervised_leaves_resolved_sprint_active_and_next_planned(self) -> None:
        project = self._make_project("supervised")
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        sprint1 = self._make_sprint(project.id, order_index=1, status="planned")
        self._make_done_task(sprint0)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "sprint_resolved")
        s0 = self._sprint(sprint0.id)
        self.assertEqual(s0.status, "active")
        self.assertIsNone(s0.completed_at)
        self.assertEqual(self._sprint(sprint1.id).status, "planned")
        events = self._event_types(project.id)
        self.assertNotIn("engine.sprint_completed", events)
        self.assertEqual(events.count("engine.sprint_ready"), 1)
        self.assertEqual(self._attention(project.id), ["sprint_resolved"])

    def test_foreman_finishes_and_activates_next_sprint_and_runs_it(self) -> None:
        project = self._make_project("supervised", foreman_finishes=True)
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        sprint1 = self._make_sprint(project.id, order_index=1, status="planned")
        self._make_done_task(sprint0)
        next_task = self._todo_task(sprint1, "task-adv-next")

        result = self._orchestrator_running_tasks().run_project(project.id)

        s0 = self._sprint(sprint0.id)
        self.assertEqual(s0.status, "completed")
        self.assertIsNotNone(s0.completed_at)
        self.assertIn("engine.sprint_completed", self._event_types(project.id))
        self.assertEqual(self._sprint(sprint1.id).status, "completed")
        self.assertEqual(self.ran, [next_task.id])
        self.assertEqual(result.stop_reason, "idle")

    def test_foreman_finishing_with_no_next_sprint_stops_idle_with_one_attention(self) -> None:
        project = self._make_project("supervised", foreman_finishes=True)
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        self._make_done_task(sprint)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "idle")
        self.assertEqual(self._sprint(sprint.id).status, "completed")
        self.assertEqual(self._attention(project.id), ["sprint_resolved"])

    def test_an_autonomous_level_alone_does_not_finish_a_sprint(self) -> None:
        # Who finishes a sprint is its own setting since 2026-11-19
        # (ADR-0025 amendment); the autonomy level no longer decides it.
        project = self._make_project("autonomous")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        self._make_done_task(sprint)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "sprint_resolved")
        self.assertEqual(self._sprint(sprint.id).status, "active")

    def test_after_a_person_finishes_a_sprint_the_next_waits_to_be_activated(self) -> None:
        from foreman.mutations import Mutations

        project = self._make_project("supervised")
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        sprint1 = self._make_sprint(project.id, order_index=1, status="planned")
        self._make_done_task(sprint0)
        next_task = self._todo_task(sprint1, "task-adv-next")
        orchestrator = self._orchestrator_running_tasks()
        orchestrator.run_project(project.id)
        self.assertEqual(self.ran, [])

        mutations = Mutations(self.store, via="cli")
        mutations.transition_sprint(self._sprint(sprint0.id), "completed")
        orchestrator.run_project(project.id)

        # The next sprint waits for a person to activate it (owner, 2026-11-21).
        self.assertEqual(self.ran, [])
        self.assertEqual(self._sprint(sprint1.id).status, "planned")

        mutations.transition_sprint(self._sprint(sprint1.id), "active")
        orchestrator.run_project(project.id)

        self.assertEqual(self.ran, [next_task.id])

    def test_task_added_to_resolved_active_sprint_is_run(self) -> None:
        project = self._make_project("supervised")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        self._make_done_task(sprint)
        orchestrator = self._orchestrator_running_tasks()
        orchestrator.run_project(project.id)
        added = self._todo_task(sprint, "task-adv-added")

        result = orchestrator.run_project(project.id)

        self.assertEqual(self.ran, [added.id])
        self.assertEqual(self._sprint(sprint.id).status, "active")
        self.assertEqual(result.stop_reason, "sprint_resolved")
        # Resolved again by a new task: the person is told again.
        self.assertEqual(self._attention(project.id), ["sprint_resolved"] * 2)

    def test_two_passes_over_resolved_sprint_raise_one_attention(self) -> None:
        project = self._make_project("supervised")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        self._make_done_task(sprint)
        orchestrator = self._orchestrator()

        first = orchestrator.run_project(project.id)
        second = orchestrator.run_project(project.id)

        self.assertEqual(first.stop_reason, "sprint_resolved")
        self.assertEqual(second.stop_reason, "sprint_resolved")
        self.assertEqual(self._attention(project.id), ["sprint_resolved"])
        self.assertEqual(self._event_types(project.id).count("engine.sprint_ready"), 1)

    def test_the_engine_never_activates_a_planned_sprint(self) -> None:
        # A sprint created while the engine runs is planned, not started:
        # its tasks may not be planned yet (owner, 2026-11-21).
        project = self._make_project("directed")
        sprint = self._make_sprint(project.id, order_index=0, status="planned")
        self._todo_task(sprint, "task-adv-waiting")

        result = self._orchestrator_running_tasks().run_project(project.id)

        self.assertEqual(self.ran, [])
        self.assertEqual(result.stop_reason, "idle")
        refreshed = self._sprint(sprint.id)
        self.assertEqual(refreshed.status, "planned")
        self.assertIsNone(refreshed.started_at)

    def test_blocked_task_prevents_completion_and_attention_at_every_level(self) -> None:
        for level in ("directed", "supervised", "autonomous"):
            with self.subTest(level=level):
                project = self._make_project(level)
                sprint = self._make_sprint(project.id, order_index=0, status="active")
                self.store.save_task(Task(
                    id=f"task-adv-blocked-{level}", sprint_id=sprint.id,
                    project_id=project.id, title="Blocked", status="blocked",
                ))

                result = self._orchestrator().run_project(project.id)

                self.assertEqual(result.stop_reason, "blocked")
                self.assertEqual(self._sprint(sprint.id).status, "active")
                self.assertEqual(self._attention(project.id), [])
                self.assertNotIn("engine.sprint_completed", self._event_types(project.id))

    def test_only_autonomous_path_completes_a_sprint(self) -> None:
        import re
        root = Path(__file__).resolve().parent.parent / "foreman"
        hits = []
        for path in (root / "engine").glob("*.py"):
            for line in path.read_text().splitlines():
                if re.search(r"""\.status\s*=\s*["']completed["']""", line) and "sprint" in line:
                    hits.append((path.name, line.strip()))
        self.assertEqual(hits, [("sprints.py", 'sprint.status = "completed"')])


if __name__ == "__main__":
    unittest.main()
