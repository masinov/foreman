"""Persisting agent events and applying their signals."""

from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from foreman.models import Project, Run, Sprint, Task
from foreman.engine.results import AgentEventRecord
from foreman.orchestrator import ForemanOrchestrator
from foreman.store import ForemanStore



class AgentSignalPersistenceTests(unittest.TestCase):
    """Regression coverage for persisted agent-created task signals."""

    def test_signal_task_created_persists_engine_event_on_active_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "foreman.db"
            with ForemanStore(db_path) as store:
                store.initialize()
                project = Project(
                    id="project-1",
                    name="Foreman Demo",
                    repo_path=temp_dir,
                    workflow_id="development",
                )
                sprint = Sprint(
                    id="sprint-1",
                    project_id=project.id,
                    title="Active Sprint",
                    status="active",
                    order_index=0,
                )
                task = Task(
                    id="task-1",
                    sprint_id=sprint.id,
                    project_id=project.id,
                    title="Parent task",
                    status="in_progress",
                )
                run = Run(
                    id="run-1",
                    task_id=task.id,
                    project_id=project.id,
                    role_id="developer",
                    workflow_step="develop",
                    agent_backend="claude_code",
                    status="running",
                )
                store.save_project(project)
                store.save_sprint(sprint)
                store.save_task(task)
                store.save_run(run)

                event_record = AgentEventRecord(
                    event_type="signal.task_created",
                    payload={
                        "title": "Follow-up task",
                        "task_type": "fix",
                        "description": "Created from an agent signal.",
                        "criteria": "Follow-up is persisted.",
                    },
                    timestamp="2026-06-12T10:00:00Z",
                )

                orchestrator = ForemanOrchestrator(store)
                orchestrator.signals.persist_agent_event(
                    run,
                    task,
                    project,
                    "developer",
                    event_record,
                )

                # The follow-up does not join the running sprint (ADR-0021).
                self.assertEqual(
                    [item.id for item in store.list_tasks(sprint_id=sprint.id)], [task.id]
                )
                backlog = store.get_backlog(project.id)
                assert backlog is not None
                created = store.list_tasks(sprint_id=backlog.id)
                self.assertEqual(len(created), 1)
                self.assertEqual(created[0].title, "Follow-up task")
                self.assertEqual(created[0].created_by, "agent:developer")
                self.assertEqual(created[0].task_type, "fix")
                # The default triage policy is `human`: filed, waiting for a person.
                self.assertEqual(created[0].status, "triage")

                events = store.list_events(task_id=task.id)
                created_events = [
                    event for event in events if event.event_type == "engine.task_created"
                ]
                self.assertEqual(len(created_events), 1)
                self.assertEqual(created_events[0].run_id, run.id)
                self.assertEqual(created_events[0].payload["task_id"], created[0].id)

    def test_signal_blocker_emits_exactly_one_attention_needed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "foreman.db"
            with ForemanStore(db_path) as store:
                store.initialize()
                project = Project(id="p", name="P", repo_path=temp_dir, workflow_id="development")
                sprint = Sprint(id="s", project_id="p", title="A", status="active")
                task = Task(id="t", sprint_id="s", project_id="p", title="T", status="in_progress")
                run = Run(
                    id="r", task_id="t", project_id="p", role_id="developer",
                    workflow_step="develop", agent_backend="claude_code", status="running",
                )
                for obj in (project, sprint, task, run):
                    getattr(store, f"save_{type(obj).__name__.lower()}")(obj)

                orchestrator = ForemanOrchestrator(store)
                orchestrator.signals.persist_agent_event(
                    run, task, project, "developer",
                    AgentEventRecord(
                        event_type="signal.blocker",
                        payload={"message": "Cannot proceed without the API key."},
                        timestamp="2026-06-13T10:00:00Z",
                    ),
                )

                attention = [
                    e for e in store.list_events(task_id="t")
                    if e.event_type == "engine.attention_needed"
                ]
                self.assertEqual(len(attention), 1)
                self.assertEqual(attention[0].payload["trigger"], "task_blocked")
                self.assertEqual(attention[0].payload["task_id"], "t")
                self.assertEqual(store.get_task("t").status, "blocked")

    def test_signal_task_created_persists_valid_complexity_and_ignores_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "foreman.db"
            with ForemanStore(db_path) as store:
                store.initialize()
                project = Project(id="p", name="P", repo_path=temp_dir, workflow_id="development")
                sprint = Sprint(id="s", project_id="p", title="A", status="active")
                task = Task(id="t", sprint_id="s", project_id="p", title="Parent", status="in_progress")
                run = Run(
                    id="r", task_id="t", project_id="p", role_id="architect",
                    workflow_step="plan", agent_backend="claude_code", status="running",
                )
                for obj in (project, sprint, task, run):
                    getattr(store, f"save_{type(obj).__name__.lower()}")(obj)

                orchestrator = ForemanOrchestrator(store)
                orchestrator.signals.persist_agent_event(
                    run, task, project, "architect",
                    AgentEventRecord(
                        event_type="signal.task_created",
                        payload={"title": "Big task", "complexity": "large"},
                        timestamp="2026-06-12T10:00:00Z",
                    ),
                )
                orchestrator.signals.persist_agent_event(
                    run, task, project, "architect",
                    AgentEventRecord(
                        event_type="signal.task_created",
                        payload={"title": "Bogus complexity", "complexity": "enormous"},
                        timestamp="2026-06-12T10:01:00Z",
                    ),
                )

                created = {t.title: t for t in store.list_tasks(project_id="p") if t.id != "t"}
                self.assertEqual(created["Big task"].complexity, "large")
                self.assertIsNone(created["Bogus complexity"].complexity)


class AgentFiledTaskTriageTests(unittest.TestCase):
    """A task an agent files lands in the backlog under the project's triage policy."""

    def _file(self, settings: dict, payload: dict) -> tuple[ForemanStore, Task]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        store = ForemanStore(Path(temp_dir.name) / "foreman.db")
        self.addCleanup(store.close)
        store.initialize()
        project = Project(
            id="p", name="P", repo_path=temp_dir.name, workflow_id="development",
            settings=settings,
        )
        sprint = Sprint(id="s", project_id="p", title="A", status="active")
        task = Task(id="t", sprint_id="s", project_id="p", title="Parent", status="in_progress")
        run = Run(
            id="r", task_id="t", project_id="p", role_id="developer",
            workflow_step="develop", agent_backend="claude_code", status="running",
        )
        for obj in (project, sprint, task, run):
            getattr(store, f"save_{type(obj).__name__.lower()}")(obj)
        ForemanOrchestrator(store).signals.persist_agent_event(
            run, task, project, "developer",
            AgentEventRecord(
                event_type="signal.task_created", payload=payload,
                timestamp="2026-11-12T10:00:00Z",
            ),
        )
        (created,) = [t for t in store.list_tasks(project_id="p") if t.id != "t"]
        return store, created

    def test_with_triage_human_it_is_filed_and_a_person_is_asked(self) -> None:
        store, created = self._file({}, {"title": "Follow up", "task_type": "fix"})

        self.assertTrue(store.get_sprint(created.sprint_id).is_backlog)
        self.assertEqual(created.status, "triage")
        events = {e.event_type: e for e in store.list_events(task_id=created.id)}
        self.assertEqual(events["backlog.task_filed"].payload["by"], "agent:developer")
        self.assertEqual(events["backlog.task_filed"].payload["via"], "engine")
        self.assertEqual(events["backlog.task_filed"].payload["filed_from_task_id"], "t")
        self.assertEqual(events["engine.attention_needed"].payload["trigger"], "triage")

    def test_with_triage_auto_it_is_accepted_but_not_planned(self) -> None:
        store, created = self._file(
            {"triage": "auto"}, {"title": "Follow up", "task_type": "fix"}
        )

        self.assertTrue(store.get_sprint(created.sprint_id).is_backlog)
        self.assertEqual(created.status, "todo")
        self.assertNotIn(
            "engine.attention_needed",
            {e.event_type for e in store.list_events(task_id=created.id)},
        )
        # The engine runs the active sprint only, so it never picks it up.
        project = store.get_project("p")
        store.save_task(
            Task(id="t", sprint_id="s", project_id="p", title="Parent", status="done")
        )
        self.assertIsNone(ForemanOrchestrator(store).select_next_task(project))

    def test_a_task_type_rule_applies_to_agent_filed_work(self) -> None:
        _, created = self._file(
            {"triage": "auto", "policy_rules": {"feature": {"triage": "human"}}},
            {"title": "New thing", "task_type": "feature"},
        )

        self.assertEqual(created.status, "triage")

    def test_an_unknown_type_is_filed_as_a_feature_and_the_refusal_recorded(self) -> None:
        store, created = self._file({}, {"title": "Odd", "task_type": "bugfix"})

        self.assertEqual(created.task_type, "feature")
        rejected = [
            e for e in store.list_events(task_id="t") if e.event_type == "signal.rejected"
        ]
        self.assertEqual(rejected[0].payload["field"], "task_type")


if __name__ == "__main__":
    unittest.main()
