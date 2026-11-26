"""A review's cited commands are checked through the whole engine, retries included (review of sprint 66)."""

from __future__ import annotations

import json

from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.runner.base import AgentEvent
from foreman.store import ForemanStore

from engine_support import SEEDED_CRITERIA, OrchestratorTestCase, ScriptedNativeRunner
from test_step_records import GOOD_REPORT, fenced, native_developer

SUITE = "./venv/bin/python -m pytest tests -q"


def verdict(ran: list[str]) -> dict:
    return {
        "criteria": [{
            "criterion": SEEDED_CRITERIA, "status": "verified", "evidence": "ran the suite",
            "ran": ran, "read": [], "from_report": False,
        }],
        "findings": [],
    }


class ReviewBasisThroughTheEngineTests(OrchestratorTestCase):
    def run_flow(self, *reviews: tuple[list[str], dict]):
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()
        project, _, task = self.seed_project(store, repo_path=repo_path)

        def work(tree):
            self.write_text(tree / "feature.txt", "x\n")
            self.write_text(tree / "ready.txt", "ready\n")
            self.commit_all(tree, "feat: x")

        def review(commands, record):
            def handler(config):
                events = [AgentEvent("agent.command", payload={"command": c, "cwd": "/w"}) for c in commands]
                events.append(AgentEvent("agent.message", payload={
                    "text": "```foreman-record\n" + json.dumps(record) + "\n```\nAPPROVE", "phase": "result"}))
                # One session for every attempt: a retry resumes it.
                events.append(AgentEvent("agent.completed", payload={"session_id": "review-session"}))
                return tuple(events)
            return handler

        handlers = {1: native_developer(f"Did it.\n{fenced(GOOD_REPORT)}\nTASK_COMPLETE", work=work)}
        for index, (commands, record) in enumerate(reviews, start=2):
            handlers[index] = review(commands, record)
        runner = ScriptedNativeRunner(handlers)
        ForemanOrchestrator(
            store, roles=self.roles, workflows=self.workflows, agent_runners={"claude_code": runner}
        ).run_project(project.id)
        reviews_run = [r for r in store.list_runs(task_id=task.id) if r.role_id == "code_reviewer"]
        return store.get_task(task.id), reviews_run

    def test_a_made_up_command_is_refused_on_the_retry_too(self) -> None:
        task, reviews = self.run_flow(([], verdict([SUITE])), ([], verdict([SUITE])))
        self.assertNotEqual(task.status, "done")
        self.assertEqual([r.outcome for r in reviews][:2], ["error", "error"])
        self.assertIn("which the review did not run", reviews[1].outcome_detail or "")

    def test_a_command_that_only_mentions_the_cited_one_does_not_count(self) -> None:
        task, reviews = self.run_flow(
            ([f"grep -rn '{SUITE}' docs/"], verdict([SUITE])), ([], verdict([SUITE]))
        )
        self.assertNotEqual(task.status, "done")

    def test_a_retry_may_cite_what_the_first_attempt_ran(self) -> None:
        not_listed = {"criteria": [], "findings": []}
        task, reviews = self.run_flow(([SUITE], not_listed), ([], verdict([SUITE])))
        self.assertEqual([r.outcome for r in reviews][:2], ["error", "approve"])
        self.assertEqual(task.status, "done")
