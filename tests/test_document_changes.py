"""A task hears when a document it rests on changes (FOR-94).

A merge that changes a document an unfinished task rests on adds one line to
that task's Activity and its next agent step is told; a finished task, and a
task resting on a document the merge left alone, hear nothing. A command lists
the tasks that rest on a document, finished ones included.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

from foreman.cli import main
from foreman.domain.models import Project, Sprint, Task
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.mutations import Mutations
from foreman.repo.context import build_project_context
from foreman.services import Services
from foreman.services.errors import InvalidRequestError, NotFoundError
from foreman.services.task_reads import TaskReads
from foreman.store import ForemanStore

from engine_support import RepoTestCase

ADR = "docs/adr/ADR-0041.md"
SPEC = "docs/specs/engine-design-v3.md"


class _Fixture(RepoTestCase):
    def setUp(self) -> None:
        self.repo, self.db_path = self.create_workspace()
        self.initialize_repo(self.repo)
        self.write_text(self.repo / ADR, "# ADR-0041\nThe task layer.\n")
        self.write_text(self.repo / SPEC, "# Spec\n")
        self.commit_all(self.repo, "docs: documents")
        self.named_at = self.head()
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.project = Project(
            id="p", name="P", repo_path=str(self.repo), workflow_id="development", default_branch="main",
            settings={"completion_guard_enabled": False},
        )
        self.store.save_project(self.project)
        self.store.save_sprint(Sprint(id="s", project_id="p", title="S", status="active"))
        self.mutations = Mutations(self.store, via="cli")
        self.orchestrator = ForemanOrchestrator(self.store, roles=self.roles, workflows=self.workflows)

    def head(self) -> str:
        return self.git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def task(self, title: str, rests_on: list[str], status: str = "todo") -> Task:
        task = self.mutations.add_task(self.store.get_sprint("s"), title=title, rests_on=rests_on)
        if status != "todo":
            task.status = status
            self.store.save_task(task)
        return task

    def merge(self, files: dict[str, str]) -> tuple[Task, str]:
        """Merge a branch that writes ``files`` the way the engine does, and tell the tasks."""

        merging = self.mutations.add_task(self.store.get_sprint("s"), title="The change", acceptance_criteria="x")
        branch = f"feat/{merging.id}"
        self.git(self.repo, "checkout", "-q", "-b", branch)
        for path, text in files.items():
            self.write_text(self.repo / path, text)
        self.commit_all(self.repo, "feat: change")
        self.git(self.repo, "checkout", "-q", "main")
        merging.branch_name = branch
        merging.status = "in_progress"
        self.store.save_task(merging)
        step = self.orchestrator.workflows["development"].get_step("merge")
        run, outcome, _ = self.orchestrator.runner._run_builtin_step(
            self.project, merging, step, step="merge", visit_count=1, carried_output=None
        )
        self.assertEqual(outcome, "success", run.outcome_detail)
        return merging, self.head()

    def lines(self, task: Task) -> list[str]:
        return [
            run.outcome_detail
            for run in self.store.list_runs(task_id=task.id)
            if run.workflow_step == "document_changed"
        ]


class DocumentChangeTests(_Fixture):
    def test_a_merge_that_changes_a_document_tells_each_unfinished_task_resting_on_it(self) -> None:
        waiting = self.task("Waits", [f"{ADR}#6"])
        working = self.task("Works", [ADR], status="in_progress")
        blocked = self.task("Blocked", [ADR], status="blocked")
        elsewhere = self.task("Elsewhere", [SPEC])

        merged, sha = self.merge({ADR: "# ADR-0041\nSuperseded.\n"})

        key = f"{merged.task_key}'s" if merged.task_key else f"“{merged.title}”'s"
        line = f"{ADR}#6 changed in {key} merge ({sha[:7]}) since this task named it at {self.named_at[:7]}"
        self.assertEqual(self.lines(waiting), [line])
        self.assertEqual(len(self.lines(working)), 1)
        self.assertEqual(len(self.lines(blocked)), 1)
        self.assertEqual(self.lines(elsewhere), [])
        self.assertEqual(self.lines(merged), [])
        # Nothing about the task itself changed.
        after = self.store.get_task(waiting.id)
        self.assertEqual((after.status, after.rests_on), (waiting.status, waiting.rests_on))

    def test_a_finished_or_cancelled_task_is_not_told(self) -> None:
        done = self.task("Done", [ADR], status="done")
        cancelled = self.task("Cancelled", [ADR], status="cancelled")

        self.merge({ADR: "# ADR-0041\nChanged.\n"})

        self.assertEqual((self.lines(done), self.lines(cancelled)), ([], []))

    def test_a_merge_that_leaves_the_document_alone_tells_nobody(self) -> None:
        task = self.task("Waits", [ADR])

        self.merge({"docs/other.md": "other\n"})

        self.assertEqual(self.lines(task), [])

    def test_the_line_is_in_the_activity_and_the_task_page_says_the_document_changed(self) -> None:
        task = self.task("Waits", [ADR, SPEC])
        _, sha = self.merge({ADR: "# ADR-0041\nChanged.\n"})

        runs = TaskReads(self.store).list_runs(task.id, limit=20, offset=0).runs
        self.assertIn("changed in", " ".join(run.outcome_detail or "" for run in runs if run.step == "document_changed"))
        shown = Services(self.store).tasks.get_task(task.id)["rests_on"]
        self.assertEqual(shown[0]["changed"]["commit"], sha)
        self.assertIsNone(shown[1]["changed"])

        diff = TaskReads(self.store).get_document_change(task.id, ADR)
        self.assertEqual((diff.from_commit, diff.to_commit), (self.named_at, sha))
        self.assertIn("+Changed.", diff.diff)
        with self.assertRaises(NotFoundError):
            TaskReads(self.store).get_document_change(task.id, SPEC)
        with self.assertRaises(InvalidRequestError):
            TaskReads(self.store).get_document_change(task.id, "README.md")

    def test_naming_the_document_again_clears_it(self) -> None:
        task = self.task("Waits", [ADR])
        self.merge({ADR: "# ADR-0041\nChanged.\n"})
        self.mutations.edit_task(self.store.get_task(task.id), {"rests_on": []})
        self.mutations.edit_task(self.store.get_task(task.id), {"rests_on": [ADR]})

        self.assertIsNone(Services(self.store).tasks.get_task(task.id)["rests_on"][0]["changed"])

    def test_the_next_step_is_told_in_its_prompt(self) -> None:
        task = self.task("Waits", [ADR], status="in_progress")
        quiet = self.task("Quiet", [SPEC])
        merged, sha = self.merge({ADR: "# ADR-0041\nChanged.\n"})
        project = self.store.get_project("p")

        def prompt(for_task: Task) -> str:
            fresh = self.store.get_task(for_task.id)
            return self.orchestrator.prompts.build(
                self.roles["developer"], project, fresh, carried_output=None,
                context_projection=build_project_context(self.store, project, current_task=fresh),
            )

        told = prompt(task)
        self.assertIn("### Changed since this task was planned", told)
        self.assertIn(f"{ADR}: changed in", told)
        self.assertIn(sha[:10], told)
        self.assertIn(self.named_at[:10], told)
        self.assertNotIn("Changed since this task was planned", prompt(quiet))


class RestsOnListTests(_Fixture):
    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([*argv, "--db", str(self.db_path)])
        return code, out.getvalue(), err.getvalue()

    def test_the_command_lists_every_task_that_rests_on_the_document_finished_ones_included(self) -> None:
        one = self.task("Open one", [f"{ADR}#6"])
        two = self.task("Finished one", [ADR], status="done")
        three = self.task("Cancelled one", [ADR], status="cancelled")
        self.task("On the spec", [SPEC])
        self.task("On nothing", [])

        code, out, err = self.run_cli("task", "list", "p", "--rests-on", ADR)

        self.assertEqual(code, 0, err)
        for task in (one, two, three):
            self.assertIn(task.id, out)
        self.assertNotIn("On the spec", out)
        self.assertNotIn("On nothing", out)
        self.assertIn(f"rests on {ADR}#6 (named at {self.named_at[:10]})", out)

        code, out, _ = self.run_cli("task", "list", "p", "--rests-on", f"{ADR}#6")
        self.assertIn("Open one", out)
        self.assertNotIn("Finished one", out)

        code, out, _ = self.run_cli("task", "list", "p", "--rests-on", "docs/none.md")
        self.assertEqual(code, 0)
        self.assertIn("No task rests on docs/none.md.", out)

        code, out, err = self.run_cli("task", "list", "p", "--rests-on", "/etc/passwd")
        self.assertEqual(code, 1)
        self.assertIn("absolute", err)

    def test_the_json_names_the_matched_documents(self) -> None:
        self.task("Open one", [ADR, SPEC])

        code, out, _ = self.run_cli("task", "list", "p", "--rests-on", SPEC, "--json")

        self.assertEqual(code, 0)
        import json
        tasks = json.loads(out)["tasks"]
        self.assertEqual([[ref["path"] for ref in task["rests_on"]] for task in tasks], [[SPEC]])


