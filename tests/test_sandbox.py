"""A role's run scope, and the sandbox a ``sandbox`` step runs in (ADR-0041 section 5)."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from foreman.data import ROLES_DIR
from foreman.definitions.roles import RoleLoadError, load_role, load_role_text, load_roles
from foreman.domain.models import Project, Task
from foreman.engine.agent_step import AgentStepRunner
from foreman.runner.base import AgentEvent
from foreman.runner.process import EngineShutdown
from foreman.repo.worktrees import SANDBOX_WORKTREE_PREFIX, WorktreeError, WorktreeManager


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stdout}{result.stderr}")
    return result.stdout.strip()


ROLE = """
[role]
id = "r"
name = "R"
description = "d"

[agent]
backend = "claude_code"
model = "m"
session_persistence = false
permission_mode = "bypassPermissions"
{agent}

[agent.tools]
{tools}

[prompt]
template = "go"

[completion]
marker = "DONE"
timeout_minutes = 1
max_cost_usd = 1.0
"""


def role_text(agent: str = "", tools: str = "") -> str:
    return ROLE.format(agent=agent, tools=tools)


class RunScopeLoaderTests(unittest.TestCase):
    def test_each_scope_is_accepted(self) -> None:
        for scope in ("none", "sandbox", "branch"):
            role = load_role_text(role_text(agent=f'run_scope = "{scope}"'), "r.toml")
            self.assertEqual(role.run_scope, scope)

    def test_a_role_without_it_runs_where_it_always_ran(self) -> None:
        self.assertEqual(load_role_text(role_text(), "r.toml").run_scope, "branch")

    def test_another_value_is_refused(self) -> None:
        with self.assertRaisesRegex(RoleLoadError, "agent.run_scope must be one of none, sandbox, branch"):
            load_role_text(role_text(agent='run_scope = "container"'), "r.toml")

    def test_a_role_that_runs_nothing_cannot_list_bash(self) -> None:
        with self.assertRaisesRegex(RoleLoadError, "run_scope is none"):
            load_role_text(
                role_text(agent='run_scope = "none"', tools='allowed = ["Read", "Bash"]'), "r.toml"
            )

    def test_only_the_code_reviewer_is_sandboxed_among_the_shipped_roles(self) -> None:
        roles = load_roles(ROLES_DIR)
        self.assertEqual(roles["code_reviewer"].run_scope, "sandbox")
        self.assertIn("Bash", roles["code_reviewer"].agent.tools.allowed)
        self.assertNotIn("Bash", roles["code_reviewer"].agent.tools.disallowed)
        self.assertEqual(roles["developer"].run_scope, "branch")

    def test_the_reviewer_prompt_asks_for_checks_and_screenshots(self) -> None:
        template = load_role(ROLES_DIR / "code_reviewer.toml").prompt_template
        for needle in ("test command", "1440", "390", "Looking at a page in a review", "not seen in a browser", "never bind a fixed port", "cite what you ran"):
            self.assertIn(needle, template)


class SandboxCase(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init")
        git(self.repo, "checkout", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "T")
        (self.repo / ".gitignore").write_text(".foreman/\nvenv/\n", encoding="utf-8")
        (self.repo / "a.txt").write_text("a\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "init")
        git(self.repo, "branch", "feat/x")
        (self.repo / "venv").mkdir()
        (self.repo / "venv" / "marker").write_text("tooling", encoding="utf-8")
        self.task = Task(
            id="t1", sprint_id="s", project_id="p", title="T", task_key="T-1", branch_name="feat/x"
        )

    def project(self, **settings: object) -> Project:
        return Project(
            id="p", name="P", repo_path=str(self.repo), workflow_id="development",
            default_branch="main", settings=dict(settings),
        )

    def head(self) -> str:
        return git(self.repo, "rev-parse", "refs/heads/feat/x")

    def sandboxes(self, project: Project) -> list[str]:
        return [
            entry.slug for entry in WorktreeManager(project).list()
            if entry.slug.startswith(SANDBOX_WORKTREE_PREFIX)
        ]


class SandboxWorktreeTests(SandboxCase):
    def test_it_is_detached_at_the_commit_and_prepared_like_a_task_worktree(self) -> None:
        project = self.project(
            worktree_link_paths=["venv"], worktree_setup_command="echo setup > setup.txt"
        )
        with WorktreeManager(project).sandbox(self.task) as box:
            self.assertEqual(git(box.path, "rev-parse", "HEAD"), self.head())
            self.assertEqual(git(box.path, "branch", "--show-current"), "")
            self.assertTrue((box.path / "venv" / "marker").exists())
            self.assertEqual((box.path / "setup.txt").read_text().strip(), "setup")
            self.assertIsNone(box.check())
        self.assertFalse(box.path.exists())
        self.assertEqual(self.sandboxes(project), [])

    def test_it_is_removed_when_the_step_raises(self) -> None:
        project = self.project()
        manager = WorktreeManager(project)
        with self.assertRaises(RuntimeError):
            with manager.sandbox(self.task) as box:
                raise RuntimeError("boom")
        self.assertFalse(box.path.exists())
        self.assertEqual(self.sandboxes(project), [])

    def test_it_is_removed_when_setup_fails(self) -> None:
        project = self.project(worktree_setup_command="exit 3")
        with self.assertRaisesRegex(WorktreeError, "exit code 3"):
            with WorktreeManager(project).sandbox(self.task):
                self.fail("the step must not start")
        self.assertEqual(self.sandboxes(project), [])

    def test_a_leftover_from_a_killed_engine_is_replaced(self) -> None:
        project = self.project()
        manager = WorktreeManager(project)
        with self.assertRaises(RuntimeError):
            with manager.sandbox(self.task) as box:
                # A copy cut off mid-step is a registered tree that stays.
                git(self.repo, "worktree", "add", "--detach", str(box.path.with_name("x")), "main")
                raise RuntimeError
        left = manager.root / f"{SANDBOX_WORKTREE_PREFIX}T-1"
        git(self.repo, "worktree", "add", "--detach", str(left), "main")
        with manager.sandbox(self.task) as box:
            self.assertEqual(git(box.path, "rev-parse", "HEAD"), self.head())

    def test_a_task_without_a_branch_has_nothing_to_open(self) -> None:
        task = Task(id="t2", sprint_id="s", project_id="p", title="T", branch_name=None)
        with self.assertRaisesRegex(WorktreeError, "no branch"):
            with WorktreeManager(self.project()).sandbox(task):
                pass

    def test_a_commit_in_the_sandbox_leaves_the_branch_alone(self) -> None:
        before = self.head()
        with WorktreeManager(self.project()).sandbox(self.task) as box:
            (box.path / "b.txt").write_text("b\n")
            git(box.path, "add", ".")
            git(box.path, "commit", "-m", "in the sandbox")
            self.assertIsNone(box.check())
        self.assertEqual(self.head(), before)

    def test_a_moved_branch_is_put_back_and_named(self) -> None:
        before = self.head()
        with WorktreeManager(self.project()).sandbox(self.task) as box:
            (box.path / "b.txt").write_text("b\n")
            git(box.path, "add", ".")
            git(box.path, "commit", "-m", "x")
            git(box.path, "branch", "-f", "feat/x", "HEAD")
            self.assertNotEqual(self.head(), before)
            violation = box.check()
        self.assertIn("feat/x was at", violation)
        self.assertIn("may not commit to, move or push", violation)
        self.assertEqual(self.head(), before)

    def test_a_deleted_branch_is_put_back(self) -> None:
        before = self.head()
        with WorktreeManager(self.project()).sandbox(self.task) as box:
            git(box.path, "update-ref", "-d", "refs/heads/feat/x")
            self.assertIn("was deleted", box.check())
        self.assertEqual(self.head(), before)

    def test_a_branch_moved_by_a_killed_step_is_put_back(self) -> None:
        before = self.head()
        with self.assertRaises(EngineShutdown):
            with WorktreeManager(self.project()).sandbox(self.task) as box:
                (box.path / "c").write_text("c")
                git(box.path, "add", ".")
                git(box.path, "commit", "-m", "c")
                git(box.path, "update-ref", "refs/heads/feat/x", "HEAD")
                raise EngineShutdown("stop")
        self.assertEqual(self.head(), before)

    def test_a_push_goes_nowhere(self) -> None:
        remote = self.repo.parent / "remote.git"
        git(self.repo.parent, "init", "--bare", str(remote))
        git(self.repo, "remote", "add", "origin", str(remote))
        with WorktreeManager(self.project()).sandbox(self.task) as box:
            import os

            result = subprocess.run(
                ["git", "push", "origin", "HEAD:refs/heads/leak"],
                cwd=box.path, env={**os.environ, **box.env}, capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(git(remote, "branch", "--list"), "")

    def test_git_works_in_a_sandbox_of_a_repository_with_a_remote(self) -> None:
        # The push block must not break every other git command: git before
        # 2.31 refuses the whole GIT_CONFIG_PARAMETERS variable when an entry
        # is written in the newer 'key'='value' form (2026-11-25, git 2.25).
        remote = self.repo.parent / "remote.git"
        git(self.repo.parent, "init", "--bare", str(remote))
        git(self.repo, "remote", "add", "origin", str(remote))
        with WorktreeManager(self.project()).sandbox(self.task) as box:
            import os

            env = {**os.environ, **box.env}
            for command in (["status", "--short"], ["log", "--oneline", "-1"], ["diff", "--stat", "HEAD"]):
                result = subprocess.run(
                    ["git", *command], cwd=box.path, env=env, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, f"git {' '.join(command)}: {result.stderr}")
            pushurl = subprocess.run(
                ["git", "config", "remote.origin.pushurl"],
                cwd=box.path, env=env, capture_output=True, text=True,
            )
            self.assertIn("/nonexistent/", pushurl.stdout)


class FakeRunner:
    def __init__(self, act) -> None:
        self.act = act
        self.configs: list = []

    def run(self, config):
        self.configs.append(config)
        yield AgentEvent("agent.session", {"session_id": "s"})
        self.act(config)
        yield AgentEvent(
            "agent.completed",
            {"cost_usd": 0.0, "message": "APPROVE"},
        )


class SandboxedStepTests(SandboxCase):
    def step_runner(self, runner) -> AgentStepRunner:
        return AgentStepRunner(
            agent_executor=None,
            agent_runners={"claude_code": runner},
            leases=None,
            records=None,
            runner_sleep=None,
            utc_now=lambda: None,
            heartbeat_seconds=0,
            poll_commands=lambda _id: None,
        )

    def run_step(self, runner, project=None):
        role = load_roles(ROLES_DIR)["code_reviewer"]
        project = project or self.project()
        return self.step_runner(runner).execute(
            role=role, project=project, task=self.task, workflow_step="review",
            prompt="p", session_id=None, carried_output=None, model="m",
        )

    def test_it_runs_in_the_sandbox_and_removes_it_after_success(self) -> None:
        seen: list[Path] = []
        runner = FakeRunner(lambda config: seen.append(config.working_dir))
        result = self.run_step(runner)

        self.assertEqual(result.status, "completed")
        self.assertTrue(seen[0].name.startswith(SANDBOX_WORKTREE_PREFIX))
        self.assertFalse(seen[0].exists())
        self.assertNotIn("GIT_CONFIG_PARAMETERS", runner.configs[0].env)  # no remote to block

    def test_it_removes_the_sandbox_after_a_failure(self) -> None:
        seen: list[Path] = []

        def act(config) -> None:
            seen.append(config.working_dir)
            raise RuntimeError("the agent broke")

        result = self.run_step(FakeRunner(act))

        self.assertEqual(result.outcome, "error")
        self.assertFalse(seen[0].exists())
        self.assertEqual(self.sandboxes(self.project()), [])

    def test_it_removes_the_sandbox_when_the_step_is_killed(self) -> None:
        seen: list[Path] = []

        def act(config) -> None:
            seen.append(config.working_dir)
            raise EngineShutdown("engine stopped")

        with self.assertRaises(EngineShutdown):
            self.run_step(FakeRunner(act))
        self.assertTrue(seen)
        self.assertFalse(seen[0].exists())
        self.assertEqual(self.sandboxes(self.project()), [])

    def test_a_step_that_moves_the_branch_fails_with_the_reason(self) -> None:
        before = self.head()

        def act(config) -> None:
            Path(config.working_dir, "b.txt").write_text("b")
            git(config.working_dir, "add", ".")
            git(config.working_dir, "commit", "-m", "sneaky")
            git(config.working_dir, "update-ref", "refs/heads/feat/x", "HEAD")

        result = self.run_step(FakeRunner(act))

        self.assertEqual((result.outcome, result.status), ("error", "failed"))
        self.assertIn("changed the task's branch", result.detail)
        self.assertIn("feat/x", result.detail)
        self.assertEqual(self.head(), before)
        self.assertIsNone(result.record)

    def test_a_step_that_only_commits_in_the_sandbox_is_not_a_violation(self) -> None:
        def act(config) -> None:
            Path(config.working_dir, "b.txt").write_text("b")
            git(config.working_dir, "add", ".")
            git(config.working_dir, "commit", "-m", "scratch")

        before = self.head()
        result = self.run_step(FakeRunner(act))
        self.assertEqual(result.status, "completed")
        self.assertEqual(self.head(), before)

    def test_a_sandbox_that_cannot_be_made_fails_the_step_with_the_reason(self) -> None:
        runner = FakeRunner(lambda config: None)
        result = self.run_step(runner, self.project(worktree_setup_command="exit 2"))

        self.assertEqual((result.outcome, result.status), ("error", "failed"))
        self.assertIn("sandbox for this step could not be made", result.detail)
        self.assertEqual(runner.configs, [])

    def test_a_role_without_a_scope_runs_in_the_task_worktree(self) -> None:
        role = load_role_text(role_text(), "r.toml")
        seen: list[Path] = []
        runner = FakeRunner(lambda config: seen.append(config.working_dir))
        self.step_runner(runner).execute(
            role=role, project=self.project(), task=self.task, workflow_step="develop",
            prompt="p", session_id=None, carried_output=None, model="m",
        )
        self.assertEqual(seen, [self.repo])
        self.assertNotIn("GIT_CONFIG_PARAMETERS", runner.configs[0].env)


if __name__ == "__main__":
    unittest.main()
