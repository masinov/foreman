"""After a merge the engine pushes the default branch, when the project names a remote."""

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

from foreman.engine.results import AgentExecutionResult
from foreman.models import Task
from foreman.orchestrator import ForemanOrchestrator
from foreman.settings import HOST_LEVEL_SETTINGS, ProjectSettings, SettingsError
from foreman.store import ForemanStore

from engine_support import OrchestratorTestCase, ScriptedAgentExecutor


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=path, capture_output=True, text=True, check=True
    ).stdout.strip()


class PushAfterMergeTests(OrchestratorTestCase):
    def _run_one_task(self, *, remote_setting: str | None, add_remote: bool):
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        bare = repo_path.parent / "origin.git"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        if add_remote:
            _git(repo_path, "remote", "add", "origin", str(bare))

        store = ForemanStore(db_path)
        self.addCleanup(store.close)
        store.initialize()
        project, _, task = self.seed_project(store, repo_path=repo_path)
        if remote_setting is not None:
            project.settings["merge_push_remote"] = remote_setting
            store.save_project(project)

        def developer(*, task: Task, prompt: str, carried_output: str | None) -> AgentExecutionResult:
            work = self.work_dir(task, repo_path)
            self.write_text(work / "feature.txt", "implemented\n")
            self.write_text(work / "ready.txt", "ready\n")
            self.commit_all(work, "feat: implement")
            return AgentExecutionResult(outcome="done", detail="Implemented.")

        executor = ScriptedAgentExecutor(
            {
                ("developer", 1): developer,
                ("code_reviewer", 1): lambda **_: AgentExecutionResult(outcome="approve", detail="APPROVE"),
            }
        )
        ForemanOrchestrator(
            store, roles=self.roles, workflows=self.workflows, agent_executor=executor
        ).run_project(project.id)
        events = {e.event_type: e for e in store.list_events(task_id=task.id)}
        return repo_path, bare, store.get_task(task.id), events

    def test_the_merge_is_pushed_to_the_named_remote(self) -> None:
        repo_path, bare, task, events = self._run_one_task(remote_setting="origin", add_remote=True)

        self.assertEqual(task.status, "done")
        self.assertEqual(_git(bare, "rev-parse", "refs/heads/main"), _git(repo_path, "rev-parse", "main"))
        self.assertEqual(events["engine.push"].payload["remote"], "origin")
        self.assertNotIn("engine.push_failed", events)

    def test_nothing_is_pushed_unless_a_remote_is_named(self) -> None:
        _, bare, task, events = self._run_one_task(remote_setting=None, add_remote=True)

        self.assertEqual(task.status, "done")
        self.assertEqual(_git(bare, "for-each-ref"), "")
        self.assertNotIn("engine.push", events)

    def test_a_failed_push_is_recorded_and_the_merge_stands(self) -> None:
        repo_path, _, task, events = self._run_one_task(remote_setting="origin", add_remote=False)

        self.assertEqual(task.status, "done")
        self.assertIn("feature.txt", _git(repo_path, "ls-tree", "-r", "--name-only", "main"))
        failed = events["engine.push_failed"]
        self.assertEqual(failed.payload["remote"], "origin")
        self.assertTrue(failed.payload["error"])


class PushRemoteSettingTests(unittest.TestCase):
    def test_it_is_a_host_level_setting(self) -> None:
        self.assertIn("merge_push_remote", HOST_LEVEL_SETTINGS)

    def test_it_is_off_by_default(self) -> None:
        self.assertEqual(ProjectSettings.from_raw({}).merge_push_remote, "")

    def test_it_must_be_a_remote_name_not_a_url_or_an_option(self) -> None:
        self.assertEqual(ProjectSettings.from_raw({"merge_push_remote": "origin"}).merge_push_remote, "origin")
        for bad in ("--mirror", "https://example.com/x.git", "a b", "-o"):
            with self.assertRaises(SettingsError):
                ProjectSettings.from_raw({"merge_push_remote": bad})


if __name__ == "__main__":
    unittest.main()
