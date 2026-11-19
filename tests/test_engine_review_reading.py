"""A reviewer's approval of a change it was shown only part of."""

from __future__ import annotations

from pathlib import Path
import unittest

from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.runner.base import AgentEvent, AgentRunConfig
from foreman.store import ForemanStore

from engine_support import OrchestratorTestCase, ScriptedNativeRunner


def _approve(*reads: str) -> tuple[AgentEvent, ...]:
    opened = tuple(
        AgentEvent("agent.file_change", payload={"tool": "Read", "path": path}) for path in reads
    )
    return (
        *opened,
        AgentEvent("agent.message", payload={"text": "APPROVE", "phase": "result"}),
        AgentEvent("agent.completed", payload={"session_id": "review-1"}),
    )


class ReviewReadingTests(OrchestratorTestCase):
    def _run(self, reviews: list, *, cap: int = 400):
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()
        project, _, task = self.seed_project(store, repo_path=repo_path)
        project.settings["review_diff_max_chars"] = cap
        store.save_project(project)
        prompts: list[str] = []

        def developer(config: AgentRunConfig):
            work = Path(config.working_dir)
            # A change far longer than the reviewer is shown.
            self.write_text(work / "feature.txt", "line of the change\n" * 400)
            self.write_text(work / "ready.txt", "ready\n")
            self.commit_all(work, "feat: a long change")
            return (
                AgentEvent("agent.message", payload={"text": "Done.\nTASK_COMPLETE", "phase": "assistant"}),
                AgentEvent("agent.completed", payload={"session_id": "dev-1"}),
            )

        def review(events):
            def handler(config: AgentRunConfig):
                prompts.append(config.prompt)
                return events

            return handler

        handlers = {1: developer}
        for index, events in enumerate(reviews, start=2):
            handlers[index] = review(events)
        runner = ScriptedNativeRunner(handlers)
        ForemanOrchestrator(
            store, roles=self.roles, workflows=self.workflows, agent_runners={"claude_code": runner}
        ).run_project(project.id)
        return store, store.get_task(task.id), prompts, runner

    def test_an_unread_approval_of_a_cut_diff_is_sent_back_and_a_read_one_is_taken(self) -> None:
        store, task, prompts, runner = self._run([_approve(), _approve("feature.txt")])

        self.assertEqual(task.status, "done")
        self.assertEqual(runner.call_count, 3)
        self.assertRegex(prompts[0], r"\[\.\.\.truncated \d+ chars")
        self.assertIn("you opened no file", prompts[1])
        retries = [
            e for e in store.list_events(task_id=task.id)
            if e.event_type == "engine.output_contract_retry"
        ]
        self.assertEqual([e.payload["reason"] for e in retries], ["approved_unread"])

    def test_two_unread_approvals_stop_the_task_for_a_person(self) -> None:
        store, task, _, runner = self._run([_approve(), _approve()])

        self.assertEqual(runner.call_count, 3)
        self.assertEqual(task.status, "blocked")
        self.assertIn("approved a change it had not read", task.blocked_reason)
        review_runs = [r for r in store.list_runs(task_id=task.id) if r.workflow_step == "review"]
        self.assertEqual(sorted(r.outcome for r in review_runs), ["approve", "error"])
        self.assertFalse(
            [e for e in store.list_events(task_id=task.id) if e.event_type == "engine.merge"]
        )

    def test_a_search_counts_as_reading(self) -> None:
        searched = (
            AgentEvent("agent.tool_use", payload={"tool": "Grep", "input": {"pattern": "change"}}),
            *_approve(),
        )
        _, task, _, runner = self._run([searched])

        self.assertEqual(task.status, "done")
        self.assertEqual(runner.call_count, 2)

    def test_a_diff_shown_whole_can_be_approved_as_read(self) -> None:
        _, task, prompts, runner = self._run([_approve()], cap=200000)

        self.assertNotRegex(prompts[0], r"\[\.\.\.truncated \d+ chars")
        self.assertEqual(task.status, "done")
        self.assertEqual(runner.call_count, 2)


if __name__ == "__main__":
    unittest.main()
