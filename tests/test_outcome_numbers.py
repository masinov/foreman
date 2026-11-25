"""Outcome numbers (ADR-0034): the computation, the store read, the CLI and the API."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from foreman.api.app import create_dashboard_app
from foreman.cli.parser import main
from foreman.domain.models import Event, Project, Run, Sprint, Task, TokenUsage
from foreman.domain.outcome_numbers import outcome_numbers
from foreman.services import Services
from foreman.services.errors import NotFoundError
from foreman.store import ForemanStore


class Story:
    """Builds one task's runs and events in time order."""

    def __init__(self, task_id: str, *, status: str = "done", sprint_id: str = "s1") -> None:
        self.task = Task(id=task_id, sprint_id=sprint_id, project_id="p1", title=task_id, status=status)
        self.runs: list[Run] = []
        self.events: list[Event] = []
        self._minute = 0

    def _at(self) -> str:
        self._minute += 1
        return f"2026-11-19T10:{self._minute:02d}:00+00:00"

    def event(self, event_type: str, *, role: str | None = None, run_id: str = "", **payload) -> Story:
        self.events.append(
            Event(
                id=f"{self.task.id}-e{len(self.events)}",
                run_id=run_id,
                task_id=self.task.id,
                project_id="p1",
                event_type=event_type,
                timestamp=self._at(),
                role_id=role,
                payload=payload,
            )
        )
        return self

    def run(
        self,
        step: str,
        role: str,
        *,
        model: str | None = "sonnet",
        backend: str = "claude_code",
        status: str = "completed",
        outcome: str = "done",
        cost: float = 0.0,
        output_tokens: int = 0,
    ) -> str:
        run_id = f"{self.task.id}-r{len(self.runs)}"
        started = self._at()
        self.runs.append(
            Run(
                id=run_id,
                task_id=self.task.id,
                project_id="p1",
                role_id=role,
                workflow_step=step,
                agent_backend=backend,
                status=status,
                outcome=outcome,
                model=model,
                cost_usd=cost,
                token_usage=TokenUsage(output=output_tokens),
                duration_ms=60_000,
                started_at=started,
                created_at=started,
            )
        )
        return run_id

    def step(self, step: str) -> Story:
        return self.event("workflow.step_started", step=step)

    def develop(self, *, model: str = "sonnet", cost: float = 1.0) -> Story:
        self.step("develop")
        run_id = self.run("develop", "developer", model=model, cost=cost, output_tokens=100)
        return self.event("workflow.transition", role="developer", run_id=run_id,
                          from_step="develop", to_step="test", trigger="completion:done")

    def tests(self, *, passed: bool = True) -> Story:
        self.step("test")
        to = "review" if passed else "develop"
        return self.event("workflow.transition", role="_builtin:run_tests",
                          from_step="test", to_step=to,
                          trigger="completion:success" if passed else "completion:failure")

    def review(self, *, approve: bool = True, model: str = "sonnet", cost: float = 0.5) -> Story:
        self.step("review")
        run_id = self.run("review", "code_reviewer", model=model, cost=cost,
                          outcome="approve" if approve else "steer")
        return self.event("workflow.transition", role="code_reviewer", run_id=run_id,
                          from_step="review", to_step="merge_approval" if approve else "develop",
                          trigger="completion:approve" if approve else "completion:steer")

    def gate(self, *, approve: bool = True) -> Story:
        self.step("merge_approval")
        self.event("workflow.paused", role="_builtin:human_gate", reason="human_gate",
                   step="merge_approval")
        self.event("workflow.resumed", role="_builtin:human_gate",
                   decision="approve" if approve else "deny", step="merge_approval")
        return self.event("workflow.transition", role="_builtin:human_gate",
                          from_step="merge_approval", to_step="merge" if approve else "develop",
                          trigger="completion:approve" if approve else "completion:deny")

    def merge(self, *, conflict: bool = False) -> Story:
        self.step("merge")
        if conflict:
            return self.event("workflow.transition", role="_builtin:merge",
                              from_step="merge", to_step="develop", trigger="completion:conflict")
        return self.event("engine.merge", role="_builtin:merge", sha="abc")

    def through(self) -> Story:
        """Develop, test, review, approve and merge, once."""
        return self.develop().tests().review().gate().merge()


def compute(*stories: Story):
    return outcome_numbers(
        [s.task for s in stories],
        [r for s in stories for r in s.runs],
        [e for s in stories for e in s.events],
    )


class OutcomeNumbersTests(unittest.TestCase):
    def test_a_task_merged_with_nothing_sent_back_passed_first_time(self) -> None:
        numbers = compute(Story("t1").through())

        self.assertEqual(numbers.tasks.started, 1)
        self.assertEqual(numbers.tasks.merged, 1)
        self.assertEqual(numbers.tasks.passed_first_time, 1)
        self.assertEqual(sum(numbers.send_backs.values()), 0)
        self.assertEqual(numbers.cost.total_usd, 1.5)
        self.assertEqual(numbers.cost.per_merged_task_usd, 1.5)
        self.assertEqual(numbers.cost.tokens_per_merged_task.output, 100)
        self.assertIsNotNone(numbers.median_minutes_to_merge)

    def test_each_send_back_is_counted_by_what_sent_it(self) -> None:
        reviewed = Story("review").develop().tests().review(approve=False, model="opus").through()
        tested = Story("tests").develop().tests(passed=False).through()
        person = Story("person").develop().tests().review().gate(approve=False).through()
        conflict = Story("conflict").develop().tests().review().gate().merge(conflict=True).through()

        numbers = compute(reviewed, tested, person, conflict)

        self.assertEqual(
            numbers.send_backs,
            {"tests": 1, "review": 1, "person": 1, "merge_conflict": 1, "other": 0},
        )
        self.assertEqual(numbers.send_backs_by_reviewer, {"code_reviewer": 1})
        self.assertEqual(numbers.tasks.merged, 4)
        self.assertEqual(numbers.tasks.passed_first_time, 0)
        # A conflict is usually caused by other work, so it is also left aside.
        self.assertEqual(numbers.tasks.passed_first_time_conflicts_aside, 1)
        reviewer_rows = {
            (row.role, row.model): row.send_backs_caused for row in numbers.by_role_and_model
            if row.role == "code_reviewer"
        }
        self.assertEqual(reviewer_rows, {("code_reviewer", "opus"): 1, ("code_reviewer", "sonnet"): 0})

    def test_a_task_never_started_is_not_counted_and_unmerged_ends_are_told_apart(self) -> None:
        filed = Story("filed", status="todo")
        by_hand = Story("by-hand").develop().event("human.task_completed")
        cancelled = Story("cancelled", status="cancelled").develop().event("human.task_cancelled")
        running = Story("running", status="in_progress").develop()

        numbers = compute(filed, by_hand, cancelled, running)

        self.assertEqual(numbers.tasks.started, 3)
        self.assertEqual(numbers.tasks.merged, 0)
        self.assertEqual(numbers.tasks.closed_by_hand, 1)
        self.assertEqual(numbers.tasks.cancelled, 1)
        self.assertEqual(numbers.tasks.not_finished, 1)
        self.assertIsNone(numbers.cost.per_merged_task_usd)
        self.assertEqual(numbers.cost.not_merged_usd, 3.0)

    def test_a_person_asked_is_told_apart_from_a_person_stepping_in(self) -> None:
        story = (
            Story("t1")
            .event("human.task_planned")
            .event("human.task_accepted")
            .develop()
            .event("human.message", text="Use the existing helper.")
            .tests()
            .review()
            .gate()
            .merge()
        )
        waiting = Story("t2", status="blocked").develop().tests().review()
        waiting.step("merge_approval").event(
            "workflow.paused", role="_builtin:human_gate", reason="human_gate"
        )

        numbers = compute(story, waiting)

        self.assertEqual(numbers.people.decisions_asked, 2)
        self.assertEqual(numbers.people.decisions_waiting, 1)
        self.assertEqual(numbers.people.median_wait_seconds, 60.0)
        # Planning and accepting happened before the task started: not stepping in.
        self.assertEqual(numbers.people.interventions, 1)
        self.assertEqual(numbers.people.interventions_by_kind, {"message": 1})

    def test_a_task_closed_at_a_gate_is_not_waiting(self) -> None:
        # FOR-49: paused at merge approval, then merged by hand and closed.
        closed = Story("t1", status="done").develop().tests().review()
        closed.step("merge_approval").event(
            "workflow.paused", role="_builtin:human_gate", reason="human_gate"
        )
        cancelled = Story("t2", status="cancelled").develop().tests().review()
        cancelled.step("merge_approval").event(
            "workflow.paused", role="_builtin:human_gate", reason="human_gate"
        )

        numbers = compute(closed, cancelled)

        self.assertEqual(numbers.people.decisions_asked, 2)
        self.assertEqual(numbers.people.decisions_waiting, 0)
        self.assertIsNone(numbers.people.median_wait_seconds)

    def test_a_merged_task_is_credited_to_the_model_of_its_first_build(self) -> None:
        first = Story("t1").develop(model="haiku").tests(passed=False).through()
        second = Story("t2").develop(model="sonnet").tests().review().gate().merge()
        engine_records = Story("t3").through()
        engine_records.run("file", "human", model=None, backend="cli")

        numbers = compute(first, second, engine_records)

        rows = {(row.role, row.model): row for row in numbers.by_role_and_model}
        self.assertEqual(rows[("developer", "haiku")].tasks_built_merged, 1)
        self.assertEqual(rows[("developer", "haiku")].tasks_built_passed_first_time, 0)
        self.assertEqual(rows[("developer", "sonnet")].tasks_built_merged, 2)
        self.assertEqual(rows[("developer", "sonnet")].tasks_built_passed_first_time, 2)
        # Only agents' runs are grouped: a person's filing record is not one.
        self.assertNotIn(("human", None), rows)

    def test_reads_before_the_first_edit_are_a_median_per_role_and_model(self) -> None:
        story = Story("t1").through()
        # Developer runs: 3 and 9 reads before an edit, one with no edit; the reviewer changed nothing.
        story.event("engine.step_reads", run_id=story.runs[0].id, reads=3, edited=True)
        second = story.run("develop", "developer", model="sonnet")
        story.event("engine.step_reads", run_id=second, reads=9, edited=True)
        third = story.run("develop", "developer", model="sonnet")
        story.event("engine.step_reads", run_id=third, reads=5, edited=False)
        story.event("engine.step_reads", run_id=story.runs[1].id, reads=4, edited=False)

        rows = {(row.role, row.model): row for row in compute(story).by_role_and_model}

        developer = rows[("developer", "sonnet")]
        self.assertEqual(developer.median_reads_before_first_edit, 6.0)
        self.assertEqual((developer.runs_with_reads, developer.runs_without_edit), (3, 1))
        reviewer = rows[("code_reviewer", "sonnet")]
        self.assertIsNone(reviewer.median_reads_before_first_edit)
        self.assertEqual((reviewer.runs_with_reads, reviewer.runs_without_edit), (1, 1))

    def test_failed_runs_are_counted_for_their_role_and_model(self) -> None:
        story = Story("t1", status="in_progress")
        story.step("develop")
        story.run("develop", "developer", model=None, status="killed", outcome="error")
        story.run("develop", "developer", model="sonnet", status="failed", outcome="error")

        rows = {(row.role, row.model): row for row in compute(story).by_role_and_model}

        self.assertEqual(rows[("developer", None)].failed_runs, 1)
        self.assertEqual(rows[("developer", "sonnet")].failed_runs, 1)


class OutcomeSurfacesTests(unittest.TestCase):
    """The store read, the service, `foreman outcomes` and the API answer the same."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = str(Path(self._temp.name) / "foreman.db")
        with ForemanStore(self.db_path) as store:
            store.initialize()
            store.save_project(
                Project(id="p1", name="Demo", repo_path=self._temp.name, workflow_id="development")
            )
            store.save_sprint(Sprint(id="s1", project_id="p1", title="First", status="active"))
            store.save_sprint(Sprint(id="s2", project_id="p1", title="Second", status="planned"))
            in_first = Story("t1").develop().tests(passed=False).through()
            in_second = Story("t2", sprint_id="s2").through()
            for story in (in_first, in_second):
                # Every event belongs to a run; the engine's own steps have one too.
                engine_run = story.run("orchestrator", "_builtin:orchestrator", model=None,
                                       backend="builtin", outcome="success")
                store.save_task(story.task)
                for run in story.runs:
                    store.save_run(run)
                for event in story.events:
                    event.run_id = event.run_id or engine_run
                    store.save_event(event)
                for run in story.runs:
                    if run.role_id == "developer":
                        store.save_event(
                            Event(id=f"{run.id}-reads", run_id=run.id, task_id=story.task.id,
                                  project_id="p1", event_type="engine.step_reads",
                                  payload={"reads": 7, "edited": True})
                        )
                # Raw output is not an outcome event and is never read for one.
                store.save_event(
                    Event(id=f"{story.task.id}-raw", run_id=engine_run, task_id=story.task.id,
                          project_id="p1", event_type="agent.raw_output", payload={"line": "x"})
                )

    def test_the_store_reads_only_the_outcome_events_of_the_scope(self) -> None:
        with ForemanStore(self.db_path) as store:
            tasks, runs, events = store.outcome_records("p1", sprint_id="s1")

        self.assertEqual([task.id for task in tasks], ["t1"])
        self.assertTrue(runs)
        self.assertEqual({run.task_id for run in runs}, {"t1"})
        self.assertNotIn("agent.raw_output", {event.event_type for event in events})

    def test_the_service_scopes_to_a_sprint_and_refuses_one_of_another_project(self) -> None:
        with ForemanStore(self.db_path) as store:
            store.save_project(Project(id="p2", name="Other", repo_path=self._temp.name, workflow_id="development"))
            store.save_sprint(Sprint(id="s9", project_id="p2", title="Elsewhere"))
            api = Services(store)
            whole = api.outcomes.numbers("p1")
            first = api.outcomes.numbers("p1", sprint_id="s1")
            with self.assertRaises(NotFoundError):
                api.outcomes.numbers("p1", sprint_id="s9")
            with self.assertRaises(NotFoundError):
                api.outcomes.numbers("nope")

        self.assertEqual(whole["tasks"]["merged"], 2)
        self.assertEqual(whole["tasks"]["passed_first_time"], 1)
        self.assertEqual(first["sprint_title"], "First")
        self.assertEqual(first["tasks"]["merged"], 1)
        self.assertEqual(first["send_backs"]["tests"], 1)

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([*argv, "--db", self.db_path])
        return code, out.getvalue(), err.getvalue()

    def test_the_command_prints_lines_and_json(self) -> None:
        code, text, _ = self.run_cli("outcomes", "p1")
        self.assertEqual(code, 0)
        self.assertIn("Passed first time: 1 of 2 merged (50%)", text)
        self.assertIn("Send-backs: 1: tests 1", text)
        self.assertIn("developer | sonnet", text)
        self.assertIn("reads before first edit: median 7", text)
        self.assertIn("reads before first edit: -", text)

        code, raw, _ = self.run_cli("outcomes", "p1", "--sprint", "s2", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(raw)
        self.assertEqual(payload["sprint_id"], "s2")
        self.assertEqual(payload["tasks"]["passed_first_time"], 1)

        code, _, err = self.run_cli("outcomes", "nope")
        self.assertEqual(code, 1)
        self.assertIn("Unknown project", err)

    def test_the_api_route_answers_with_the_same_numbers(self) -> None:
        app = create_dashboard_app(self.db_path, auth_token=None)

        async def call():
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return (
                    await client.get("/api/v1/projects/p1/outcomes"),
                    await client.get("/api/v1/projects/p1/outcomes?sprint=s1"),
                    await client.get("/api/v1/projects/p1/outcomes?sprint=nope"),
                )

        whole, first, missing = asyncio.run(call())

        self.assertEqual(whole.status_code, 200)
        self.assertEqual(whole.json()["tasks"]["merged"], 2)
        self.assertEqual(first.json()["tasks"]["merged"], 1)
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()


class OutcomeTimesTests(unittest.TestCase):
    """The store writes timestamps ending in ``Z``; Python 3.10 must read them too."""

    def test_times_ending_in_z_are_read(self) -> None:
        from foreman.domain.outcome_numbers import outcome_numbers

        task = Task(id="t", project_id="p", sprint_id="s", title="T", status="done")

        def event(eid: str, kind: str, stamp: str, **payload) -> Event:
            return Event(id=eid, run_id="r", task_id="t", project_id="p", event_type=kind,
                         timestamp=stamp, role_id=None, payload=payload)

        numbers = outcome_numbers([task], [], [
            event("e1", "workflow.step_started", "2026-11-20T17:00:00.000001Z", step="develop"),
            event("e2", "engine.merge", "2026-11-20T17:15:00Z"),
        ])
        self.assertEqual(numbers.median_minutes_to_merge, 15.0)
