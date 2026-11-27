"""A question an agent asked, and a person answering it from the API, the CLI and Needs you."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path

import httpx

from foreman.api.app import create_dashboard_app
from foreman.domain.models import Project, Run, Sprint, Task
from foreman.definitions.question import QUESTION_BLOCKED_REASON
from foreman.store import ForemanStore

from test_cli import cli_argv, cli_env

QUESTION = {
    "question": "Which store holds it?",
    "options": ["SQLite", "A file"],
    "recommendation": {"option": 1, "why": "It is the source of truth."},
}


class AnswerSurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "foreman.db"
        self.store = ForemanStore(self.db)
        self.store.upgrade()
        self.addCleanup(self.store.close)
        self.store.save_project(
            Project(id="p", name="P", repo_path=self.temp.name, workflow_id="development", default_branch="main")
        )
        self.store.save_sprint(Sprint(id="s", project_id="p", title="S", status="active"))
        self.store.save_task(
            Task(
                id="t", sprint_id="s", project_id="p", title="T", status="blocked", task_type="feature",
                description="Do it", acceptance_criteria="- works", workflow_current_step="develop",
                blocked_reason=QUESTION_BLOCKED_REASON,
            )
        )
        self.store.save_run(
            Run(
                id="r1", task_id="t", project_id="p", role_id="developer", workflow_step="develop",
                agent_backend="claude_code", status="completed", outcome="ask",
                outcome_detail=QUESTION["question"], started_at="2026-11-28T10:00:00Z",
                completed_at="2026-11-28T10:05:00Z", created_at="2026-11-28T10:00:00Z",
                record={"kind": "question", "fields": QUESTION},
            )
        )

    def api(self, method: str, url: str, **kwargs) -> httpx.Response:
        async def send():
            transport = httpx.ASGITransport(app=create_dashboard_app(str(self.db)))
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(send())

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cli_argv(*args, "--db", str(self.db)), env=cli_env(), capture_output=True, text=True, check=False
        )

    def test_the_task_page_carries_the_pending_question_first(self) -> None:
        task = self.api("GET", "/api/tasks/t").json()
        self.assertEqual(task["blocked_kind"], "question")
        self.assertFalse(task["awaiting_human_gate"])
        self.assertEqual(task["question"]["question"], QUESTION["question"])
        self.assertEqual(task["question"]["options"], QUESTION["options"])
        self.assertEqual(task["question"]["recommendation"]["option"], 1)
        self.assertEqual(task["question"]["step"], "develop")

    def test_needs_you_lists_the_question_with_its_options(self) -> None:
        items = self.api("GET", "/api/needs-you").json()["items"]
        asked = [item for item in items if item["kind"] == "answer_question"]
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0]["task_id"], "t")
        self.assertEqual(asked[0]["question"]["options"], QUESTION["options"])
        self.assertEqual(asked[0]["question"]["recommendation"]["why"], "It is the source of truth.")
        # And not as an unblock.
        self.assertEqual([item["kind"] for item in items], ["answer_question"])

    def test_the_api_records_an_answer_by_option(self) -> None:
        response = self.api("POST", "/api/tasks/t/answer", json={"option": 2, "requested_by": "ada"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "answered")
        self.assertEqual(body["answer"]["option_text"], "A file")
        self.assertEqual(body["answer"]["answered_by"], "ada")
        self.assertIn("Develop", body["message"])
        task = self.store.get_task("t")
        self.assertEqual((task.status, task.workflow_current_step, task.blocked_reason), ("in_progress", "develop", None))
        self.assertIsNone(self.api("GET", "/api/tasks/t").json()["question"])
        activity = [r for r in self.api("GET", "/api/tasks/t").json()["runs"] if r["outcome"] == "answered"]
        self.assertEqual(len(activity), 1)

    def test_the_api_records_an_answer_in_words_and_refuses_an_empty_or_wrong_one(self) -> None:
        for body in ({}, {"option": 9}, {"text": " "}):
            response = self.api("POST", "/api/tasks/t/answer", json=body)
            self.assertGreaterEqual(response.status_code, 400, body)
            self.assertEqual(self.store.get_task("t").status, "blocked")
        response = self.api("POST", "/api/tasks/t/answer", json={"text": "Use a file."})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["answer"]["text"], "Use a file.")
        again = self.api("POST", "/api/tasks/t/answer", json={"option": 1})
        self.assertGreaterEqual(again.status_code, 400)

    def test_the_cli_answers_with_an_option(self) -> None:
        done = self.cli("task", "answer", "t", "--option", "1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('option 1 ("SQLite")', done.stdout)
        self.assertIn("Answered by:", done.stdout)
        self.assertEqual(self.store.get_task("t").status, "in_progress")

    def test_the_cli_answers_with_words_and_says_what_is_wrong(self) -> None:
        wrong = self.cli("task", "answer", "t")
        self.assertNotEqual(wrong.returncode, 0)
        self.assertIn("option or with your own words", wrong.stderr)
        out_of_range = self.cli("task", "answer", "t", "--option", "5")
        self.assertNotEqual(out_of_range.returncode, 0)
        self.assertIn("2 options", out_of_range.stderr)
        done = self.cli("task", "answer", "t", "--text", "Use a file")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Use a file", done.stdout)

    def test_task_show_names_the_kind_and_the_question(self) -> None:
        shown = self.cli("task", "show", "t")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("Blocked kind: question", shown.stdout)
        self.assertIn("Which store holds it?", shown.stdout)
        self.assertIn("1. SQLite  <- recommended", shown.stdout)
        self.assertIn("2. A file", shown.stdout)
        self.assertIn("Recommended because: It is the source of truth.", shown.stdout)
        self.assertIn("foreman task answer", shown.stdout)

    def test_the_activity_lists_the_question_and_the_answer(self) -> None:
        self.api("POST", "/api/tasks/t/answer", json={"option": 1})
        runs = self.api("GET", "/api/tasks/t").json()["runs"]
        by_outcome = {run["outcome"]: run for run in runs}
        self.assertEqual(by_outcome["ask"]["record"]["fields"]["question"], QUESTION["question"])
        self.assertEqual(by_outcome["answered"]["record"]["fields"]["option"], 1)


if __name__ == "__main__":
    unittest.main()
