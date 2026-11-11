"""Moving from one sprint to the next."""

from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from foreman.models import Project, Sprint, Task
from foreman.orchestrator import ForemanOrchestrator
from foreman.roles import default_roles_dir, load_roles
from foreman.store import ForemanStore
from foreman.workflows import (
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

    def _make_project(self, autonomy_level: str = "directed") -> Project:
        p = Project(
            id=f"proj-adv-{autonomy_level}",
            name=f"Test {autonomy_level}",
            repo_path=self.tmp.name,
            workflow_id="development",
            autonomy_level=autonomy_level,  # type: ignore[arg-type]
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

    def test_directed_completes_sprint_and_stops(self) -> None:
        project = self._make_project("directed")
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        sprint1 = self._make_sprint(project.id, order_index=1, status="planned")
        self._make_done_task(sprint0)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "sprint_complete")
        self.assertIsNone(self.store.get_active_sprint(project.id))
        s0 = next(s for s in self.store.list_sprints(project.id) if s.id == sprint0.id)
        self.assertEqual(s0.status, "completed")
        s1 = next(s for s in self.store.list_sprints(project.id) if s.id == sprint1.id)
        self.assertEqual(s1.status, "planned")

    def test_directed_idle_when_no_next_sprint(self) -> None:
        project = self._make_project("directed")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        self._make_done_task(sprint)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "idle")
        s = next(s for s in self.store.list_sprints(project.id) if s.id == sprint.id)
        self.assertEqual(s.status, "completed")

    def test_supervised_emits_sprint_ready_event(self) -> None:
        project = self._make_project("supervised")
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        sprint1 = self._make_sprint(project.id, order_index=1, status="planned")
        task = self._make_done_task(sprint0)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "sprint_complete")
        event_types = [e.event_type for e in self.store.list_events(task_id=task.id)]
        self.assertIn("engine.sprint_completed", event_types)
        self.assertIn("engine.sprint_ready", event_types)
        ready = next(e for e in self.store.list_events(task_id=task.id) if e.event_type == "engine.sprint_ready")
        self.assertEqual(ready.payload["sprint_id"], sprint1.id)

    def test_directed_does_not_emit_sprint_ready(self) -> None:
        project = self._make_project("directed")
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        self._make_sprint(project.id, order_index=1, status="planned")
        task = self._make_done_task(sprint0)

        self._orchestrator().run_project(project.id)

        event_types = [e.event_type for e in self.store.list_events(task_id=task.id)]
        self.assertNotIn("engine.sprint_ready", event_types)
        self.assertIn("engine.sprint_completed", event_types)

    def test_autonomous_activates_next_sprint(self) -> None:
        project = self._make_project("autonomous")
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        sprint1 = self._make_sprint(project.id, order_index=1, status="planned")
        self._make_done_task(sprint0)

        result = self._orchestrator().run_project(project.id)

        s1 = next(s for s in self.store.list_sprints(project.id) if s.id == sprint1.id)
        self.assertEqual(s1.status, "active")
        self.assertIsNotNone(s1.started_at)
        self.assertEqual(result.stop_reason, "idle")

    def test_autonomous_stops_when_no_next_sprint(self) -> None:
        project = self._make_project("autonomous")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        self._make_done_task(sprint)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "idle")

    def test_run_project_auto_activates_first_planned_sprint(self) -> None:
        project = self._make_project("directed")
        sprint = self._make_sprint(project.id, order_index=0, status="planned")
        self._make_done_task(sprint)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "idle")
        refreshed = next(s for s in self.store.list_sprints(project.id) if s.id == sprint.id)
        self.assertEqual(refreshed.status, "completed")
        self.assertIsNotNone(refreshed.started_at)
        self.assertIsNotNone(refreshed.completed_at)

    def test_blocked_tasks_prevent_sprint_completion(self) -> None:
        project = self._make_project("autonomous")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        t = Task(
            id="task-adv-blocked",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Blocked task",
            status="blocked",
        )
        self.store.save_task(t)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "blocked")
        s = next(s for s in self.store.list_sprints(project.id) if s.id == sprint.id)
        self.assertEqual(s.status, "active")

    def test_sprint_with_mixed_done_cancelled_is_resolved(self) -> None:
        project = self._make_project("directed")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        self._make_done_task(sprint)
        t = Task(
            id="task-adv-cancelled",
            sprint_id=sprint.id,
            project_id=project.id,
            title="Cancelled task",
            status="cancelled",
        )
        self.store.save_task(t)

        result = self._orchestrator().run_project(project.id)

        s = next(s for s in self.store.list_sprints(project.id) if s.id == sprint.id)
        self.assertEqual(s.status, "completed")
        self.assertEqual(result.stop_reason, "idle")

    def _sprint_resolved_triggers(self, task_id: str) -> list[str]:
        return [
            e.payload.get("trigger")
            for e in self.store.list_events(task_id=task_id)
            if e.event_type == "engine.attention_needed"
        ]

    def test_supervised_sprint_completion_emits_sprint_resolved_attention(self) -> None:
        project = self._make_project("supervised")
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        self._make_sprint(project.id, order_index=1, status="planned")
        task = self._make_done_task(sprint0)

        self._orchestrator().run_project(project.id)

        self.assertEqual(self._sprint_resolved_triggers(task.id), ["sprint_resolved"])

    def test_directed_idle_emits_sprint_resolved_attention(self) -> None:
        project = self._make_project("directed")
        sprint = self._make_sprint(project.id, order_index=0, status="active")
        task = self._make_done_task(sprint)

        result = self._orchestrator().run_project(project.id)

        self.assertEqual(result.stop_reason, "idle")
        self.assertEqual(self._sprint_resolved_triggers(task.id), ["sprint_resolved"])

    def test_autonomous_auto_advance_does_not_emit_sprint_resolved(self) -> None:
        project = self._make_project("autonomous")
        sprint0 = self._make_sprint(project.id, order_index=0, status="active")
        self._make_sprint(project.id, order_index=1, status="planned")
        task = self._make_done_task(sprint0)

        self._orchestrator().run_project(project.id)

        # Autonomous mode advances itself; no manager handoff is needed.
        self.assertEqual(self._sprint_resolved_triggers(task.id), [])


if __name__ == "__main__":
    unittest.main()
