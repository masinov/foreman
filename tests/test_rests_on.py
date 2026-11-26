"""A task names the documents it rests on, with the default branch's commit
at the moment each was named (ADR-0041 section 6, FOR-93).

Every way in is covered: the mutations, the CLI, the dashboard's API, the
manager's proposals and the intake API; a path that is not on the default
branch is refused with the reason; a step's prompt lists them as pointers.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from foreman.cli import main
from foreman.domain.models import Project, Sprint, Task
from foreman.domain.rests_on import DocumentRef, RestsOnError, parse_documents, pointers_text
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.manager.proposals import ProposalError, Proposals
from foreman.mutations import MutationError, Mutations
from foreman.repo.context import build_project_context
from foreman.repo.rests_on import name_documents
from foreman.services import Services
from foreman.services.errors import InvalidRequestError
from foreman.services.task_reads import TaskReads
from foreman.store import ForemanStore

from engine_support import RepoTestCase

ADR = "docs/adr/ADR-0041.md"
SPEC = "docs/specs/engine-design-v3.md"


class _Repo(unittest.TestCase):
    """A repository whose default branch holds two documents, and a project on it."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        root = Path(self._temp.name)
        self.repo = root / "repo"
        (self.repo / "docs" / "adr").mkdir(parents=True)
        (self.repo / "docs" / "specs").mkdir(parents=True)
        self.git("init")
        self.git("checkout", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")
        (self.repo / ADR).write_text("# ADR-0041\nThe task layer.\n", encoding="utf-8")
        (self.repo / SPEC).write_text("# Spec\n", encoding="utf-8")
        self.first = self.commit("chore: documents")
        self.db_path = root / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.project = Project(id="p1", name="P", repo_path=str(self.repo), workflow_id="development")
        self.store.save_project(self.project)
        self.store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))

    def git(self, *args: str) -> str:
        done = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True)
        return done.stdout.strip()

    def commit(self, message: str) -> str:
        self.git("add", ".")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def move_the_default_branch(self) -> str:
        (self.repo / "NOTES.md").write_text(f"{self.git('rev-parse', 'HEAD')}\n", encoding="utf-8")
        return self.commit("docs: notes")

    def stored(self, task_id: str) -> Task:
        task = self.store.get_task(task_id)
        assert task is not None
        return task


class DocumentRefTests(unittest.TestCase):
    def test_entries_are_a_path_with_an_optional_heading_and_repeats_are_dropped(self) -> None:
        refs = parse_documents(f"{ADR}#6\n\n {SPEC} \n{ADR}#6\n")

        self.assertEqual([(ref.path, ref.heading) for ref in refs], [(ADR, "6"), (SPEC, "")])
        self.assertEqual(parse_documents([{"path": SPEC, "heading": "6.3"}])[0].label(), f"{SPEC}#6.3")

    def test_a_path_outside_the_repository_is_refused_with_the_reason(self) -> None:
        for bad, words in (("/etc/passwd", "absolute"), ("../secrets.md", "inside the repository"), ("", "needs a path")):
            with self.assertRaises(RestsOnError) as caught:
                parse_documents([bad])
            self.assertIn(words, str(caught.exception))

    def test_pointers_give_the_path_the_heading_and_the_commit_and_nothing_else(self) -> None:
        text = pointers_text([DocumentRef(ADR, "6", "a" * 40), DocumentRef(SPEC, "", "b" * 40)])

        self.assertIn(f"- {ADR}, 6 (named at {'a' * 10})", text)
        self.assertIn(f"- {SPEC} (named at {'b' * 10})", text)
        self.assertEqual(pointers_text([]), "")


class NamingTests(_Repo):
    def test_each_document_gets_the_default_branchs_commit_now(self) -> None:
        named = name_documents(self.repo, "main", [f"{ADR}#6", SPEC])

        self.assertEqual([ref.commit for ref in named], [self.first, self.first])

    def test_a_path_that_is_not_on_the_default_branch_is_refused_with_the_reason(self) -> None:
        (self.repo / "docs" / "only-in-the-tree.md").write_text("x\n", encoding="utf-8")  # not committed

        for missing in ("docs/nope.md", "docs/only-in-the-tree.md"):
            with self.assertRaises(RestsOnError) as caught:
                name_documents(self.repo, "main", [missing])
            self.assertIn(f"{missing} does not exist on main", str(caught.exception))
        with self.assertRaises(RestsOnError) as caught:
            name_documents(self.repo, "main", ["docs"])
        self.assertIn("directory", str(caught.exception))

    def test_a_document_named_before_keeps_its_commit_and_a_new_one_gets_the_current_one(self) -> None:
        before = name_documents(self.repo, "main", [ADR])
        later = self.move_the_default_branch()

        after = name_documents(self.repo, "main", [ADR, SPEC], already=before)

        self.assertEqual(after[0].commit, self.first)
        self.assertEqual(after[1].commit, later)


class MutationTests(_Repo):
    def setUp(self) -> None:
        super().setUp()
        self.mutations = Mutations(self.store, via="cli", actor="alice")

    def test_add_task_stores_each_document_with_the_commit(self) -> None:
        task = self.mutations.add_task(
            self.store.get_sprint("s1"), title="T", rests_on=[f"{ADR}#6", {"path": SPEC, "heading": "6.3"}]
        )

        stored = self.stored(task.id)
        self.assertEqual(
            [ref.as_dict() for ref in stored.rests_on],
            [
                {"path": ADR, "heading": "6", "commit": self.first},
                {"path": SPEC, "heading": "6.3", "commit": self.first},
            ],
        )

    def test_add_task_refuses_a_missing_path_and_files_nothing(self) -> None:
        with self.assertRaises(MutationError) as caught:
            self.mutations.add_task(self.store.get_sprint("s1"), title="T", rests_on=["docs/nope.md"])

        self.assertIn("docs/nope.md does not exist on main", str(caught.exception))
        self.assertEqual(self.store.list_tasks(sprint_id="s1"), [])

    def test_file_task_stores_them_in_the_backlog(self) -> None:
        filed = self.mutations.file_task(self.project, title="T", rests_on=[ADR])

        self.assertEqual(self.stored(filed.task.id).rests_on[0].commit, self.first)

    def test_edit_task_names_adds_and_clears_and_an_old_one_keeps_its_commit(self) -> None:
        task = self.mutations.add_task(self.store.get_sprint("s1"), title="T", rests_on=[ADR])
        later = self.move_the_default_branch()

        changed = self.mutations.edit_task(task, {"rests_on": [ADR, SPEC]})

        self.assertEqual([item["commit"] for item in changed["rests_on"]], [self.first, later])
        self.assertEqual([ref.commit for ref in self.stored(task.id).rests_on], [self.first, later])
        self.assertEqual(self.mutations.edit_task(task, {"rests_on": [ADR, SPEC]}), {})
        self.mutations.edit_task(task, {"rests_on": []})
        self.assertEqual(self.stored(task.id).rests_on, [])

    def test_edit_task_refuses_a_missing_path_and_changes_nothing(self) -> None:
        task = self.mutations.add_task(self.store.get_sprint("s1"), title="T", rests_on=[ADR])

        with self.assertRaises(MutationError) as caught:
            self.mutations.edit_task(task, {"rests_on": ["docs/nope.md"]})

        self.assertIn("does not exist on main", str(caught.exception))
        self.assertEqual([ref.path for ref in self.stored(task.id).rests_on], [ADR])

    def test_an_edit_of_a_running_task_says_so_in_its_audit_event(self) -> None:
        task = self.mutations.add_task(self.store.get_sprint("s1"), title="T")
        task.status = "in_progress"
        self.store.save_task(task)

        self.mutations.edit_task(task, {"rests_on": [ADR]})

        event = [e for e in self.store.list_events(task_id=task.id) if e.event_type == "human.task_edited"][0]
        self.assertEqual(event.payload["changed_fields"]["rests_on"][0]["path"], ADR)

    def test_the_engine_does_not_overwrite_them(self) -> None:
        task = self.mutations.add_task(self.store.get_sprint("s1"), title="T")
        engine_copy = self.stored(task.id)
        self.mutations.edit_task(task, {"rests_on": [ADR]})

        self.store.update_task_engine_state(engine_copy)

        self.assertEqual([ref.path for ref in self.stored(task.id).rests_on], [ADR])


class DashboardApiTests(_Repo):
    def test_a_task_is_created_edited_and_read_with_its_documents(self) -> None:
        api = Services(self.store)

        created = api.tasks.create_task("s1", title="T", rests_on=[f"{ADR}#6"])
        self.assertEqual(created["rests_on"], [{"path": ADR, "heading": "6", "commit": self.first}])
        detail = api.tasks.update_task_fields(created["id"], updates={"rests_on": [ADR, SPEC]})
        self.assertEqual([item["path"] for item in detail["rests_on"]], [ADR, SPEC])
        self.assertEqual(api.tasks.get_task(created["id"])["rests_on"][0]["heading"], "")

    def test_a_missing_path_is_refused_as_an_invalid_request_with_the_reason(self) -> None:
        api = Services(self.store)

        with self.assertRaises(InvalidRequestError) as caught:
            api.tasks.create_task("s1", title="T", rests_on=["docs/nope.md"])
        self.assertIn("does not exist on main", str(caught.exception))
        with self.assertRaises(InvalidRequestError):
            api.backlog.file_backlog_task("p1", title="T", rests_on=["docs/nope.md"])

    def test_a_backlog_task_carries_them(self) -> None:
        filed = Services(self.store).backlog.file_backlog_task("p1", title="T", rests_on=[ADR])

        self.assertEqual(filed["rests_on"][0]["commit"], self.first)

    def test_a_document_is_read_as_it_was_at_its_commit_and_only_if_the_task_names_it(self) -> None:
        task = Services(self.store).tasks.create_task("s1", title="T", rests_on=[ADR])
        (self.repo / ADR).write_text("# ADR-0041\nChanged.\n", encoding="utf-8")
        self.commit("docs: change the ADR")

        document = TaskReads(self.store).get_document(task["id"], ADR)

        self.assertIn("The task layer.", document.text)
        self.assertEqual(document.commit, self.first)
        with self.assertRaises(InvalidRequestError):
            TaskReads(self.store).get_document(task["id"], SPEC)


class IntakeTests(_Repo):
    def test_intake_takes_them_optionally_and_refuses_a_missing_path(self) -> None:
        token, _ = self.store.create_api_token(project_id="p1", name="pagerduty")
        intake = Services(self.store).intake

        plain = intake.intake_task("p1", token=token, title="A")
        named = intake.intake_task("p1", token=token, title="B", rests_on=[{"path": ADR, "heading": "6"}])

        self.assertEqual(plain["rests_on"], [])
        self.assertEqual(named["rests_on"], [{"path": ADR, "heading": "6", "commit": self.first, "changed": None}])
        with self.assertRaises(InvalidRequestError) as caught:
            intake.intake_task("p1", token=token, title="C", rests_on=["docs/nope.md"])
        self.assertIn("does not exist on main", str(caught.exception))
        self.assertEqual(len(self.store.list_tasks(project_id="p1")), 2)


class ProposalTests(_Repo):
    def test_a_proposal_names_them_on_filing_adding_and_editing(self) -> None:
        existing = Mutations(self.store, via="cli").add_task(self.store.get_sprint("s1"), title="Existing")
        proposals = Proposals(self.store, via="cli", actor="manager")

        proposal = proposals.create(
            self.project,
            reason="Name what the work rests on.",
            operations=[
                {"kind": "file_task", "title": "Filed", "rests_on": [ADR]},
                {"kind": "add_task", "sprint_id": "s1", "title": "Added", "rests_on": [f"{SPEC}#6.3"]},
                {"kind": "edit_task", "task_id": existing.id, "rests_on": [ADR]},
            ],
            proposed_by="manager",
        )
        result = proposals.confirm(proposal.id)

        self.assertEqual(result.state, "confirmed")
        by_title = {task.title: task for task in self.store.list_tasks(project_id="p1")}
        self.assertEqual([r.as_dict() for r in by_title["Filed"].rests_on], [{"path": ADR, "heading": "", "commit": self.first}])
        self.assertEqual(by_title["Added"].rests_on[0].heading, "6.3")
        self.assertEqual(by_title["Existing"].rests_on[0].commit, self.first)

    def test_a_proposal_naming_a_missing_path_is_refused_when_it_is_made(self) -> None:
        with self.assertRaises(ProposalError) as caught:
            Proposals(self.store, via="cli", actor="manager").create(
                self.project,
                reason="Because.",
                operations=[{"kind": "file_task", "title": "Filed", "rests_on": ["docs/nope.md"]}],
                proposed_by="manager",
            )
        self.assertIn("does not exist on main", str(caught.exception))

    def test_a_malformed_list_is_refused(self) -> None:
        with self.assertRaises(ProposalError):
            Proposals(self.store, via="cli", actor="manager").create(
                self.project,
                reason="Because.",
                operations=[{"kind": "file_task", "title": "Filed", "rests_on": "docs/a.md"}],
                proposed_by="manager",
            )


class CliTests(_Repo):
    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([*argv, "--db", str(self.db_path)])
        return code, out.getvalue(), err.getvalue()

    def test_task_add_names_documents_and_prints_each_with_its_commit(self) -> None:
        code, out, err = self.run_cli(
            "task", "add", "p1", "--title", "T", "--criteria", "C",
            "--rests-on", f"{ADR}#6", "--rests-on", SPEC,
        )

        self.assertEqual(code, 0, err)
        self.assertIn(f"{ADR}#6 (named at {self.first[:10]})", out)
        (task,) = self.store.list_tasks(sprint_id="s1")
        self.assertEqual([ref.path for ref in task.rests_on], [ADR, SPEC])

    def test_task_add_refuses_a_missing_path_with_the_reason(self) -> None:
        code, _, err = self.run_cli(
            "task", "add", "p1", "--title", "T", "--criteria", "C", "--rests-on", "docs/nope.md"
        )

        self.assertEqual(code, 1)
        self.assertIn("docs/nope.md does not exist on main", err)
        self.assertEqual(self.store.list_tasks(sprint_id="s1"), [])

    def test_task_edit_replaces_and_clears_them(self) -> None:
        task = Mutations(self.store, via="cli").add_task(self.store.get_sprint("s1"), title="T", rests_on=[ADR])

        code, out, err = self.run_cli("task", "edit", task.id, "--rests-on", SPEC)
        self.assertEqual(code, 0, err)
        self.assertIn("Documents: 1 -> 1 documents", out)
        self.assertEqual([ref.path for ref in self.stored(task.id).rests_on], [SPEC])
        code, out, _ = self.run_cli("task", "edit", task.id, "--no-rests-on")
        self.assertEqual(code, 0)
        self.assertIn("Rests on: nothing named", out)
        self.assertEqual(self.stored(task.id).rests_on, [])
        code, _, err = self.run_cli("task", "edit", task.id, "--rests-on", ADR, "--no-rests-on")
        self.assertEqual(code, 1)
        self.assertIn("not both", err)

    def test_backlog_add_names_documents(self) -> None:
        code, _, err = self.run_cli("backlog", "add", "p1", "--title", "T", "--rests-on", ADR)

        self.assertEqual(code, 0, err)
        (task,) = self.store.list_tasks(project_id="p1")
        self.assertEqual(task.rests_on[0].commit, self.first)


class PromptTests(RepoTestCase):
    def test_every_role_is_given_the_documents_as_pointers_not_text(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        self.write_text(repo_path / ADR, "SECRET-BODY-OF-THE-ADR\n")
        self.commit_all(repo_path, "docs: adr")
        commit = self.git(repo_path, "rev-parse", "HEAD").stdout.strip()
        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(
                id="p", name="P", repo_path=str(repo_path), workflow_id="development", default_branch="main"
            )
            store.save_project(project)
            store.save_sprint(Sprint(id="s", project_id="p", title="S", status="active"))
            task = Mutations(store, via="cli").add_task(
                store.get_sprint("s"), title="T", acceptance_criteria="It works.", rests_on=[f"{ADR}#6"]
            )
            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)
            context = build_project_context(store, project, current_task=task)

            for role_id in ("developer", "code_reviewer"):
                prompt = orchestrator.prompts.build(
                    self.roles[role_id], project, task, carried_output=None, context_projection=context
                )
                self.assertIn("## Documents this task rests on", prompt, role_id)
                self.assertIn(f"- {ADR}, 6 (named at {commit[:10]})", prompt, role_id)
                self.assertNotIn("SECRET-BODY-OF-THE-ADR", prompt, role_id)

    def test_a_task_that_names_none_adds_no_section(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        with ForemanStore(db_path) as store:
            store.initialize()
            project = Project(id="p", name="P", repo_path=str(repo_path), workflow_id="development")
            store.save_project(project)
            store.save_sprint(Sprint(id="s", project_id="p", title="S", status="active"))
            task = Mutations(store, via="cli").add_task(store.get_sprint("s"), title="T")
            orchestrator = ForemanOrchestrator(store, roles=self.roles, workflows=self.workflows)
            prompt = orchestrator.prompts.build(
                self.roles["developer"], project, task, carried_output=None,
                context_projection=build_project_context(store, project, current_task=task),
            )

            self.assertNotIn("Documents this task rests on", prompt)


if __name__ == "__main__":
    unittest.main()


class EdgeTests(_Repo):
    """What the review of FOR-93 found: what a document is, how one is written, where one is refused."""

    def add(self, value: object) -> Task:
        return Mutations(self.store, via="cli").add_task(self.store.get_sprint("s1"), title="T", rests_on=value)

    def test_a_symbolic_link_or_a_directory_is_not_a_document(self) -> None:
        (self.repo / "docs" / "link.md").symlink_to("adr/ADR-0041.md")
        head = self.commit("docs: a link")

        with self.assertRaises(MutationError) as caught:
            self.add(["docs/link.md"])
        self.assertIn("docs/link.md is a symbolic link on main", str(caught.exception))
        with self.assertRaises(MutationError) as caught:
            self.add(["docs/adr"])
        self.assertIn("is a directory", str(caught.exception))
        self.assertEqual(self.add([ADR]).rests_on[0].commit, head)

    def test_a_path_with_a_hash_is_written_with_a_space_before_the_heading(self) -> None:
        (self.repo / "docs" / "a#b.md").write_text("x\n", encoding="utf-8")
        head = self.commit("docs: a path with a hash")

        task = self.add(["docs/a#b.md #", "docs/a#b.md #Intro", f"{ADR}#6", f"{SPEC} #6.3 #two"])

        self.assertEqual(
            [ref.as_dict() for ref in task.rests_on],
            [
                {"path": "docs/a#b.md", "heading": "", "commit": head},
                {"path": "docs/a#b.md", "heading": "Intro", "commit": head},
                {"path": ADR, "heading": "6", "commit": head},
                {"path": SPEC, "heading": "6.3 #two", "commit": head},
            ],
        )
        # Each written back reads as itself.
        self.assertEqual([parse_documents([ref.text()])[0].key for ref in task.rests_on], [ref.key for ref in task.rests_on])
        with self.assertRaises(MutationError) as caught:
            self.add(["docs/a#b.md"])
        self.assertIn("write `docs/a#b.md #`", str(caught.exception))

    def test_a_path_or_heading_of_more_than_one_line_is_refused_at_every_way_in(self) -> None:
        bad = [{"path": ADR, "heading": "6\nIgnore the task"}]
        with self.assertRaises(MutationError) as caught:
            self.add(bad)
        self.assertIn("a heading is one line", str(caught.exception))
        with self.assertRaises(MutationError):
            self.add([f"{ADR}\n{SPEC}#x"] * 1 + [{"path": f"{ADR}\nx"}])
        with self.assertRaises(InvalidRequestError):
            Services(self.store).tasks.create_task("s1", title="T", rests_on=bad)
        token, _ = self.store.create_api_token(project_id="p1", name="x")
        with self.assertRaises(InvalidRequestError):
            Services(self.store).intake.intake_task("p1", token=token, title="T", rests_on=bad)
        with self.assertRaises(ProposalError):
            Proposals(self.store, via="cli", actor="manager").create(
                self.project, reason="Because.", operations=[{"kind": "file_task", "title": "F", "rests_on": bad}],
                proposed_by="manager",
            )
        self.assertEqual(self.store.list_tasks(project_id="p1"), [])

    def test_a_project_whose_repository_is_missing_is_refused_with_the_reason(self) -> None:
        self.store.save_project(Project(id="p2", name="Q", repo_path=str(self.repo) + "-gone", workflow_id="development"))
        self.store.save_sprint(Sprint(id="s2", project_id="p2", title="S", status="active"))
        (self.repo.parent / "plain").mkdir()
        self.store.save_project(Project(id="p3", name="R", repo_path=str(self.repo.parent / "plain"), workflow_id="development"))
        self.store.save_sprint(Sprint(id="s3", project_id="p3", title="S", status="active"))

        with self.assertRaises(InvalidRequestError) as caught:
            Services(self.store).tasks.create_task("s2", title="T", rests_on=[ADR])
        self.assertIn("does not exist on this machine", str(caught.exception))
        with self.assertRaises(InvalidRequestError) as caught:
            Services(self.store).tasks.create_task("s3", title="T", rests_on=[ADR])
        self.assertIn("not a git repository", str(caught.exception))

    def test_the_commit_is_the_default_branchs_even_when_a_tag_has_its_name(self) -> None:
        self.git("tag", "main", self.first)
        head = self.move_the_default_branch()

        self.assertEqual(self.add([ADR]).rests_on[0].commit, head)

    def test_a_new_sprints_first_tasks_are_checked_before_anything_is_made(self) -> None:
        before = [sprint.id for sprint in self.store.list_sprints("p1")]

        with self.assertRaises(InvalidRequestError) as caught:
            Services(self.store).sprints.create_sprint(
                "p1", title="New", initial_tasks=[{"title": "ok", "rests_on": [ADR]}, {"title": "bad", "rests_on": ["docs/nope.md"]}]
            )

        self.assertIn("docs/nope.md does not exist on main", str(caught.exception))
        self.assertEqual([sprint.id for sprint in self.store.list_sprints("p1")], before)
        self.assertEqual(self.store.list_tasks(project_id="p1"), [])
        made = Services(self.store).sprints.create_sprint("p1", title="New", initial_tasks=[{"title": "ok", "rests_on": [ADR]}])
        self.assertEqual(made["tasks_created"], 1)


class HeadingAndRestampTests(_Repo):
    def setUp(self) -> None:
        super().setUp()
        self.api = Services(self.store)

    def test_changing_only_the_heading_keeps_the_commit(self) -> None:
        created = self.api.tasks.create_task("s1", title="T", rests_on=[f"{ADR}#6"])
        self.move_the_default_branch()

        detail = self.api.tasks.update_task_fields(created["id"], updates={"rests_on": [f"{ADR}#7", f"{ADR}#8"]})

        self.assertEqual([(item["heading"], item["commit"]) for item in detail["rests_on"]], [("7", self.first), ("8", self.first)])

    def test_marking_a_document_read_stamps_the_commit_now_and_keeps_the_heading(self) -> None:
        created = self.api.tasks.create_task("s1", title="T", rests_on=[f"{ADR}#6", SPEC])
        head = self.move_the_default_branch()

        detail = self.api.tasks.restamp_document(created["id"], path=ADR, heading="6")

        self.assertEqual(
            [(item["path"], item["heading"], item["commit"]) for item in detail["rests_on"]],
            [(ADR, "6", head), (SPEC, "", self.first)],
        )
        with self.assertRaises(InvalidRequestError) as caught:
            self.api.tasks.restamp_document(created["id"], path=ADR, heading="7")
        self.assertIn("is not a document this task rests on", str(caught.exception))
        self.git("rm", "-q", SPEC)
        self.commit("docs: drop the spec")
        with self.assertRaises(InvalidRequestError) as caught:
            self.api.tasks.restamp_document(created["id"], path=SPEC)
        self.assertIn("does not exist on main", str(caught.exception))

    def test_the_command_marks_one_read(self) -> None:
        task = Mutations(self.store, via="cli").add_task(self.store.get_sprint("s1"), title="T", rests_on=[ADR, SPEC])
        head = self.move_the_default_branch()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["task", "edit", task.id, "--restamp", SPEC, "--db", str(self.db_path)])

        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("Documents: marked as read again", out.getvalue())
        self.assertIn(f"{SPEC} (named at {head[:10]})", out.getvalue())
        self.assertEqual([ref.commit for ref in self.stored(task.id).rests_on], [self.first, head])

    def test_the_dashboard_marks_one_read_and_opens_each_entry_at_its_own_commit(self) -> None:
        import asyncio

        import httpx

        from foreman.api.app import create_dashboard_app

        created = self.api.tasks.create_task("s1", title="T", rests_on=[f"{ADR}#6", f"{ADR}#7"])
        (self.repo / ADR).write_text("# ADR-0041\nChanged.\n", encoding="utf-8")
        head = self.commit("docs: change the ADR")

        async def send(method: str, url: str, **kwargs: object) -> httpx.Response:
            transport = httpx.ASGITransport(app=create_dashboard_app(str(self.db_path)))
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, url, **kwargs)

        marked = asyncio.run(
            send("POST", f"/api/tasks/{created['id']}/documents/restamp", json={"path": ADR, "heading": "7"})
        )
        self.assertEqual(marked.status_code, 200, marked.text)
        self.assertEqual([item["commit"] for item in marked.json()["rests_on"]], [self.first, head])
        six = asyncio.run(send("GET", f"/api/tasks/{created['id']}/documents", params={"path": ADR, "heading": "6"}))
        seven = asyncio.run(send("GET", f"/api/tasks/{created['id']}/documents", params={"path": ADR, "heading": "7"}))
        self.assertEqual((six.json()["commit"], seven.json()["commit"]), (self.first, head))
        self.assertIn("The task layer.", six.json()["text"])
        self.assertIn("Changed.", seven.json()["text"])
        refused = asyncio.run(
            send("POST", f"/api/tasks/{created['id']}/documents/restamp", json={"path": "docs/nope.md"})
        )
        self.assertEqual(refused.status_code // 100, 4)


class StampedProposalTests(_Repo):
    def test_a_proposal_stamps_its_documents_when_it_is_made_not_when_confirmed(self) -> None:
        existing = Mutations(self.store, via="cli").add_task(self.store.get_sprint("s1"), title="Existing", rests_on=[SPEC])
        proposals = Proposals(self.store, via="cli", actor="manager")
        proposal = proposals.create(
            self.project,
            reason="Name what the work rests on.",
            operations=[
                # A commit the manager writes is not taken.
                {"kind": "file_task", "title": "Filed", "rests_on": [{"path": ADR, "commit": "deadbeef"}]},
                {"kind": "add_task", "sprint_id": "s1", "title": "Added", "rests_on": [f"{SPEC}#6.3"]},
                {"kind": "edit_task", "task_id": existing.id, "rests_on": [SPEC, ADR]},
            ],
            proposed_by="manager",
        )
        self.assertEqual(proposal.operations[0]["rests_on"], [{"path": ADR, "heading": "", "commit": self.first}])
        self.move_the_default_branch()

        self.assertEqual(proposals.confirm(proposal.id).state, "confirmed")

        by_title = {task.title: task for task in self.store.list_tasks(project_id="p1")}
        self.assertEqual(by_title["Filed"].rests_on[0].commit, self.first)
        self.assertEqual(by_title["Added"].rests_on[0].commit, self.first)
        self.assertEqual([ref.commit for ref in by_title["Existing"].rests_on], [self.first, self.first])
