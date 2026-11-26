"""A user's holds on work (ADR-0043): Pause, Stop, Resume and Block.

Pause is soft and belongs to tasks; on a sprint or the workspace it is a bulk
action. Block is hard, with a reason, and holds everything under it until it
is lifted where it was set. A hold holds what comes after: a task's next
steps, what waits for it, its sprint's finish and the next sprint's start.
"""

from __future__ import annotations

import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from foreman.domain.holds import task_hold
from foreman.domain.models import Project, Run, Sprint, Task
from foreman.engine.builtins import BuiltinExecutor
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.mutations import MutationError, Mutations
from foreman.runner.base import AgentEvent, AgentRunConfig
from foreman.store import ForemanStore

from engine_support import DEV_REPORT, OrchestratorTestCase, ScriptedNativeRunner


class _Store(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = ForemanStore(Path(temp.name) / "foreman.db")
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.repo = temp.name
        self.project("p1")
        self.mutations = Mutations(self.store, via="cli", actor="ana")

    def project(self, project_id: str) -> Project:
        return self.store.save_project(
            Project(id=project_id, name=project_id, repo_path=self.repo, workflow_id="development")
        ) or self.store.get_project(project_id)

    def sprint(self, sprint_id: str, *, project_id: str = "p1", status: str = "active", order: int = 0) -> Sprint:
        self.store.save_sprint(
            Sprint(id=sprint_id, project_id=project_id, title=f"Sprint {sprint_id}", status=status, order_index=order)
        )
        return self.store.get_sprint(sprint_id)

    def task(self, task_id: str, sprint_id: str, *, status: str = "todo", project_id: str = "p1", **kw) -> Task:
        return self.store.save_task(
            Task(id=task_id, sprint_id=sprint_id, project_id=project_id, title=task_id, status=status, **kw)
        )

    def running(self, task: Task) -> None:
        self.store.save_run(
            Run(
                id=f"run-{task.id}", task_id=task.id, project_id=task.project_id, role_id="developer",
                workflow_step="develop", agent_backend="claude_code", status="running",
            )
        )

    def fresh(self, task_id: str) -> Task:
        task = self.store.get_task(task_id)
        assert task is not None
        return task

    def events(self, event_type: str) -> list:
        return [event for event in self.store.list_events(project_id="p1") if event.event_type == event_type]


class TaskPauseTests(_Store):
    def test_pause_and_resume_a_task(self) -> None:
        self.sprint("s1")
        task = self.task("t1", "s1")

        self.mutations.pause_task(task)
        paused = self.fresh("t1")
        self.assertEqual((paused.paused_by, paused.pause_mode, paused.status), ("ana", "finish_step", "todo"))
        self.assertEqual(task_hold(paused).kind, "pause")

        self.mutations.resume_task(paused)
        self.assertIsNone(self.fresh("t1").paused_at)
        kinds = [event.event_type for event in self.store.list_events(task_id="t1")]
        self.assertEqual(kinds, ["human.task_paused", "human.task_resumed"])

    def test_what_cannot_be_paused_or_resumed_says_why(self) -> None:
        self.sprint("s1")
        done = self.task("t-done", "s1", status="done")
        with self.assertRaises(MutationError):
            self.mutations.pause_task(done)
        with self.assertRaisesRegex(MutationError, "not paused"):
            self.mutations.resume_task(self.task("t1", "s1"))
        self.mutations.pause_task(self.fresh("t1"))
        with self.assertRaisesRegex(MutationError, "already paused"):
            self.mutations.pause_task(self.fresh("t1"))
        backlog = self.store.ensure_backlog("p1", created_at="2026-11-26T00:00:00Z")
        with self.assertRaisesRegex(MutationError, "backlog"):
            self.mutations.pause_task(self.task("t-back", backlog.id))

    def test_a_stop_needs_a_running_step(self) -> None:
        self.sprint("s1")
        task = self.task("t1", "s1", status="in_progress", workflow_current_step="develop")
        with self.assertRaisesRegex(MutationError, "Pause it instead"):
            self.mutations.pause_task(task, mode="now")
        self.running(task)
        self.mutations.pause_task(task, mode="now")
        self.assertEqual(self.fresh("t1").pause_mode, "now")
        self.assertEqual(len(self.events("human.task_stopped")), 1)

    def test_a_task_under_a_block_cannot_be_resumed(self) -> None:
        sprint = self.sprint("s1")
        task = self.task("t1", "s1")
        self.mutations.pause_task(task)
        self.mutations.block_sprint(sprint, "design review")
        with self.assertRaisesRegex(MutationError, "Unblock the sprint first"):
            self.mutations.resume_task(self.fresh("t1"))
        self.mutations.unblock_sprint(sprint)
        self.mutations.resume_task(self.fresh("t1"))

    def test_a_hold_does_not_outlive_what_it_was_set_on(self) -> None:
        self.sprint("s1")
        for task_id in ("t-cancel", "t-done", "t-back"):
            self.mutations.pause_task(self.task(task_id, "s1"))
        self.mutations.cancel_task(self.fresh("t-cancel"))
        self.mutations.complete_task(self.fresh("t-done"), "done by hand")
        self.mutations.unplan_task(self.fresh("t-back"))
        for task_id in ("t-cancel", "t-done", "t-back"):
            with self.subTest(task=task_id):
                self.assertIsNone(self.fresh(task_id).paused_at)
        self.mutations.reopen_task(self.fresh("t-done"))
        self.assertIsNone(self.fresh("t-done").paused_at)


class SprintAndWorkspaceTests(_Store):
    def test_pausing_a_sprint_pauses_each_unfinished_task_and_resuming_releases_them(self) -> None:
        sprint = self.sprint("s1")
        self.task("t1", "s1")
        self.task("t2", "s1", status="in_progress", workflow_current_step="develop")
        self.task("t3", "s1", status="done")
        self.mutations.pause_task(self.task("t4", "s1"))

        change = self.mutations.pause_sprint(sprint)
        # Already paused tasks keep who paused them; finished ones are left alone.
        self.assertEqual(sorted(task.id for task in change.tasks), ["t1", "t2"])
        self.assertIsNone(self.fresh("t3").paused_at)
        (event,) = [e for e in self.store.list_sprint_events("s1") if e.event_type == "human.sprint_paused"]
        self.assertEqual(sorted(event.payload["task_ids"]), ["t1", "t2"])

        # A task can be resumed on its own while the rest stay paused.
        self.mutations.resume_task(self.fresh("t2"))
        self.assertIsNone(self.fresh("t2").paused_at)
        self.assertIsNotNone(self.fresh("t1").paused_at)

        # Resume on the sprint releases everything in it, one by one or not.
        resumed = self.mutations.resume_sprint(sprint)
        self.assertEqual(sorted(task.id for task in resumed.tasks), ["t1", "t4"])
        with self.assertRaisesRegex(MutationError, "Nothing in sprint"):
            self.mutations.resume_sprint(sprint)

    def test_a_sprint_stop_needs_a_running_step(self) -> None:
        sprint = self.sprint("s1")
        task = self.task("t1", "s1", status="in_progress", workflow_current_step="develop")
        with self.assertRaisesRegex(MutationError, "is running a step"):
            self.mutations.pause_sprint(sprint, mode="now")
        self.running(task)
        self.mutations.pause_sprint(sprint, mode="now")
        self.assertEqual(self.fresh("t1").pause_mode, "now")

    def test_block_needs_a_reason_and_unblock_leaves_pauses(self) -> None:
        sprint = self.sprint("s1")
        self.mutations.pause_task(self.task("t1", "s1"))
        self.task("t2", "s1")
        with self.assertRaisesRegex(MutationError, "reason"):
            self.mutations.block_sprint(sprint, "  ")
        self.mutations.block_sprint(sprint, "waiting for the design")
        with self.assertRaisesRegex(MutationError, "already blocked"):
            self.mutations.block_sprint(sprint, "again")
        held = task_hold(self.fresh("t2"), sprint_block=self.store.get_sprint_block("s1"))
        self.assertEqual((held.kind, held.scope, held.reason), ("block", "sprint", "waiting for the design"))

        self.mutations.unblock_sprint(sprint)
        self.assertIsNone(self.store.get_sprint_block("s1"))
        self.assertIsNotNone(self.fresh("t1").paused_at, "Unblock lifts only the block")

    def test_a_finished_or_cancelled_sprint_loses_its_block(self) -> None:
        for status in ("completed", "cancelled"):
            with self.subTest(status=status):
                sprint = self.sprint(f"s-{status}")
                self.mutations.block_sprint(sprint, "hold")
                self.mutations.transition_sprint(self.store.get_sprint(sprint.id), status)
                self.assertIsNone(self.store.get_sprint_block(sprint.id))

    def test_the_workspace_pauses_and_blocks_every_project(self) -> None:
        self.project("p2")
        self.sprint("s1")
        self.sprint("s2", project_id="p2")
        self.sprint("s3", status="planned", order=1)
        self.task("t1", "s1")
        self.task("t2", "s2", project_id="p2")
        self.task("t3", "s3")

        change = self.mutations.pause_all()
        self.assertEqual(sorted(task.id for task in change.tasks), ["t1", "t2", "t3"])
        self.assertEqual(sorted(task.id for task in self.mutations.resume_all().tasks), ["t1", "t2", "t3"])

        self.mutations.block_all("release freeze")
        self.assertEqual(self.store.get_workspace_block().reason, "release freeze")
        for project_id in ("p1", "p2"):
            kinds = [e.event_type for e in self.store.list_events(project_id=project_id)]
            self.assertIn("human.workspace_blocked", kinds)
        self.mutations.unblock_all()
        self.assertIsNone(self.store.get_workspace_block())

    def test_work_added_to_a_paused_sprint_joins_the_pause(self) -> None:
        sprint = self.sprint("s1")
        self.task("t1", "s1")
        self.mutations.pause_sprint(sprint)

        added = self.mutations.add_task(sprint, title="Later work")
        self.assertIsNotNone(self.fresh(added.id).paused_at)

        backlog = self.store.ensure_backlog("p1", created_at="2026-11-26T00:00:00Z")
        first = self.task("b1", backlog.id)
        second = self.task("b2", backlog.id)
        planned = self.mutations.plan_tasks([first, second], sprint=sprint)
        self.assertTrue(all(task.paused_at for task in planned.tasks))

    def test_work_added_to_a_sprint_that_is_not_all_paused_runs(self) -> None:
        sprint = self.sprint("s1")
        self.mutations.pause_task(self.task("t1", "s1"))
        self.task("t2", "s1")
        added = self.mutations.add_task(sprint, title="More work")
        self.assertIsNone(self.fresh(added.id).paused_at)

    def test_a_pause_survives_a_task_object_read_before_it(self) -> None:
        """The engine and stale objects never lift a pause (only Resume does)."""
        self.sprint("s1")
        stale = self.task("t1", "s1")
        self.mutations.pause_task(stale)
        stale.title = "Edited title"
        self.store.save_task(stale)
        self.assertIsNotNone(self.fresh("t1").paused_at)


class HoldEngineTests(OrchestratorTestCase):
    def _orchestrator(self, store: ForemanStore, runner: ScriptedNativeRunner) -> ForemanOrchestrator:
        return ForemanOrchestrator(
            store, roles=self.roles, workflows=self.workflows, agent_runners={"claude_code": runner}
        )

    def _second(self, store: ForemanStore, sprint: Sprint, *, status: str = "todo", **kw) -> Task:
        return store.save_task(
            Task(
                id="task-2", sprint_id=sprint.id, project_id=sprint.project_id, title="Second task",
                status=status, task_type="feature", priority=2, order_index=2, **kw,
            )
        )

    def _second_developer(self, config: AgentRunConfig):
        work_dir = Path(config.working_dir)
        self.write_text(work_dir / "second.txt", "second\n")
        self.write_text(work_dir / "ready.txt", "ready\n")
        self.commit_all(work_dir, "feat: second task")
        yield AgentEvent("agent.message", payload={"text": "Done.\n" + DEV_REPORT + "\nTASK_COMPLETE", "phase": "assistant"})
        yield AgentEvent("agent.completed", payload={"session_id": "dev-2"})

    def test_a_pause_lets_the_step_finish_and_holds_the_next(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        with ForemanStore(db_path) as store:
            store.initialize()
            project, _sprint, task = self.seed_project(store, repo_path=repo_path)

            def developer_then_paused(config: AgentRunConfig):
                # A user pauses while the developer works.
                with ForemanStore(db_path) as writer:
                    Mutations(writer, via="dashboard", actor="ana").pause_task(writer.get_task(task.id))
                yield from self._native_developer_success(config)

            runner = ScriptedNativeRunner({1: developer_then_paused})
            result = self._orchestrator(store, runner).run_project(project.id)

            held = store.get_task(task.id)
            # The develop step finished; the tests never started.
            self.assertEqual((held.status, held.workflow_current_step), ("in_progress", "test"))
            self.assertEqual(
                [(run.workflow_step, run.status) for run in store.list_runs(task_id=task.id)
                 if not run.role_id.startswith("_builtin:orchestrator")],
                [("develop", "completed")],
            )
            self.assertEqual(result.stop_reason, "held")
            self.assertIsNone(
                store.get_active_lease(project_id=project.id, resource_type="task", resource_id=task.id)
            )
            self.assertNotIn("test", held.step_visit_counts)

    def test_a_paused_task_does_not_hold_the_queue(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, first = self.seed_project(store, repo_path=repo_path)
            project.settings["merge_approval"] = "human"
            store.save_project(project)
            second = self._second(store, sprint)
            Mutations(store, via="cli", actor="ana").pause_task(first)

            runner = ScriptedNativeRunner(
                {1: self._second_developer, 2: lambda config: self._native_reviewer_approve(config)}
            )
            self._orchestrator(store, runner).run_project(project.id)

            # Only the audit of the pause hangs off the first task: no step ran.
            self.assertEqual(
                [run.workflow_step for run in store.list_runs(task_id=first.id)], ["pause"]
            )
            self.assertEqual(store.get_task(second.id).workflow_current_step, "merge_approval")

    def test_a_paused_task_waiting_for_a_decision_releases_the_queue(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, first = self.seed_project(store, repo_path=repo_path)
            first.status = "blocked"
            first.workflow_current_step = "merge_approval"
            store.save_task(first)
            second = self._second(store, sprint)
            Mutations(store, via="cli", actor="ana").pause_task(store.get_task(first.id))

            runner = ScriptedNativeRunner(
                {1: self._second_developer, 2: lambda config: self._native_reviewer_approve(config)}
            )
            result = self._orchestrator(store, runner).run_project(project.id)

            self.assertIn(second.id, result.executed_task_ids)

    def test_a_block_above_holds_everything_and_the_sprint_is_not_finished(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, task = self.seed_project(store, repo_path=repo_path)
            mutations = Mutations(store, via="cli", actor="ana")
            orchestrator = self._orchestrator(store, ScriptedNativeRunner({}))

            for block, lift in (
                (lambda: mutations.block_sprint(sprint, "design review"), lambda: mutations.unblock_sprint(sprint)),
                (lambda: mutations.block_all("freeze"), mutations.unblock_all),
            ):
                block()
                self.assertEqual(orchestrator.run_project(project.id).stop_reason, "held")
                self.assertEqual(store.list_runs(task_id=task.id), [])
                lift()

            # Every task done, Foreman finishes sprints: a block keeps it open.
            project.settings["sprint_completion"] = "auto"
            store.save_project(project)
            task = store.get_task(task.id)
            task.status = "done"
            store.save_task(task)
            mutations.block_sprint(sprint, "not yet")
            self.assertEqual(orchestrator.run_project(project.id).stop_reason, "held")
            self.assertEqual(store.get_sprint(sprint.id).status, "active")
            mutations.unblock_sprint(sprint)
            orchestrator.run_project(project.id)
            self.assertEqual(store.get_sprint(sprint.id).status, "completed")

    def test_a_blocked_next_sprint_is_not_started(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        with ForemanStore(db_path) as store:
            store.initialize()
            project, sprint, task = self.seed_project(store, repo_path=repo_path)
            project.settings["sprint_completion"] = "auto"
            store.save_project(project)
            task.status = "done"
            store.save_task(task)
            store.save_sprint(Sprint(id="sprint-2", project_id=project.id, title="Next", status="planned", order_index=2))
            Mutations(store, via="cli", actor="ana").block_sprint(store.get_sprint("sprint-2"), "wait for me")

            result = self._orchestrator(store, ScriptedNativeRunner({})).run_project(project.id)

            self.assertEqual(result.stop_reason, "held")
            self.assertEqual(store.get_sprint(sprint.id).status, "completed")
            self.assertEqual(store.get_sprint("sprint-2").status, "planned")

    def test_a_request_to_run_a_held_task_does_not_run_it(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        with ForemanStore(db_path) as store:
            store.initialize()
            project, _sprint, task = self.seed_project(store, repo_path=repo_path)
            Mutations(store, via="cli", actor="ana").pause_task(task)

            result = self._orchestrator(store, ScriptedNativeRunner({})).run_project(project.id, task_id=task.id)

            self.assertEqual((result.stop_reason, result.executed_task_ids), ("held", ()))
            self.assertIn("paused by ana", result.detail)

    def test_a_block_requested_during_a_step_is_applied_when_it_ends(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        with ForemanStore(db_path) as store:
            store.initialize()
            project, _sprint, task = self.seed_project(store, repo_path=repo_path)

            def developer_then_blocked(config: AgentRunConfig):
                with ForemanStore(db_path) as writer:
                    Mutations(writer, via="dashboard", actor="ana").block_task(
                        writer.get_task(task.id), "wrong approach"
                    )
                yield from self._native_developer_success(config)

            self._orchestrator(store, ScriptedNativeRunner({1: developer_then_blocked})).run_project(project.id)

            blocked = store.get_task(task.id)
            self.assertEqual((blocked.status, blocked.blocked_reason), ("blocked", "wrong approach"))
            self.assertIsNone(blocked.block_requested)
            self.assertIsNone(blocked.workflow_current_step)


class StopCutsTestsTests(unittest.TestCase):
    """A Stop reaches a running test command within seconds and kills it."""

    def test_an_interrupt_kills_the_test_command(self) -> None:
        class Stopped(BaseException):
            pass

        polls = {"count": 0}

        def interrupt_poll() -> None:
            polls["count"] += 1
            raise Stopped()

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        project = Project(
            id="p", name="p", repo_path=temp.name, workflow_id="development",
            settings={"test_command": "sleep 30", "test_timeout_seconds": 60},
        )
        started = time.monotonic()
        with unittest.mock.patch("foreman.engine.builtins.run_tests.INTERRUPT_POLL_SECONDS", 0.2):
            with self.assertRaises(Stopped):
                BuiltinExecutor()._run_tests(
                    project=project, working_dir=Path(temp.name), interrupt_poll=interrupt_poll
                )
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(polls["count"], 1)


if __name__ == "__main__":
    unittest.main()


class HoldsApiTests(_Store):
    """The holds routes: what the dashboard calls."""

    def setUp(self) -> None:
        super().setUp()
        from foreman.api.app import create_dashboard_app

        self.app = create_dashboard_app(str(self.store.db_path), auth_token=None)
        self.sprint("s1")
        self.task("t1", "s1")
        self.task("t2", "s1")

    def post(self, path: str, body: dict | None = None):
        import asyncio

        import httpx

        async def call():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.post(path, json=body or {})

        return asyncio.run(call())

    def test_the_routes_pause_resume_block_and_unblock(self) -> None:
        response = self.post("/api/v1/tasks/t1/pause", {"requested_by": "ana"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.fresh("t1").paused_by, "ana")

        response = self.post("/api/v1/sprints/s1/pause")
        self.assertEqual(response.json()["task_ids"], ["t2"])
        response = self.post("/api/v1/tasks/t2/resume")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.post("/api/v1/sprints/s1/resume").json()["task_ids"], ["t1"])

        response = self.post("/api/v1/sprints/s1/block", {"reason": "design review", "requested_by": "ana"})
        self.assertEqual(response.json()["block"]["reason"], "design review")
        self.assertEqual(self.post("/api/v1/sprints/s1/unblock").status_code, 200)

        self.assertEqual(self.post("/api/v1/workspace/block", {"reason": "freeze"}).status_code, 200)
        self.assertEqual(self.post("/api/v1/workspace/unblock").json()["unblocked"]["reason"], "freeze")
        self.assertEqual(self.post("/api/v1/workspace/pause").json()["mode"], "finish_step")
        self.assertEqual(sorted(self.post("/api/v1/workspace/resume").json()["task_ids"]), ["t1", "t2"])

    def test_refusals_are_400_with_the_reason(self) -> None:
        for path, body, words in (
            ("/api/v1/tasks/t1/resume", None, "not paused"),
            ("/api/v1/tasks/t1/stop", None, "Pause it instead"),
            ("/api/v1/sprints/s1/block", {"reason": ""}, "reason"),
            ("/api/v1/sprints/s1/unblock", None, "not blocked"),
            ("/api/v1/workspace/stop", None, "running a step"),
            ("/api/v1/tasks/t1/pause", {"mode": "later"}, "mode"),
        ):
            with self.subTest(path=path):
                response = self.post(path, body)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn(words, response.json()["error"])

    def test_a_task_and_its_sprint_say_what_holds_them(self) -> None:
        import asyncio

        import httpx

        self.post("/api/v1/tasks/t1/pause", {"requested_by": "ana"})
        self.post("/api/v1/sprints/s1/block", {"reason": "design review"})

        async def get(path):
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return (await client.get(path)).json()

        task = asyncio.run(get("/api/v1/tasks/t2"))
        self.assertEqual((task["hold"]["kind"], task["hold"]["scope"]), ("block", "sprint"))
        self.assertFalse(task["step_running"])
        sprint = asyncio.run(get("/api/v1/sprints/s1"))
        self.assertEqual(sprint["block"]["reason"], "design review")
        # The lifecycle stays `status`; what the work is doing is `work`.
        self.assertEqual((sprint["status"], sprint["work"]["state"]), ("active", "blocked"))
        listed = {item["id"]: item for item in asyncio.run(get("/api/v1/sprints/s1/tasks"))["tasks"]}
        self.assertEqual(listed["t1"]["hold"]["scope"], "sprint", "a block above is what is shown")


class StatusLineTests(_Store):
    """What a sprint's status line says (ADR-0043 §6)."""

    def status(self, sprint_id: str) -> dict:
        from foreman.services.work_status import sprint_work_status

        return sprint_work_status(self.store, self.store.get_sprint(sprint_id), resident=True)

    def test_the_first_true_state_is_said(self) -> None:
        sprint = self.sprint("s1")
        first = self.task("t1", "s1", status="in_progress", workflow_current_step="develop")
        self.task("t2", "s1")
        self.assertEqual(self.status("s1")["state"], "waiting")

        self.running(first)
        working = self.status("s1")
        self.assertEqual((working["state"], working["task_id"], working["step"]), ("working", "t1", "develop"))

        self.mutations.pause_task(self.fresh("t2"))
        self.assertEqual(self.status("s1")["paused"], 1)
        self.mutations.pause_task(self.fresh("t1"))
        self.assertEqual(self.status("s1")["state"], "pausing")
        self.mutations.pause_task(self.fresh("t1"), mode="now")
        self.assertEqual(self.status("s1")["state"], "stopping")

        self.store.save_run(
            Run(
                id="run-t1", task_id="t1", project_id="p1", role_id="developer",
                workflow_step="develop", agent_backend="claude_code", status="killed",
            )
        )
        stopped = self.status("s1")
        self.assertEqual((stopped["state"], stopped["paused"]), ("stopped", 2))

        self.mutations.block_sprint(sprint, "design review")
        blocked = self.status("s1")
        self.assertEqual((blocked["state"], blocked["scope"], blocked["reason"]), ("blocked", "sprint", "design review"))

    def test_no_worker_is_said_only_when_work_could_run(self) -> None:
        from foreman.services.work_status import sprint_work_status

        self.sprint("s1")
        self.task("t1", "s1")
        self.assertTrue(sprint_work_status(self.store, self.store.get_sprint("s1"))["no_worker"])
        self.mutations.pause_sprint(self.store.get_sprint("s1"))
        self.assertFalse(sprint_work_status(self.store, self.store.get_sprint("s1"))["no_worker"])

    def test_a_blocked_sprint_waits_for_a_user(self) -> None:
        from foreman.services.workspace import WorkspaceService

        sprint = self.sprint("s1")
        self.mutations.block_sprint(sprint, "design review")
        items = WorkspaceService(self.store).list_needs_you()["items"]
        (item,) = [entry for entry in items if entry["kind"] == "unblock_sprint"]
        self.assertEqual((item["sprint_id"], item["blocked"]["reason"]), ("s1", "design review"))


class HoldsCliTests(_Store):
    def run_cli(self, *args: str):
        import subprocess

        from test_cli import cli_argv, cli_env

        return subprocess.run(
            cli_argv(*args, "--db", str(self.store.db_path)),
            env=cli_env(), capture_output=True, text=True, check=False,
        )

    def test_pause_resume_block_and_unblock(self) -> None:
        self.sprint("s1")
        task = self.task("t1", "s1")

        result = self.run_cli("pause", "p1", "--task", task.id)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Paused:", result.stdout)
        self.assertIsNotNone(self.fresh("t1").paused_at)

        result = self.run_cli("resume", "p1", "--sprint", "s1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(self.fresh("t1").paused_at)

        result = self.run_cli("block", "--all", "--reason", "freeze")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.store.get_workspace_block().reason, "freeze")
        self.assertEqual(self.run_cli("unblock", "--all").returncode, 0)

        result = self.run_cli("pause", "p1", "--task", task.id, "--now")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Pause it instead", result.stderr)

        result = self.run_cli("pause", "p1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--task, --sprint or --all", result.stderr)


class CarriedOverTests(unittest.TestCase):
    """Migration 31 keeps a user's stop and pause from before holds existed."""

    def test_a_standing_engine_pause_and_a_stopped_task_become_pauses(self) -> None:
        from foreman.store import _SCHEMA_MIGRATIONS_DDL
        from foreman.store.migrations import MIGRATIONS

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = ForemanStore(Path(temp.name) / "foreman.db")
        self.addCleanup(store.close)
        store._connection.executescript(_SCHEMA_MIGRATIONS_DDL)
        store.migrate([m for m in MIGRATIONS if m[0] <= 30])
        connection = store._connection
        with connection:
            for project_id in ("stopped", "running"):
                connection.execute(
                    "INSERT INTO projects (id, name, repo_path, workflow_id, created_at, updated_at)"
                    " VALUES (?, ?, '/tmp', 'development', 'x', 'x')",
                    (project_id, project_id),
                )
                connection.execute(
                    "INSERT INTO sprints (id, project_id, title, status, order_index, created_at)"
                    " VALUES (?, ?, 'S', 'active', 0, 'x')",
                    (f"s-{project_id}", project_id),
                )
                for task_id, status, reason, step in (
                    (f"{project_id}-todo", "todo", None, None),
                    (f"{project_id}-done", "done", None, None),
                ):
                    connection.execute(
                        "INSERT INTO tasks (id, sprint_id, project_id, title, task_key, status,"
                        " task_type, created_by, created_at, blocked_reason, workflow_current_step)"
                        " VALUES (?, ?, ?, 'T', ?, ?, 'feature', 'human', 'x', ?, ?)",
                        (task_id, f"s-{project_id}", project_id, task_id, status, reason, step),
                    )
            connection.execute(
                "INSERT INTO tasks (id, sprint_id, project_id, title, task_key, status,"
                " task_type, created_by, created_at, blocked_reason, workflow_current_step)"
                " VALUES ('cut', 's-running', 'running', 'T', 'cut', 'blocked', 'feature', 'human',"
                " 'x', 'Stopped by dana', 'review')"
            )
            for project_id, command, at in (
                ("stopped", "resume", "2026-11-01T00:00:00Z"),
                ("stopped", "shutdown", "2026-11-02T00:00:00Z"),
                ("running", "pause", "2026-11-01T00:00:00Z"),
                ("running", "resume", "2026-11-02T00:00:00Z"),
            ):
                connection.execute(
                    "INSERT INTO engine_commands (id, project_id, command, requested_by, requested_at,"
                    " status, completed_at) VALUES (?, ?, ?, 'ana', ?, 'completed', ?)",
                    (f"{project_id}-{command}", project_id, command, at, at),
                )

        store.migrate(MIGRATIONS)

        stopped = store.get_task("stopped-todo")
        self.assertEqual((stopped.paused_by, stopped.pause_mode), ("ana", "finish_step"))
        self.assertIsNone(store.get_task("stopped-done").paused_at)
        self.assertIsNone(store.get_task("running-todo").paused_at)
        cut = store.get_task("cut")
        self.assertEqual(
            (cut.status, cut.blocked_reason, cut.paused_by, cut.pause_mode, cut.workflow_current_step),
            ("in_progress", None, "dana", "now", "review"),
        )
