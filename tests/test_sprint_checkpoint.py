"""A finished sprint's checkpoint (spec 6.4): a tag, and a note where asked."""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
from pathlib import Path
import subprocess
import tempfile
import unittest

from foreman.cli import main
from foreman.domain.models import Event, Project, Run, Sprint, Task
from foreman.domain.settings import ProjectSettings, SettingsError
from foreman.engine.sprints import SprintFlow
from foreman.history.records import RunRecords
from foreman.notifications.delivery import NotificationDispatcher
from foreman.mutations import Mutations
from foreman.mutations.checkpoint import SprintCheckpoints, tag_name
from foreman.services.sprints import SprintService
from foreman.store import ForemanStore


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


class SprintCheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        for args in (("init", "-q"), ("checkout", "-q", "-b", "main"),
                     ("config", "user.email", "t@example.com"), ("config", "user.name", "T")):
            git(self.repo, *args)
        (self.repo / "README.md").write_text("# r\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")
        self.store = ForemanStore(root / "foreman.db")
        self.store.initialize()
        self.addCleanup(self.store.close)

    def project(self, **settings: object) -> Project:
        project = Project(
            id="p", name="P", repo_path=str(self.repo), workflow_id="development",
            default_branch="main", settings=dict(settings),
        )
        self.store.save_project(project)
        return project

    def sprint(self, title: str = "Weight of evidence") -> Sprint:
        sprint = Sprint(id="s", project_id="p", title=title, goal="Claims carry their evidence.", status="active")
        self.store.save_sprint(sprint)
        self.store.save_task(Task(id="t1", sprint_id="s", project_id="p", title="Claim card", status="done", task_key="P-1"))
        self.store.save_task(Task(id="t2", sprint_id="s", project_id="p", title="Dropped idea", status="cancelled", task_key="P-2"))
        return sprint

    def finish(self) -> Sprint:
        return Mutations(self.store, via="cli").transition_sprint(self.store.get_sprint("s"), "completed")

    def events(self, kind: str) -> list[Event]:
        return self.store.list_sprint_events("s", event_types=[kind])

    def test_a_finished_sprint_tags_the_default_branch(self) -> None:
        self.project()
        self.sprint()
        head = git(self.repo, "rev-parse", "main")
        sprint = self.finish()
        day = datetime.fromisoformat(sprint.completed_at).astimezone(timezone.utc).strftime("%Y%m%d")
        tag = f"checkpoint-{day}-weight-of-evidence"
        self.assertEqual(git(self.repo, "rev-parse", f"{tag}^{{commit}}"), head)
        # An annotated tag, saying which sprint it marks.
        self.assertEqual(git(self.repo, "cat-file", "-t", tag), "tag")
        self.assertIn("Sprint finished: Weight of evidence", git(self.repo, "tag", "-n1", tag))
        (event,) = self.events("engine.checkpoint")
        self.assertEqual(event.payload["tag"], tag)
        self.assertEqual(event.payload["sha"], head)
        self.assertIsNone(event.payload["note_path"])
        self.assertEqual(event.payload["completed_at"], sprint.completed_at)
        # No note unless the project asks for one: main has not moved.
        self.assertEqual(git(self.repo, "rev-parse", "main"), head)
        # The sprint page names it.
        checkpoint = SprintService(self.store).get_sprint("s")["checkpoint"]
        self.assertEqual(checkpoint, {"tag": tag, "sha": head, "note_path": None, "problem": None})

    def test_the_note_is_committed_on_the_default_branch_before_the_tag(self) -> None:
        self.project(write_checkpoint_notes=True)
        self.sprint()
        # An agent filed a follow-up while working on P-1.
        self.store.save_sprint(Sprint(id="later", project_id="p", title="Later", status="planned"))
        self.store.save_task(Task(id="t3", sprint_id="later", project_id="p", title="Rank the evidence", status="triage", task_key="P-3"))
        self.store.save_run(Run(id="r1", task_id="t1", project_id="p", role_id="developer", workflow_step="develop",
                                agent_backend="claude_code", status="completed"))
        self.store.save_event(Event(id="e1", run_id="r1", task_id="t1", project_id="p", event_type="engine.task_created",
                                    timestamp="2026-01-01T00:00:00Z", payload={"task_id": "t3", "title": "Rank the evidence"}))
        before = git(self.repo, "rev-parse", "main")
        self.finish()
        (event,) = self.events("engine.checkpoint")
        tag, note = event.payload["tag"], event.payload["note_path"]
        self.assertEqual(note, f"docs/checkpoints/{tag}.md")
        head = git(self.repo, "rev-parse", "main")
        self.assertNotEqual(head, before)
        self.assertEqual(git(self.repo, "rev-parse", f"{head}^"), before)
        self.assertEqual(git(self.repo, "rev-parse", f"{tag}^{{commit}}"), head)
        text = git(self.repo, "show", f"{tag}:{note}")
        self.assertIn("# Weight of evidence", text)
        self.assertIn(f"- Tag: `{tag}`", text)
        self.assertIn("## Goal\n\nClaims carry their evidence.", text)
        self.assertIn("## Done\n\n- P-1: Claim card", text)
        self.assertIn("## Cancelled\n\n- P-2: Dropped idea", text)
        self.assertIn("## Follow-ups\n\n- P-3: Rank the evidence (triage)", text)
        # The checkout on main shows the note, as it shows a merge (ADR-0031).
        self.assertTrue((self.repo / note).is_file())
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_a_second_sprint_of_the_same_name_on_the_same_day_gets_its_own_tag(self) -> None:
        project = self.project()
        sprint = self.sprint()
        sprint.status, sprint.completed_at = "completed", "2026-11-20T17:00:00+00:00"
        self.store.save_sprint(sprint)
        first = SprintCheckpoints(self.store).record(project, sprint)
        sprint.completed_at = "2026-11-20T18:00:00+00:00"
        self.store.save_sprint(sprint)
        second = SprintCheckpoints(self.store).record(project, sprint)
        self.assertEqual(first.tag, "checkpoint-20261120-weight-of-evidence")
        self.assertEqual(second.tag, "checkpoint-20261120-weight-of-evidence-2")

    def test_the_same_completion_is_checkpointed_once(self) -> None:
        project = self.project()
        sprint = self.finish_later()
        first = SprintCheckpoints(self.store).record(project, sprint)
        again = SprintCheckpoints(self.store).record(project, sprint)
        self.assertEqual(first, again)
        self.assertEqual(len(self.events("engine.checkpoint")), 1)

    def finish_later(self) -> Sprint:
        sprint = self.sprint()
        sprint.status, sprint.completed_at = "completed", "2026-11-20T17:00:00+00:00"
        self.store.save_sprint(sprint)
        return sprint

    def test_a_sprint_that_cannot_be_tagged_stays_finished_and_says_why(self) -> None:
        self.project()
        self.sprint()
        git(self.repo, "branch", "-m", "main", "trunk")
        sprint = self.finish()
        self.assertEqual(sprint.status, "completed")
        self.assertEqual(self.store.get_sprint("s").status, "completed")
        (event,) = self.events("engine.checkpoint_failed")
        self.assertEqual(event.payload["reason"], "The repository has no branch 'main' to tag.")
        self.assertEqual(self.events("engine.checkpoint"), [])
        self.assertEqual(git(self.repo, "tag"), "")
        checkpoint = SprintService(self.store).get_sprint("s")["checkpoint"]
        self.assertEqual(checkpoint["problem"], "The repository has no branch 'main' to tag.")

    def test_the_tag_and_the_note_are_pushed_where_merges_are(self) -> None:
        remote = self.repo.parent / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        git(self.repo, "remote", "add", "origin", str(remote))
        git(self.repo, "push", "-q", "origin", "main")
        self.project(write_checkpoint_notes=True, merge_push_remote="origin")
        self.sprint()
        self.finish()
        (event,) = self.events("engine.checkpoint")
        tag = event.payload["tag"]
        self.assertEqual(git(remote, "rev-parse", "main"), event.payload["sha"])
        self.assertEqual(git(remote, "rev-parse", f"{tag}^{{commit}}"), event.payload["sha"])
        pushed = [e.payload for e in self.events("engine.push")]
        self.assertEqual([("branch" in p, "tag" in p) for p in pushed], [(True, False), (False, True)])

    def test_a_proposal_tags_after_its_changes_are_written(self) -> None:
        self.project()
        self.sprint()
        mutations = Mutations(self.store, via="manager", defer_side_effects=True)
        mutations.transition_sprint(self.store.get_sprint("s"), "completed")
        self.assertEqual(git(self.repo, "tag"), "")
        warnings = [run() for run in mutations.deferred]
        self.assertEqual(warnings, [None])
        self.assertEqual(len(self.events("engine.checkpoint")), 1)

    def test_a_sprint_foreman_finishes_is_tagged_the_same_way(self) -> None:
        project = self.project(sprint_completion="auto")
        sprint = self.sprint()
        records = RunRecords(self.store, NotificationDispatcher(self.store))
        flow = SprintFlow(self.store, records, lambda: datetime(2026, 11, 23, 12, tzinfo=timezone.utc))
        self.assertEqual(flow.resolve(project, sprint), "idle")
        (event,) = self.events("engine.checkpoint")
        self.assertEqual(event.payload["tag"], "checkpoint-20261123-weight-of-evidence")
        self.assertEqual(git(self.repo, "rev-parse", "checkpoint-20261123-weight-of-evidence^{commit}"), git(self.repo, "rev-parse", "main"))

    def test_the_note_setting_is_true_or_false(self) -> None:
        self.assertFalse(ProjectSettings.from_raw({}).write_checkpoint_notes)
        self.assertTrue(ProjectSettings.from_raw({"write_checkpoint_notes": True}).write_checkpoint_notes)
        with self.assertRaises(SettingsError):
            ProjectSettings.from_raw({"write_checkpoint_notes": "yes"})

    def test_the_cli_says_what_it_tagged(self) -> None:
        self.project(write_checkpoint_notes=True)
        self.sprint()
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["sprint", "complete", "s", "--db", str(self.store.db_path)])
        self.assertEqual(code, 0)
        (event,) = self.events("engine.checkpoint")
        self.assertIn(f"Tagged: {event.payload['tag']} at {event.payload['sha'][:7]}", out.getvalue())
        self.assertIn(f"Note: {event.payload['note_path']}", out.getvalue())

    def test_the_tag_name_is_the_day_and_the_title(self) -> None:
        sprint = Sprint(id="sprint-62", project_id="p", title="Sprint 62: finish what's there!", status="completed")
        moment = datetime(2026, 11, 23, 23, 30, tzinfo=timezone.utc)
        self.assertEqual(tag_name(sprint, moment), "checkpoint-20261123-sprint-62-finish-what-s-there")
        untitled = Sprint(id="sprint-x", project_id="p", title="!!!", status="completed")
        self.assertEqual(tag_name(untitled, moment), "checkpoint-20261123-sprint-x")


if __name__ == "__main__":
    unittest.main()
