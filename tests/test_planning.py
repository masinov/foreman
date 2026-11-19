"""Planning: a sprint's goal into tasks, a big task into smaller ones."""

from __future__ import annotations

import asyncio
import json

import httpx

from foreman.manager import agent as meta_agent
from foreman.dashboard.app import create_dashboard_app
from foreman.domain.models import Sprint
from foreman.manager.planning import (
    PlanningError,
    does_only_what_was_asked,
    planning_request,
    settle_plan,
)
from foreman.manager.proposals import MANAGER_TURN_ENV, ProposalError, Proposals

from test_proposals import ProposalCase


def add(title: str, *, sprint: str = "s2", **fields: object) -> dict:
    return {"kind": "add_task", "sprint_id": sprint, "title": title, **fields}


class AddTaskTests(ProposalCase):
    def test_tasks_are_added_to_the_sprint_ready_to_run_and_wait_for_each_other_by_name(self) -> None:
        proposal = self.propose(
            add("Schema", ref="schema", complexity="small", acceptance_criteria="The table exists."),
            add("API", ref="api", waits_for=["schema"]),
            add("Page", waits_for=["api", "schema"]),
        )

        confirmed = Proposals(self.store, via="dashboard", actor="ada").confirm(proposal.id)

        self.assertEqual(confirmed.state, "confirmed", confirmed.outcome)
        tasks = {task.title: task for task in self.store.list_tasks(sprint_id="s2")}
        self.assertEqual(set(tasks), {"Schema", "API", "Page"})
        self.assertEqual({task.status for task in tasks.values()}, {"todo"})
        self.assertEqual(tasks["Schema"].complexity, "small")
        self.assertEqual(tasks["Schema"].acceptance_criteria, "The table exists.")
        self.assertEqual(tasks["API"].depends_on_task_ids, [tasks["Schema"].id])
        self.assertEqual(set(tasks["Page"].depends_on_task_ids), {tasks["API"].id, tasks["Schema"].id})

    def test_nothing_is_stored_until_a_person_confirms(self) -> None:
        self.propose(add("Schema"))

        self.assertEqual(self.store.list_tasks(sprint_id="s2"), [])

    def test_a_task_may_wait_for_one_that_already_exists(self) -> None:
        self.task("old", "todo", sprint="s2")
        proposal = self.propose(add("New", waits_for=["old"]))

        Proposals(self.store, via="dashboard").confirm(proposal.id)

        new = next(task for task in self.store.list_tasks(sprint_id="s2") if task.title == "New")
        self.assertEqual(new.depends_on_task_ids, ["old"])

    def test_two_tasks_with_one_name_are_refused(self) -> None:
        with self.assertRaisesRegex(ProposalError, "two things in this proposal are called 'a'"):
            self.propose(add("One", ref="a"), add("Two", ref="a"))

    def test_waiting_for_a_name_nothing_has_is_refused(self) -> None:
        with self.assertRaises(ProposalError):
            self.propose(add("One", waits_for=["nobody"]))

    def test_a_finished_sprint_takes_no_tasks(self) -> None:
        self.store.save_sprint(Sprint(id="old", project_id="p1", title="Old", status="completed"))

        with self.assertRaises(ProposalError):
            self.propose(add("One", sprint="old"))


class RequestTests(ProposalCase):
    def goal(self, sprint_id: str = "s2", goal: str = "People can sign in.") -> None:
        sprint = self.store.get_sprint(sprint_id)
        sprint.goal = goal
        self.store.save_sprint(sprint)

    def test_a_sprint_is_planned_from_its_goal(self) -> None:
        self.goal()
        self.task("kept", "todo", sprint="s2")
        self.task("gone", "cancelled", sprint="s2")

        request = planning_request(self.store, self.project, {"kind": "plan_sprint", "sprint_id": "s2"})

        self.assertEqual(request.says, "Plan this sprint: Sprint 2")
        self.assertIn("Its goal: People can sign in.", request.instructions)
        self.assertIn("only `add_task` with\nsprint_id s2", request.instructions)
        self.assertIn("- kept: KEPT (todo)", request.instructions)
        self.assertNotIn("gone", request.instructions)

    def test_a_sprint_with_no_goal_is_not_planned(self) -> None:
        with self.assertRaisesRegex(PlanningError, "has no goal"):
            planning_request(self.store, self.project, {"kind": "plan_sprint", "sprint_id": "s2"})

    def test_a_finished_sprint_or_another_projects_is_not_planned(self) -> None:
        self.store.save_sprint(Sprint(id="old", project_id="p1", title="Old", status="completed", goal="G"))

        with self.assertRaisesRegex(PlanningError, "is completed"):
            planning_request(self.store, self.project, {"kind": "plan_sprint", "sprint_id": "old"})
        with self.assertRaisesRegex(PlanningError, "no such sprint"):
            planning_request(self.store, self.project, {"kind": "plan_sprint", "sprint_id": "x1"})

    def test_a_task_in_a_sprint_is_split_into_tasks_of_that_sprint(self) -> None:
        self.task("big", "todo", sprint="s2")

        request = planning_request(self.store, self.project, {"kind": "split_task", "task_id": "big"})

        self.assertEqual(request.says, "Split this task: BIG")
        self.assertIn("`add_task` with sprint_id s2", request.instructions)
        self.assertIn("then `cancel_task` with task_id big", request.instructions)

    def test_a_task_in_the_backlog_is_split_into_backlog_tasks(self) -> None:
        filed = self.file("Big", accept=True)

        request = planning_request(self.store, self.project, {"kind": "split_task", "task_id": filed.id})

        self.assertIn("`file_task` with accept true", request.instructions)

    def test_a_task_that_has_started_is_not_split(self) -> None:
        self.task("busy", "in_progress")

        with self.assertRaisesRegex(PlanningError, "is in_progress"):
            planning_request(self.store, self.project, {"kind": "split_task", "task_id": "busy"})

    def test_anything_else_is_not_a_planning_request(self) -> None:
        with self.assertRaisesRegex(PlanningError, "plan_sprint.*split_task"):
            planning_request(self.store, self.project, {"kind": "rewrite_everything"})


class SettleTests(ProposalCase):
    def setUp(self) -> None:
        super().setUp()
        sprint = self.store.get_sprint("s2")
        sprint.goal = "People can sign in."
        self.store.save_sprint(sprint)
        self.request = planning_request(self.store, self.project, {"kind": "plan_sprint", "sprint_id": "s2"})

    def foreman_approves_plans(self) -> None:
        self.project.settings = {**(self.project.settings or {}), "plan_approval": "auto"}
        self.store.save_project(self.project)

    def proposed(self, *operations, turn: str = "turn-1"):
        return self.proposals.create(
            self.project, reason="Because.", operations=list(operations), proposed_by="manager", turn_id=turn
        )

    def test_a_person_approves_plans_unless_the_project_says_otherwise(self) -> None:
        proposal = self.proposed(add("Schema"))

        self.assertEqual(settle_plan(self.store, self.project, self.request, "turn-1"), [])
        self.assertEqual(self.store.get_proposal(proposal.id).state, "proposed")

    def test_foreman_confirms_the_plan_when_the_project_lets_it(self) -> None:
        self.foreman_approves_plans()
        proposal = self.proposed(add("Schema"), add("API"))

        self.assertEqual(settle_plan(self.store, self.project, self.request, "turn-1"), [proposal.id])

        stored = self.store.get_proposal(proposal.id)
        self.assertEqual((stored.state, stored.decided_by, stored.outcome["via"]), ("confirmed", "foreman", "policy"))
        self.assertEqual(len(self.store.list_tasks(sprint_id="s2")), 2)

    def test_foreman_does_not_confirm_a_proposal_that_does_anything_else(self) -> None:
        self.foreman_approves_plans()
        self.task("other", "todo")
        strays = [
            self.proposed(add("Schema"), {"kind": "cancel_task", "task_id": "other"}),
            self.proposed(add("Elsewhere", sprint="s1")),
            self.proposed({"kind": "edit_sprint", "sprint_id": "s2", "goal": "Something easier."}),
        ]

        self.assertEqual(settle_plan(self.store, self.project, self.request, "turn-1"), [])
        self.assertEqual({self.store.get_proposal(p.id).state for p in strays}, {"proposed"})

    def test_only_the_proposals_of_this_turn_are_settled(self) -> None:
        self.foreman_approves_plans()
        earlier = self.proposed(add("Schema"), turn="turn-0")

        self.assertEqual(settle_plan(self.store, self.project, self.request, "turn-1"), [])
        self.assertEqual(self.store.get_proposal(earlier.id).state, "proposed")

    def test_a_split_is_the_pieces_and_then_the_task_cancelled(self) -> None:
        self.task("big", "todo", sprint="s2")
        self.task("other", "todo", sprint="s2")
        request = planning_request(self.store, self.project, {"kind": "split_task", "task_id": "big"})
        cancel = {"kind": "cancel_task", "task_id": "big"}

        good = self.proposed(add("One"), add("Two"), cancel)
        one_piece = self.proposed(add("One"), cancel)
        wrong_task = self.proposed(add("One"), add("Two"), {"kind": "cancel_task", "task_id": "other"})
        no_cancel = self.proposed(add("One"), add("Two"))
        other_sprint = self.proposed(add("One", sprint="s1"), add("Two"), cancel)

        self.assertTrue(does_only_what_was_asked(request, good, self.store))
        for proposal in (one_piece, wrong_task, no_cancel, other_sprint):
            self.assertFalse(does_only_what_was_asked(request, proposal, self.store))


class TurnTests(ProposalCase):
    """A planning request through the API: one manager turn, with a faked agent."""

    def setUp(self) -> None:
        super().setUp()
        sprint = self.store.get_sprint("s2")
        sprint.goal = "People can sign in."
        self.store.save_sprint(sprint)
        self._which = meta_agent.shutil.which
        meta_agent.shutil.which = lambda _exe: "/usr/bin/claude"
        self.addCleanup(lambda: setattr(meta_agent.shutil, "which", self._which))
        self._run = meta_agent._run_claude
        self.addCleanup(lambda: setattr(meta_agent, "_run_claude", self._run))
        self.prompts: list[str] = []

    def manager_proposes(self, *operations) -> None:
        test = self

        async def fake(session_id, prompt, *, repo_path, executable, model, env=None):
            test.prompts.append(prompt)
            yield {"type": "text_delta", "text": "Here is the plan."}
            if operations:
                Proposals(test.store, via="cli").create(
                    test.project,
                    reason="These reach the goal.",
                    operations=list(operations),
                    proposed_by="manager",
                    turn_id=env[MANAGER_TURN_ENV],
                )

        meta_agent._run_claude = fake

    def post(self, body: dict):
        async def send():
            app = create_dashboard_app(self.db_path)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                return await client.post("/api/v1/projects/p1/meta/message", json=body)

        return asyncio.run(send())

    def lines(self, response) -> list[dict]:
        return [json.loads(line) for line in response.text.splitlines() if line.strip()]

    def test_the_manager_is_told_how_to_plan_and_the_person_sees_what_they_asked(self) -> None:
        self.manager_proposes(add("Schema"))

        response = self.post({"plan": {"kind": "plan_sprint", "sprint_id": "s2"}})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Plan sprint s2 (Sprint 2).", self.prompts[0])
        self.assertIn("one coherent change", self.prompts[0])
        turns = self.store.list_meta_turns("p1")[0]
        asked = next(turn for turn in turns if turn["role"] == "user")
        self.assertEqual((asked["text"], asked["origin"]), ("Plan this sprint: Sprint 2", "plan"))
        proposals = [line for line in self.lines(response) if line["type"] == "proposal"]
        self.assertEqual(len(proposals), 1)
        # A person approves plans here: nothing is in the sprint yet.
        self.assertEqual(self.store.list_tasks(sprint_id="s2"), [])

    def test_with_foreman_approving_plans_the_tasks_are_in_the_sprint_when_the_turn_ends(self) -> None:
        self.project.settings = {**(self.project.settings or {}), "plan_approval": "auto"}
        self.store.save_project(self.project)
        self.manager_proposes(add("Schema", ref="s"), add("API", waits_for=["s"]))

        response = self.post({"plan": {"kind": "plan_sprint", "sprint_id": "s2"}})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual({task.title for task in self.store.list_tasks(sprint_id="s2")}, {"Schema", "API"})
        settled = [line for line in self.lines(response) if line.get("settled")]
        self.assertEqual(len(settled), 1)

    def test_a_request_that_cannot_be_planned_is_refused_before_a_turn_starts(self) -> None:
        self.manager_proposes()

        response = self.post({"plan": {"kind": "plan_sprint", "sprint_id": "s1"}})

        self.assertEqual(response.status_code, 400)
        self.assertIn("has no goal", response.text)
        self.assertEqual(self.prompts, [])
        self.assertEqual(self.store.list_meta_turns("p1")[0], [])

    def test_an_ordinary_message_is_unchanged(self) -> None:
        self.manager_proposes()

        response = self.post({"message": "What is next?"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.prompts[0].rstrip().endswith("What is next?"))
        asked = next(turn for turn in self.store.list_meta_turns("p1")[0] if turn["role"] == "user")
        self.assertEqual(asked["origin"], "chat")


class RemovedWorkflowTests(ProposalCase):
    """Migration 26: a project that was on the architect workflow."""

    def migrate(self) -> None:
        from foreman.store.migrations import MIGRATIONS

        version, _, sql = next(m for m in MIGRATIONS if m[0] == 26)
        self.store._connection.executescript(sql)

    def on_removed_workflow(self) -> None:
        # Written the way an older Foreman left it: the id is no longer known.
        self.store._connection.execute(
            "UPDATE projects SET workflow_id = 'development_with_architect' WHERE id = 'p1'"
        )
        self.store._connection.commit()

    def test_the_project_goes_to_the_standard_workflow(self) -> None:
        self.on_removed_workflow()

        self.migrate()

        self.assertEqual(self.store.get_project("p1").workflow_id, "development")
        self.assertEqual(self.store.get_project("p2").workflow_id, "development")

    def test_a_task_waiting_at_the_plan_gate_goes_back_to_the_queue(self) -> None:
        self.on_removed_workflow()
        self.task("gated", "blocked", blocked_reason="Awaiting human approval", workflow_current_step="human_approval")
        self.task("later", "blocked", blocked_reason="Awaiting human approval", workflow_current_step="merge_approval")

        self.migrate()

        gated, later = self.store.get_task("gated"), self.store.get_task("later")
        self.assertEqual((gated.status, gated.workflow_current_step, gated.blocked_reason), ("todo", None, None))
        self.assertEqual((later.status, later.workflow_current_step), ("blocked", "merge_approval"))

    def test_a_project_that_keeps_its_own_copy_is_left_alone(self) -> None:
        from plan_workflow import install_plan_workflow

        install_plan_workflow(self.store, "p1")
        self.on_removed_workflow()

        self.migrate()

        self.assertEqual(self.store.get_project("p1").workflow_id, "development_with_architect")
