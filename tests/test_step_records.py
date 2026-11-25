"""A step's result is a record its role declares (ADR-0041 section 2, ADR-0042)."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import httpx

from foreman.api.app import create_dashboard_app
from foreman.definitions.records import RECORD_PROBLEM_PREFIX, parse_record_declaration
from foreman.definitions.roles import RoleLoadError, default_roles_dir, load_role_text, load_roles
from foreman.domain.models import Run
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.engine.output_contract import contract_retry_reason, read_completion, with_retry_instruction
from foreman.engine.results import AgentExecutionResult
from foreman.runner import AgentRunConfig
from foreman.runner.base import AgentEvent
from foreman.store import ForemanStore

from engine_support import OrchestratorTestCase, ScriptedAgentExecutor, ScriptedNativeRunner

ROLE = """
[role]
id = "writer"
name = "Writer"
description = "Writes"

[agent]
backend = "claude_code"
model = ""
session_persistence = false
permission_mode = "bypassPermissions"

[prompt]
template = "Write. {record_format}"

[completion]
marker = "DONE_WRITING"
timeout_minutes = 5
max_cost_usd = 1.0

{record}
"""

RECORD = """
[completion.record]
kind = "note"

[[completion.record.fields]]
name = "summary"
type = "text"
required = true

[[completion.record.fields]]
name = "items"
type = "records"
required = true

[[completion.record.fields.fields]]
name = "title"
type = "text"
required = true

[[completion.record.fields.fields]]
name = "done"
type = "bool"
required = true

[[completion.record.fields]]
name = "tags"
type = "text_list"
required = false
"""


def role_with(record: str):
    return load_role_text(ROLE.replace("{record}", record), "writer.toml")


def fenced(payload) -> str:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return f"```foreman-record\n{body}\n```"


GOOD_REPORT = {
    "summary": "Added the loader.",
    "criteria": [
        {"criterion": "The loader rejects a bad declaration", "verification": "pytest tests/x.py: 3 passed", "verified": True},
        {"criterion": "The page shows the report", "verification": "not run in a browser", "verified": False},
    ],
    "not_verified": ["The page was not opened in a browser: no display here."],
    "beyond_task": [],
    "docs_touched": ["docs/adr/ADR-0042.md"],
    "follow_ups": ["Check the criteria against the task's"],
}


class DeclarationTests(unittest.TestCase):
    def test_a_declared_record_is_loaded(self) -> None:
        record = role_with(RECORD).completion.record
        assert record is not None
        self.assertEqual(record.kind, "note")
        self.assertEqual([f.name for f in record.fields], ["summary", "items", "tags"])
        self.assertEqual([(f.name, f.type) for f in record.fields[1].fields], [("title", "text"), ("done", "bool")])
        self.assertFalse(record.fields[2].required)

    def test_a_role_with_no_record_declares_none(self) -> None:
        self.assertIsNone(role_with("").completion.record)

    def test_the_shipped_developer_declares_the_report(self) -> None:
        record = load_roles(default_roles_dir())["developer"].completion.record
        assert record is not None
        self.assertEqual(record.kind, "developer_report")
        self.assertEqual(
            [f.name for f in record.fields],
            ["summary", "criteria", "not_verified", "beyond_task", "docs_touched", "follow_ups"],
        )
        self.assertTrue(all(f.required for f in record.fields))
        self.assertEqual([f.name for f in record.fields[1].fields], ["criterion", "verification", "verified"])
        for other in ("code_reviewer", "security_reviewer", "triage_reviewer", "frontier_reviewer"):
            self.assertIsNone(load_roles(default_roles_dir())[other].completion.record)

    def test_a_malformed_declaration_is_refused_with_what_is_wrong(self) -> None:
        cases = {
            "no fields": ('[completion.record]\nkind = "note"\n', "must declare at least one field"),
            "a bad kind": (RECORD.replace('kind = "note"', 'kind = "Not A Name"'), "completion.record.kind"),
            "an unknown type": (RECORD.replace('type = "bool"', 'type = "number"'), "type must be one of"),
            "required not said": (RECORD.replace("required = false\n", "", 1), "required must be true or false"),
            "a field twice": (RECORD.replace('name = "tags"', 'name = "summary"'), "declared twice"),
            "an unknown key": (RECORD.replace('name = "tags"', 'name = "tags"\nlabel = "x"'), "unknown key"),
            "records with no fields": (
                '[completion.record]\nkind = "n"\n[[completion.record.fields]]\nname = "a"\ntype = "records"\nrequired = true\n',
                "must declare at least one field",
            ),
            "fields on a text": (
                '[completion.record]\nkind = "n"\n[[completion.record.fields]]\nname = "a"\ntype = "text"\n'
                'required = true\n[[completion.record.fields.fields]]\nname = "b"\ntype = "text"\nrequired = true\n',
                "only a field of type records takes fields",
            ),
            "records inside records": (
                RECORD.replace('name = "done"\ntype = "bool"', 'name = "done"\ntype = "records"'),
                "cannot hold records",
            ),
        }
        for label, (record, message) in cases.items():
            with self.subTest(label), self.assertRaises(RoleLoadError) as caught:
                role_with(record)
            self.assertIn(message, str(caught.exception))

    def test_a_decision_role_cannot_declare_a_record(self) -> None:
        text = ROLE.replace("{record}", RECORD + "\n[completion.output]\nextract_decision = true\n")
        with self.assertRaises(RoleLoadError) as caught:
            load_role_text(text, "r.toml")
        self.assertIn("returns a decision", str(caught.exception))

    def test_the_prompt_says_how_to_return_the_record(self) -> None:
        prompt = role_with(RECORD).render_prompt({})
        self.assertIn("```foreman-record", prompt)
        self.assertIn("`summary` (text, required)", prompt)
        self.assertIn("before the `DONE_WRITING` line", prompt)
        self.assertNotIn("foreman-record", role_with("").render_prompt({}))


class ReadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.role = role_with(RECORD)

    def read(self, text: str):
        return read_completion(self.role, text)

    def test_a_well_formed_record_is_returned_with_the_words_around_it(self) -> None:
        payload = {"summary": "s", "items": [{"title": "a", "done": True}]}
        reading = self.read(f"Wrote it.\n\n{fenced(payload)}\nDONE_WRITING")
        self.assertEqual((reading.outcome, reading.detail), ("done", "Wrote it."))
        self.assertEqual(reading.record, {"kind": "note", "fields": payload})

    def test_with_no_words_around_it_the_summary_field_is_the_detail(self) -> None:
        reading = self.read(f"{fenced({'summary': 'In short.', 'items': []})}\nDONE_WRITING")
        self.assertEqual(reading.detail, "In short.")

    def test_the_last_block_counts(self) -> None:
        first = fenced({"summary": "old", "items": []})
        last = fenced({"summary": "new", "items": []})
        self.assertEqual(self.read(f"{first}\n{last}\nDONE_WRITING").record["fields"]["summary"], "new")

    def test_a_missing_record_is_an_error_that_says_so(self) -> None:
        reading = self.read("Wrote it.\nDONE_WRITING")
        self.assertEqual(reading.outcome, "error")
        self.assertIsNone(reading.record)
        self.assertTrue(reading.detail.startswith(RECORD_PROBLEM_PREFIX))
        self.assertIn("no ```foreman-record``` block", reading.detail)

    def test_a_record_that_is_not_json_is_an_error(self) -> None:
        reading = self.read(f"{fenced('{not json')}\nDONE_WRITING")
        self.assertEqual(reading.outcome, "error")
        self.assertIn("not valid JSON", reading.detail)

    def test_each_way_to_break_the_declaration_is_named(self) -> None:
        cases = {
            "a required field missing": ({"items": []}, "`summary` is required and missing"),
            "a required text blank": ({"summary": " ", "items": []}, "`summary` is required and blank"),
            "a wrong type": ({"summary": 3, "items": []}, "`summary` must be text"),
            "a bool as text": ({"summary": "s", "items": [{"title": "a", "done": "yes"}]}, "`items[1].done` must be true or false"),
            "an entry's field missing": ({"summary": "s", "items": [{"done": True}]}, "`items[1].title` is required and missing"),
            "a list of the wrong shape": ({"summary": "s", "items": ["a"]}, "`items` must be a list of objects"),
            "text list of numbers": ({"summary": "s", "items": [], "tags": [1]}, "`tags` must be a list of text"),
            "an undeclared field": ({"summary": "s", "items": [], "extra": 1}, "undeclared field(s) extra"),
            "not an object": ([1], "must be a JSON object"),
        }
        for label, (payload, message) in cases.items():
            with self.subTest(label):
                reading = self.read(f"{fenced(payload)}\nDONE_WRITING")
                self.assertEqual(reading.outcome, "error")
                self.assertIn(message, reading.detail)
                self.assertIsNone(reading.record)

    def test_an_optional_field_may_be_left_out(self) -> None:
        reading = self.read(f"{fenced({'summary': 's', 'items': []})}\nDONE_WRITING")
        self.assertEqual(reading.outcome, "done")

    def test_a_missing_marker_is_still_the_markers_error(self) -> None:
        reading = self.read(fenced({"summary": "s", "items": []}))
        self.assertEqual(reading.detail, "Missing completion marker `DONE_WRITING`.")

    def test_a_role_with_no_record_reads_as_before(self) -> None:
        reading = read_completion(role_with(""), f"Wrote it.\n{fenced({'a': 1})}\nDONE_WRITING")
        self.assertEqual(reading.outcome, "done")
        self.assertIsNone(reading.record)
        self.assertIn("foreman-record", reading.detail)

    def test_a_malformed_record_gets_one_correction_that_says_the_shape_again(self) -> None:
        reading = self.read("Wrote it.\nDONE_WRITING")
        result = AgentExecutionResult(outcome=reading.outcome, detail=reading.detail)
        reason = contract_retry_reason(self.role, result)
        self.assertEqual(reason, "record_format")
        correction = with_retry_instruction("FIRST", self.role, reason, resumes_session=True)
        self.assertTrue(correction.startswith("### Output Correction"))
        self.assertIn("```foreman-record", correction)

    def test_declaration_parsing_returns_none_for_no_table(self) -> None:
        self.assertIsNone(parse_record_declaration(None, "x"))


def native_developer(repo_text: str, *, work=None):
    """A native-runner handler: commits a file, then says *repo_text*."""

    def handler(config: AgentRunConfig):
        if work is not None:
            work(Path(config.working_dir))
        return (
            AgentEvent("agent.message", payload={"text": repo_text, "phase": "result"}),
            AgentEvent("agent.completed", payload={"session_id": "dev-1", "cost_usd": 0.1}),
        )

    return handler


class EngineRecordTests(OrchestratorTestCase):
    def developer_changes(self):
        def work(tree: Path) -> None:
            self.write_text(tree / "feature.txt", "x\n")
            self.write_text(tree / "ready.txt", "ready\n")
            self.commit_all(tree, "feat: slice")

        return work

    def run_with(self, developer_text: str, *, bad: bool = False):
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()
        project, _, task = self.seed_project(store, repo_path=repo_path)
        prompts: list[str] = []

        def review(config: AgentRunConfig):
            prompts.append(config.prompt)
            return (
                AgentEvent("agent.message", payload={"text": "APPROVE", "phase": "result"}),
                AgentEvent("agent.completed", payload={}),
            )

        handlers = {1: native_developer(developer_text, work=self.developer_changes())}
        # A bad answer gets one corrective retry, which answers the same way.
        first_review = 2
        if bad:
            handlers[2] = native_developer(developer_text)
            first_review = 3
        for index in range(first_review, first_review + 4):
            handlers[index] = review
        runner = ScriptedNativeRunner(handlers)
        ForemanOrchestrator(
            store, roles=self.roles, workflows=self.workflows, agent_runners={"claude_code": runner}
        ).run_project(project.id)
        return store, store.get_task(task.id), prompts, runner, db_path

    def get(self, db_path, path: str) -> httpx.Response:
        app = create_dashboard_app(str(db_path), auth_token=None)

        async def call():
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
                return await c.get(path)

        return asyncio.run(call())

    def test_a_well_formed_report_is_stored_with_the_run_and_returned_by_the_api(self) -> None:
        store, task, _, _, db_path = self.run_with(f"Did it.\n\n{fenced(GOOD_REPORT)}\nTASK_COMPLETE")

        develop = [r for r in store.list_runs(task_id=task.id) if r.workflow_step == "develop"][0]
        self.assertEqual(develop.outcome, "done")
        self.assertEqual(develop.record, {"kind": "developer_report", "fields": GOOD_REPORT})
        self.assertEqual(develop.outcome_detail, "Did it.")

        runs = self.get(db_path, f"/api/v1/tasks/{task.id}/runs").json()["runs"]
        by_step = {r["step"]: r for r in runs}
        self.assertEqual(by_step["develop"]["record"], {"kind": "developer_report", "fields": GOOD_REPORT})
        self.assertIsNone(by_step["review"]["record"])

    def test_a_missing_report_is_an_error_the_run_explains_and_the_task_is_routed_as_an_error(self) -> None:
        store, task, prompts, runner, db_path = self.run_with("Did it.\nTASK_COMPLETE", bad=True)

        develop = [r for r in store.list_runs(task_id=task.id) if r.workflow_step == "develop"]
        # One corrective retry, then the error stands.
        self.assertEqual([r.outcome for r in develop], ["error", "error"])
        self.assertIsNone(develop[-1].record)
        self.assertIn(RECORD_PROBLEM_PREFIX, develop[-1].outcome_detail)
        self.assertIn("no ```foreman-record``` block", develop[-1].outcome_detail)
        retries = [e for e in store.list_events(task_id=task.id) if e.event_type == "engine.output_contract_retry"]
        self.assertEqual([e.payload["reason"] for e in retries], ["record_format"])
        # Routed as an error is: not reviewed, not merged.
        self.assertEqual(prompts, [])
        self.assertNotEqual(task.status, "done")
        runs = self.get(db_path, f"/api/v1/tasks/{task.id}/runs").json()["runs"]
        self.assertIn(RECORD_PROBLEM_PREFIX, runs[0]["outcome_detail"])

    def test_a_malformed_report_is_an_error_naming_the_field(self) -> None:
        broken = {**GOOD_REPORT, "criteria": [{"criterion": "c", "verification": "v", "verified": "yes"}]}
        store, task, _, _, _ = self.run_with(f"Did it.\n{fenced(broken)}\nTASK_COMPLETE", bad=True)

        develop = [r for r in store.list_runs(task_id=task.id) if r.workflow_step == "develop"][-1]
        self.assertEqual(develop.outcome, "error")
        self.assertIn("`criteria[1].verified` must be true or false", develop.outcome_detail)

    def test_the_code_reviewers_prompt_shows_the_report_criterion_by_criterion(self) -> None:
        _, task, prompts, _, _ = self.run_with(f"Did it.\n{fenced(GOOD_REPORT)}\nTASK_COMPLETE")

        self.assertEqual(task.status, "done")
        prompt = prompts[0]
        self.assertIn("### Developer's Report", prompt)
        self.assertIn("Added the loader.", prompt)
        self.assertIn(
            "1. The loader rejects a bad declaration\n"
            "   - Verified by the developer: yes\n"
            "   - How: pytest tests/x.py: 3 passed",
            prompt,
        )
        self.assertIn(
            "2. The page shows the report\n"
            "   - Verified by the developer: no\n"
            "   - How: not run in a browser",
            prompt,
        )
        self.assertIn("#### Not verified, and why\n\n- The page was not opened in a browser: no display here.", prompt)
        self.assertIn("#### Behaviour changed beyond the task\n\nNothing.", prompt)
        self.assertIn("- docs/adr/ADR-0042.md", prompt)
        self.assertIn("- Check the criteria against the task's", prompt)
        # The report is not the free text pasted again.
        self.assertNotIn("Did it.", prompt)

    def test_a_reviewer_is_given_a_developers_free_text_when_the_step_has_no_record(self) -> None:
        # A project's own developer role that declares no record (ADR-0024).
        roles = {
            **self.roles,
            "developer": replace(
                self.roles["developer"], completion=replace(self.roles["developer"].completion, record=None)
            ),
        }
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()
        project, _, task = self.seed_project(store, repo_path=repo_path)
        seen: list[str] = []

        def developer(*, task, prompt, carried_output):
            self.write_text(self.work_dir(task, repo_path) / "feature.txt", "x\n")
            self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
            self.commit_all(self.work_dir(task, repo_path), "feat: slice")
            return AgentExecutionResult(outcome="done", detail="Plain words from the developer.")

        def reviewer(*, task, prompt, carried_output):
            seen.append(prompt)
            return AgentExecutionResult(outcome="approve", detail="APPROVE")

        executor = ScriptedAgentExecutor({("developer", 1): developer, ("code_reviewer", 1): reviewer})
        ForemanOrchestrator(
            store, roles=roles, workflows=self.workflows, agent_executor=executor
        ).run_project(project.id)

        self.assertIn("### Developer's Report\nPlain words from the developer.", seen[0])
        self.assertIsNone([r for r in store.list_runs(task_id=task.id) if r.workflow_step == "develop"][0].record)


class StoreTests(unittest.TestCase):
    def test_a_record_survives_the_store_and_an_old_run_has_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = ForemanStore(Path(temp) / "f.db")
            store.initialize()
            self.addCleanup(store.close)
            columns = {row[1] for row in store._connection.execute("PRAGMA table_info(runs)")}
            self.assertIn("record_json", columns)
            from foreman.domain.models import Project, Sprint, Task

            store.save_project(Project(id="p", name="P", repo_path=temp, workflow_id="development"))
            store.save_sprint(Sprint(id="s", project_id="p", title="S", status="active"))
            store.save_task(Task(id="t", sprint_id="s", project_id="p", title="T", status="todo"))
            store.save_run(Run(id="a", task_id="t", project_id="p", role_id="developer", workflow_step="develop",
                               agent_backend="claude_code", record={"kind": "k", "fields": {"x": [1]}}))
            store.save_run(Run(id="b", task_id="t", project_id="p", role_id="developer", workflow_step="develop",
                               agent_backend="claude_code"))
            self.assertEqual(store.get_run("a").record, {"kind": "k", "fields": {"x": [1]}})
            self.assertIsNone(store.get_run("b").record)


if __name__ == "__main__":
    unittest.main()
