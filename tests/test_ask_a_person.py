"""An agent may ask a person a question, and the answer goes back into its step (ADR-0041 section 4)."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from foreman.definitions.roles import load_roles, load_role_text, render_prompt
from foreman.definitions.gate_steps import blocked_kind, resolve_gate_steps
from foreman.domain.question import (
    QUESTION_BLOCKED_REASON,
    check_question,
    read_question,
)
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.engine.output_contract import (
    contract_retry_reason,
    read_completion,
    with_retry_instruction,
)
from foreman.engine.results import AgentExecutionResult
from foreman.mutations import Mutations, MutationError
from foreman.store import ForemanStore

from engine_support import OrchestratorTestCase, ScriptedAgentExecutor


def block(record: dict | str) -> str:
    body = record if isinstance(record, str) else json.dumps(record)
    return f"I need to ask.\n\n```foreman-record\n{body}\n```\n"


GOOD = {
    "outcome": "ask",
    "question": "Which store holds it?",
    "options": ["SQLite", "A file"],
    "recommendation": {"option": 1, "why": "It is the source of truth."},
}


class QuestionRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.roles = load_roles()

    def test_a_well_formed_question_is_read(self) -> None:
        fields, problem = read_question(block(GOOD))
        self.assertIsNone(problem)
        self.assertEqual(fields["options"], ["SQLite", "A file"])
        self.assertEqual(fields["recommendation"], {"option": 1, "why": "It is the source of truth."})

    def test_a_message_that_asks_nothing_is_not_a_question(self) -> None:
        self.assertIsNone(read_question("Done.\n```foreman-record\n{\"summary\": \"x\"}\n```"))
        self.assertIsNone(read_question("No block at all."))

    def test_each_way_to_break_the_shape_is_named(self) -> None:
        cases = {
            "no question": ({**GOOD, "question": "  "}, "`question`"),
            "one option": ({**GOOD, "options": ["only"]}, "at least 2"),
            "no options": ({k: v for k, v in GOOD.items() if k != "options"}, "`options`"),
            "blank option": ({**GOOD, "options": ["a", " "]}, "none blank"),
            "twice": ({**GOOD, "options": ["a", "A"]}, "twice"),
            "no recommendation": ({k: v for k, v in GOOD.items() if k != "recommendation"}, "`recommendation`"),
            "recommendation outside": ({**GOOD, "recommendation": {"option": 3, "why": "x"}}, "one of them"),
            "recommendation zero": ({**GOOD, "recommendation": {"option": 0, "why": "x"}}, "one of them"),
            "recommendation as text": ({**GOOD, "recommendation": {"option": "SQLite", "why": "x"}}, "number"),
            "no why": ({**GOOD, "recommendation": {"option": 1, "why": " "}}, "`recommendation.why`"),
            "extra field": ({**GOOD, "mood": "x"}, "undeclared"),
        }
        for name, (record, expected) in cases.items():
            with self.subTest(name):
                self.assertIn(expected, "; ".join(check_question(record)))
                fields, problem = read_question(block(record))
                self.assertIsNone(fields)
                self.assertIn(expected, problem)

    def test_a_role_that_declares_ask_returns_the_question_as_its_outcome(self) -> None:
        for role_id, text in (("developer", block(GOOD) + "\nTASK_COMPLETE"), ("code_reviewer", block(GOOD))):
            with self.subTest(role_id):
                reading = read_completion(self.roles[role_id], text)
                self.assertEqual(reading.outcome, "ask")
                self.assertEqual(reading.record["kind"], "question")
                self.assertEqual(reading.record["fields"]["question"], "Which store holds it?")

    def test_a_malformed_question_is_an_error_outcome_and_gets_one_retry(self) -> None:
        role = self.roles["developer"]
        reading = read_completion(role, block({**GOOD, "options": ["one"]}))
        self.assertEqual(reading.outcome, "error")
        self.assertIn("The step's question is not usable", reading.detail)
        result = AgentExecutionResult(outcome="error", detail=reading.detail, status="completed")
        self.assertEqual(contract_retry_reason(role, result), "question_format")
        self.assertIn("```foreman-record", with_retry_instruction("p", role, "question_format"))

    def test_a_role_that_does_not_declare_ask_cannot_ask(self) -> None:
        for role_id in ("triage_reviewer", "security_reviewer"):
            self.assertNotIn("ask", self.roles[role_id].completion.outcomes)
            self.assertNotEqual(read_completion(self.roles[role_id], block(GOOD)).outcome, "ask")

    def test_the_prompts_say_when_to_ask(self) -> None:
        for role_id in ("developer", "code_reviewer"):
            with self.subTest(role_id):
                prompt = render_prompt(self.roles[role_id], {})
                self.assertIn("Asking is not failing", prompt.replace("asking is not failing", "Asking is not failing"))
                self.assertIn('"outcome": "ask"', prompt)
                self.assertIn("recommendation", prompt)
        developer = render_prompt(self.roles["developer"], {})
        for when in ("cannot\nbe done as specified", "contradicts itself or the code", "only the owner can take"):
            self.assertIn(when, developer)

    def test_a_template_without_ask_format_is_still_told_how(self) -> None:
        source = self.roles["developer"].source_path.read_text(encoding="utf-8")
        text = source.replace("{ask_format}", "")
        role = load_role_text(text, "developer.toml")
        self.assertIn('"outcome": "ask"', render_prompt(role, {}))


class AskedAndAnsweredTests(OrchestratorTestCase):
    """The task waits, holds the queue, and the answer goes back into the same step."""

    def _start(self, *, keeps_session: bool):
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        store.initialize()
        self.addCleanup(store.close)
        project, _, task = self.seed_project(store, repo_path=repo_path)
        project.settings["completion_guard_enabled"] = False
        store.save_project(project)
        developer = self.roles["developer"]
        self.roles = {
            **self.roles,
            "developer": replace(
                developer, agent=replace(developer.agent, session_persistence=keeps_session)
            ),
        }
        self.repo_path = repo_path
        self.sessions: list[str | None] = []
        return store, project, task

    def _developer_asks(self, **_):
        return AgentExecutionResult(
            outcome="ask",
            detail=GOOD["question"],
            session_id="session-1",
            record={
                "kind": "question",
                "fields": {
                    "question": GOOD["question"],
                    "options": GOOD["options"],
                    "recommendation": GOOD["recommendation"],
                },
            },
        )

    def _developer_finishes(self, *, task, prompt, carried_output):
        tree = self.work_dir(task, self.repo_path)
        self.write_text(tree / "ready.txt", "x\n")
        self.commit_all(tree, "feat: work")
        return AgentExecutionResult(outcome="done", detail="Done.", session_id="session-1")

    def _run(self, store, project, handlers):
        sessions = self.sessions

        class Recording(ScriptedAgentExecutor):
            def execute(inner, *, session_id, **kwargs):  # noqa: N805
                sessions.append(session_id)
                return super().execute(session_id=session_id, **kwargs)

        self.executor = Recording(handlers)
        ForemanOrchestrator(
            store, roles=self.roles, workflows=self.workflows, agent_executor=self.executor
        ).run_project(project.id)

    def _ask(self, keeps_session: bool):
        store, project, task = self._start(keeps_session=keeps_session)
        self._run(store, project, {("developer", 1): self._developer_asks})
        return store, project, task

    def test_the_task_waits_with_the_question_and_holds_the_queue(self) -> None:
        store, project, task = self._ask(True)
        waiting = store.get_task(task.id)
        self.assertEqual(waiting.status, "blocked")
        self.assertEqual(waiting.blocked_reason, QUESTION_BLOCKED_REASON)
        self.assertEqual(waiting.workflow_current_step, "develop")
        self.assertEqual(blocked_kind(waiting, resolve_gate_steps(store, project)), "question")
        asked = [r for r in store.list_runs(task_id=task.id) if r.outcome == "ask"]
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0].record["fields"]["recommendation"]["option"], 1)
        events = [e.event_type for e in store.list_events(task_id=task.id)]
        self.assertIn("workflow.question_asked", events)
        self.assertIn("workflow.paused", events)
        # Nothing else ran: no review, no merge.
        self.assertEqual({r.workflow_step for r in store.list_runs(task_id=task.id)}, {"develop"})
        # The step's visit is given back: the question is not a visit.
        self.assertEqual(waiting.step_visit_counts.get("develop", 0), 0)

    def test_a_task_waiting_for_an_answer_holds_the_queue(self) -> None:
        store, project, task = self._ask(True)
        orchestrator = ForemanOrchestrator(
            store, roles=self.roles, workflows=self.workflows, agent_executor=self.executor
        )
        workflow = self.workflows["development"]
        self.assertEqual(orchestrator._task_waiting_for_a_decision(project, workflow).id, task.id)

    def test_an_answer_by_option_resumes_the_session_with_the_answer_as_the_next_message(self) -> None:
        store, project, task = self._ask(True)
        Mutations(store, via="cli", actor="mario").answer_question(
            store.get_task(task.id), option=2
        )
        self._run_after_answer(store, project)
        resumed = self.executor.capture("developer", 1)
        # The session of the step that asked is resumed ...
        self.assertEqual(self.sessions[0], "session-1")
        # ... and the answer is the message: not the whole prompt again.
        self.assertIn("You asked: Which store holds it?", resumed.prompt)
        self.assertIn('option 2 ("A file")', resumed.prompt)
        self.assertNotIn("### Acceptance Criteria", resumed.prompt)
        self._assert_answer_recorded(store, task, by="mario", option=2, text="")
        # The visit count did not grow for the question.
        self.assertEqual(store.get_task(task.id).step_visit_counts["develop"], 1)
        self.assertEqual(store.get_task(task.id).status, "done")

    def test_an_answer_in_words_reaches_a_step_with_no_session_as_part_of_its_prompt(self) -> None:
        store, project, task = self._ask(False)
        Mutations(store, via="api", actor=None).answer_question(
            store.get_task(task.id), text="Use whatever the spec says."
        )
        self._run_after_answer(store, project)
        resumed = self.executor.capture("developer", 1)
        self.assertIsNone(self.sessions[0])
        # The whole prompt, with the question and the answer as an input of it.
        self.assertIn("### Acceptance Criteria", resumed.prompt)
        self.assertIn("You asked: Which store holds it?", resumed.prompt)
        self.assertIn("answered: Use whatever the spec says.", resumed.prompt)
        self._assert_answer_recorded(store, task, by="api", option=None, text="Use whatever the spec says.")
        self.assertEqual(store.get_task(task.id).step_visit_counts["develop"], 1)

    def _run_after_answer(self, store, project) -> None:
        """Run the project's engine again, with a developer that finishes and a review that approves."""

        approve = lambda **_: AgentExecutionResult(outcome="approve", detail="ok")  # noqa: E731
        self.sessions.clear()
        self._run(
            store,
            project,
            {("developer", 1): self._developer_finishes, ("code_reviewer", 1): approve},
        )

    def _assert_answer_recorded(self, store, task, *, by, option, text) -> None:
        answers = [r for r in store.list_runs(task_id=task.id) if r.outcome == "answered"]
        self.assertEqual(len(answers), 1)
        fields = answers[0].record["fields"]
        self.assertEqual(fields["answered_by"], by)
        self.assertEqual(fields["option"] if option else None, option)
        self.assertEqual(fields["text"], text)
        self.assertTrue(fields["answered_at"])
        self.assertEqual(fields["question"], GOOD["question"])
        events = [e for e in store.list_events(task_id=task.id) if e.event_type == "human.question_answered"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["answered_by"], by)

    def test_an_answer_needs_an_option_of_the_question_or_words(self) -> None:
        store, project, task = self._ask(True)
        mutations = Mutations(store, via="cli", actor="mario")
        waiting = store.get_task(task.id)
        for bad in ({}, {"option": 0}, {"option": 3}, {"text": "  "}):
            with self.subTest(bad), self.assertRaises(MutationError):
                mutations.answer_question(waiting, **bad)
        self.assertEqual(store.get_task(task.id).status, "blocked")

    def test_a_task_that_waits_for_no_question_cannot_be_answered(self) -> None:
        store, project, task = self._start(keeps_session=True)
        with self.assertRaises(MutationError):
            Mutations(store, via="cli").answer_question(store.get_task(task.id), text="x")

    def test_unblocking_a_question_is_refused_and_points_to_answering(self) -> None:
        store, project, task = self._ask(True)
        with self.assertRaisesRegex(MutationError, "foreman task answer"):
            Mutations(store, via="cli").unblock_task(store.get_task(task.id))


if __name__ == "__main__":
    unittest.main()
