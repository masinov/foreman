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


class BacklogMutationsTests(unittest.TestCase):
    """File, accept, decline, plan and unplan backlog work (ADR-0021)."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.store = ForemanStore(Path(self._temp.name) / "foreman.db")
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.project = Project(
            id="p1", name="P", repo_path=self._temp.name, workflow_id="development"
        )
        self.store.save_project(self.project)
        self.store.save_sprint(Sprint(id="s1", project_id="p1", title="Now", status="active"))
        self.store.save_sprint(Sprint(id="s2", project_id="p1", title="Next", status="planned"))
        self.mutations = Mutations(self.store, via="cli", actor="alice")

    def file(self, title: str = "Fix the thing", **fields: object) -> Task:
        return self.mutations.file_task(self.project, title=title, **fields).task  # type: ignore[arg-type]

    def accepted(self, title: str) -> Task:
        return self.mutations.accept_task(self.file(title))

    def events(self, task_id: str, event_type: str):
        return [e for e in self.store.list_events(task_id=task_id) if e.event_type == event_type]

    def assert_audited(self, task_id: str, event_type: str, **payload: object) -> None:
        (event,) = self.events(task_id, event_type)
        self.assertEqual((event.payload["via"], event.payload["by"]), ("cli", "alice"))
        for key, value in payload.items():
            self.assertEqual(event.payload[key], value, key)

    # ── file ─────────────────────────────────────────────────────────────

    def test_filing_puts_the_task_in_the_one_backlog_and_audits_it(self) -> None:
        first = self.file("One", task_type="fix", acceptance_criteria="done")
        second = self.file("Two")

        backlog = self.store.get_backlog("p1")
        assert backlog is not None
        self.assertEqual({first.sprint_id, second.sprint_id}, {backlog.id})
        self.assertEqual((backlog.id, backlog.title, backlog.status), ("p1-backlog", "Backlog", "planned"))
        self.assertEqual(first.status, "triage")  # the default triage policy is `human`
        self.assertEqual(first.task_type, "fix")
        self.assertTrue(first.task_key)
        self.assertEqual(first.created_by, "alice")
        self.assert_audited(first.id, "backlog.task_filed", status="triage", sprint_id=backlog.id)
        self.assertEqual(self.events(first.id, "backlog.task_filed")[0].payload["triage"]["value"], "human")
        # A filed task waits for a person: one attention turn.
        (attention,) = self.events(first.id, "engine.attention_needed")
        self.assertEqual(attention.payload["trigger"], "triage")

    def test_filing_follows_the_triage_policy_and_never_plans(self) -> None:
        self.project.settings = {"triage": "auto", "policy_rules": {"fix": {"triage": "human"}}}
        self.store.save_project(self.project)

        feature = self.file("Auto accepted", task_type="feature")
        fix = self.file("Needs a person", task_type="fix")

        self.assertEqual((feature.status, fix.status), ("todo", "triage"))
        self.assertTrue(self.store.get_sprint(feature.sprint_id).is_backlog)
        self.assertEqual(self.events(feature.id, "engine.attention_needed"), [])

    def test_a_person_may_file_work_already_accepted(self) -> None:
        task = self.file("Mine", accept=True)

        self.assertEqual(task.status, "todo")
        self.assert_audited(task.id, "backlog.task_filed", status="todo", accepted_by_filer=True)
        self.assertEqual(self.events(task.id, "engine.attention_needed"), [])

    def test_filing_refuses_a_blank_title_or_an_unknown_type(self) -> None:
        for fields in ({"title": "  "}, {"title": "x", "task_type": "bug"}, {"title": "x", "complexity": "huge"}):
            with self.subTest(fields=fields), self.assertRaises(MutationError):
                self.mutations.file_task(self.project, **fields)  # type: ignore[arg-type]
        self.assertEqual(self.store.list_tasks(project_id="p1"), [])

    # ── accept ───────────────────────────────────────────────────────────

    def test_accepting_keeps_the_task_in_the_backlog(self) -> None:
        task = self.mutations.accept_task(self.file())

        stored = self.store.get_task(task.id)
        self.assertEqual(stored.status, "todo")
        self.assertTrue(self.store.get_sprint(stored.sprint_id).is_backlog)
        self.assert_audited(task.id, "human.task_accepted", from_status="triage")

    # ── decline ──────────────────────────────────────────────────────────

    def test_declining_keeps_the_task_marked_declined(self) -> None:
        task = self.file()

        self.mutations.decline_task(task, "not for us")

        stored = self.store.get_task(task.id)
        self.assertEqual(stored.status, "declined")
        self.assertTrue(self.store.get_sprint(stored.sprint_id).is_backlog)
        self.assertIsNotNone(stored.completed_at)
        self.assert_audited(task.id, "human.task_declined", from_status="triage", reason="not for us")
        with self.assertRaises(MutationError):
            self.mutations.decline_task(stored)
        with self.assertRaises(MutationError):
            self.mutations.accept_task(stored)

    def test_accepted_work_still_in_the_backlog_can_be_declined(self) -> None:
        task = self.accepted("Changed my mind")

        self.mutations.decline_task(task)

        self.assertEqual(self.store.get_task(task.id).status, "declined")

    def test_declining_a_planned_task_is_refused(self) -> None:
        task = self.accepted("Planned")
        self.mutations.plan_tasks([task], sprint=self.store.get_sprint("s2"))

        with self.assertRaises(MutationError) as caught:
            self.mutations.decline_task(self.store.get_task(task.id))

        self.assertIn("already planned", str(caught.exception))
        self.assertEqual(self.store.get_task(task.id).status, "todo")
        self.assertEqual(self.events(task.id, "human.task_declined"), [])

    def test_a_filed_task_in_a_sprint_is_declined_into_the_backlog(self) -> None:
        # Intake may still file into a named sprint (ADR-0013).
        task = self.mutations.file_task(
            self.project, title="Filed into s2", into=self.store.get_sprint("s2")
        ).task
        self.assertEqual(task.sprint_id, "s2")

        self.mutations.decline_task(task)

        stored = self.store.get_task(task.id)
        self.assertTrue(self.store.get_sprint(stored.sprint_id).is_backlog)
        self.assert_audited(task.id, "human.task_declined", from_sprint_id="s2")

    # ── plan ─────────────────────────────────────────────────────────────

    def test_planning_into_an_existing_sprint_moves_every_task_in_order(self) -> None:
        self.store.save_task(Task(id="already", sprint_id="s2", project_id="p1", title="A", order_index=4))
        first, second = self.accepted("First"), self.accepted("Second")

        result = self.mutations.plan_tasks([first, second], sprint=self.store.get_sprint("s2"))

        self.assertFalse(result.created_sprint)
        self.assertEqual(result.sprint.id, "s2")
        moved = [self.store.get_task(t.id) for t in (first, second)]
        self.assertEqual([t.sprint_id for t in moved], ["s2", "s2"])
        self.assertEqual([t.order_index for t in moved], [5, 6])
        self.assertEqual([t.status for t in moved], ["todo", "todo"])
        for task in moved:
            self.assert_audited(task.id, "human.task_planned", sprint_id="s2", sprint_title="Next")

    def test_planning_into_the_active_sprint_is_allowed(self) -> None:
        task = self.accepted("Urgent")

        self.mutations.plan_tasks([task], sprint=self.store.get_sprint("s1"))

        self.assertEqual(self.store.get_task(task.id).sprint_id, "s1")

    def test_planning_into_a_new_sprint_creates_it_planned_in_the_same_operation(self) -> None:
        task = self.accepted("Later")

        result = self.mutations.plan_tasks(
            [task], new_sprint_title="Sprint 59: later", new_sprint_goal="Do it later"
        )

        self.assertTrue(result.created_sprint)
        sprint = self.store.get_sprint(result.sprint.id)
        self.assertEqual((sprint.title, sprint.goal, sprint.status, sprint.kind),
                         ("Sprint 59: later", "Do it later", "planned", "sprint"))
        self.assertEqual(sprint.order_index, 1)  # after s1 (0) and s2 (0), queue order
        self.assertEqual(self.store.get_task(task.id).sprint_id, sprint.id)
        self.assert_audited(task.id, "human.task_planned", sprint_id=sprint.id, new_sprint=True)

    def test_planning_a_filed_task_is_refused_and_nothing_moves(self) -> None:
        accepted, filed = self.accepted("Ready"), self.file("Not yet")

        with self.assertRaises(MutationError) as caught:
            self.mutations.plan_tasks([accepted, filed], new_sprint_title="Never made")

        self.assertIn("accept it before planning", str(caught.exception))
        self.assertTrue(self.store.get_sprint(self.store.get_task(accepted.id).sprint_id).is_backlog)
        self.assertNotIn("Never made", [s.title for s in self.store.list_sprints("p1")])
        self.assertEqual(self.events(accepted.id, "human.task_planned"), [])

    def test_planning_into_a_completed_or_cancelled_sprint_is_refused(self) -> None:
        task = self.accepted("Late")
        for status in ("completed", "cancelled"):
            self.store.save_sprint(Sprint(id=f"old-{status}", project_id="p1", title="Old", status=status))
            with self.subTest(status=status):
                with self.assertRaises(MutationError) as caught:
                    self.mutations.plan_tasks([task], sprint=self.store.get_sprint(f"old-{status}"))
                self.assertIn("planned or active", str(caught.exception))
        self.assertTrue(self.store.get_sprint(self.store.get_task(task.id).sprint_id).is_backlog)

    def test_planning_refuses_declined_work_tasks_outside_the_backlog_and_the_backlog(self) -> None:
        declined = self.mutations.decline_task(self.file("No"))
        in_sprint = Task(id="in-sprint", sprint_id="s1", project_id="p1", title="Here")
        self.store.save_task(in_sprint)
        ready = self.accepted("Ready")
        cases = (
            ([declined], {"sprint": self.store.get_sprint("s2")}),
            ([self.store.get_task("in-sprint")], {"sprint": self.store.get_sprint("s2")}),
            ([ready], {"sprint": self.store.get_backlog("p1")}),
            ([ready], {}),
            ([ready], {"sprint": self.store.get_sprint("s2"), "new_sprint_title": "Both"}),
            ([], {"sprint": self.store.get_sprint("s2")}),
            ([ready, ready], {"sprint": self.store.get_sprint("s2")}),
        )
        for tasks, target in cases:
            with self.subTest(tasks=[t.id for t in tasks], target=list(target)):
                with self.assertRaises(MutationError):
                    self.mutations.plan_tasks(tasks, **target)  # type: ignore[arg-type]

    def test_planning_a_task_someone_changed_meanwhile_moves_nothing(self) -> None:
        first, second = self.accepted("First"), self.accepted("Second")
        stale = self.store.get_task(second.id)
        self.mutations.decline_task(self.store.get_task(second.id))

        with self.assertRaises(MutationError):
            # `stale` still says todo; the store checks the row it writes.
            self.mutations.plan_tasks([first, stale], new_sprint_title="Half")

        self.assertTrue(self.store.get_sprint(self.store.get_task(first.id).sprint_id).is_backlog)
        self.assertNotIn("Half", [s.title for s in self.store.list_sprints("p1")])

    # ── unplan ───────────────────────────────────────────────────────────

    def test_a_task_that_has_not_started_moves_back_to_the_backlog(self) -> None:
        task = self.accepted("Round trip")
        self.mutations.plan_tasks([task], sprint=self.store.get_sprint("s1"))

        moved = self.mutations.unplan_task(self.store.get_task(task.id))

        self.assertTrue(self.store.get_sprint(moved.sprint_id).is_backlog)
        self.assertEqual(moved.status, "todo")  # still accepted
        self.assert_audited(task.id, "human.task_unplanned", from_sprint_id="s1", from_sprint_title="Now")

    def test_a_started_task_or_a_backlog_task_cannot_be_unplanned(self) -> None:
        for status in ("in_progress", "blocked", "done", "cancelled"):
            task = Task(id=f"t-{status}", sprint_id="s1", project_id="p1", title="T", status=status)  # type: ignore[arg-type]
            self.store.save_task(task)
            with self.subTest(status=status), self.assertRaises(MutationError):
                self.mutations.unplan_task(self.store.get_task(task.id))
        with self.assertRaises(MutationError) as caught:
            self.mutations.unplan_task(self.file("Already there"))
        self.assertIn("already in the backlog", str(caught.exception))

    def test_a_task_an_engine_is_running_cannot_be_unplanned(self) -> None:
        task = Task(id="live", sprint_id="s1", project_id="p1", title="T")
        self.store.save_task(task)
        self.store.save_run(
            Run(id="run-live", task_id="live", project_id="p1", role_id="developer",
                workflow_step="develop", agent_backend="claude_code", status="running")
        )
        self.store.acquire_lease(project_id="p1", resource_type=ENGINE_RESOURCE_TYPE,
                                 resource_id="p1", holder_id="engine-a", lease_token="tok")

        with self.assertRaises(MutationError):
            self.mutations.unplan_task(self.store.get_task("live"))
        self.assertEqual(self.store.get_task("live").sprint_id, "s1")

    # ── the backlog is not a sprint ──────────────────────────────────────

    def test_the_backlog_cannot_be_activated_completed_cancelled_or_deleted(self) -> None:
        self.file()
        backlog = self.store.get_backlog("p1")
        self.mutations.transition_sprint(self.store.get_sprint("s1"), "completed")

        for target in ("active", "completed", "cancelled"):
            with self.subTest(target=target), self.assertRaises(MutationError):
                self.mutations.transition_sprint(backlog, target)
        with self.assertRaises(MutationError):
            self.mutations.delete_sprint(backlog)
        self.assertEqual(self.store.get_backlog("p1").status, "planned")

    def test_a_backlog_task_cannot_be_blocked(self) -> None:
        with self.assertRaises(MutationError):
            self.mutations.block_task(self.file(), "why")


if __name__ == "__main__":
    unittest.main()
