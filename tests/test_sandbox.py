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

    def test_a_role_that_runs_nothing_cannot_list_a_command_tool(self) -> None:
        for tool in ("Bash", "Monitor", "PowerShell"):
            with self.subTest(tool=tool), self.assertRaisesRegex(RoleLoadError, "run_scope is none"):
                load_role_text(
                    role_text(agent='run_scope = "none"', tools=f'allowed = ["Read", "{tool}"]'),
                    "r.toml",
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

    def test_a_clone_left_by_a_killed_engine_is_replaced(self) -> None:
        manager = WorktreeManager(self.project())
        left = manager.root / f"{SANDBOX_WORKTREE_PREFIX}T-1"
        manager._clone_without_remote(left, self.head())
        (left / "stale.txt").write_text("old")
        with manager.sandbox(self.task) as box:
            self.assertEqual(box.path, left)
            self.assertFalse((box.path / "stale.txt").exists())

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

    def test_it_is_a_clone_with_no_remote_and_its_own_refs_and_config(self) -> None:
        remote = self.repo.parent / "remote.git"
        git(self.repo.parent, "init", "--bare", str(remote))
        git(self.repo, "remote", "add", "origin", str(remote))
        with WorktreeManager(self.project()).sandbox(self.task) as box:
            self.assertEqual(git(box.path, "remote"), "")
            self.assertTrue((box.path / ".git").is_dir(), "a clone owns its .git; a worktree has a file")
            self.assertEqual(git(box.path, "rev-parse", "--git-common-dir"), ".git")
            self.assertNotIn(str(box.path), git(self.repo, "worktree", "list"))

    def test_a_ref_moved_or_config_changed_in_it_does_not_reach_the_repository(self) -> None:
        head, main = self.head(), git(self.repo, "rev-parse", "refs/heads/main")
        config = (self.repo / ".git" / "config").read_text()
        refs = git(self.repo, "for-each-ref")
        with WorktreeManager(self.project()).sandbox(self.task) as box:
            (box.path / "b.txt").write_text("b\n")
            git(box.path, "add", ".")
            git(box.path, "commit", "-m", "x")
            git(box.path, "branch", "-f", "feat/x", "HEAD")
            git(box.path, "branch", "-f", "main", "HEAD")
            git(box.path, "update-ref", "refs/heads/new", "HEAD")
            git(box.path, "update-ref", "-d", "refs/heads/feat/x")
            git(box.path, "config", "remote.origin.url", "https://example.invalid/x.git")
            git(box.path, "config", "core.hooksPath", "/tmp/hooks")
            git(box.path, "tag", "t-in-sandbox")
            # The step moved nothing the repository has.
            self.assertIsNone(box.check())
            self.assertEqual(self.head(), head)
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/main"), main)
        self.assertEqual((self.repo / ".git" / "config").read_text(), config)
        self.assertEqual(git(self.repo, "for-each-ref"), refs)
        self.assertEqual(git(self.repo, "tag", "--list"), "")

    def test_a_push_from_it_cannot_name_the_repository_as_a_remote(self) -> None:
        # With no remote configured there is no ``origin`` to push to.
        with WorktreeManager(self.project()).sandbox(self.task) as box:
            result = subprocess.run(
                ["git", "push", "origin", "HEAD:refs/heads/leak"],
                cwd=box.path, capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(git(self.repo, "branch", "--list", "leak"), "")

    def test_it_reads_the_repositorys_objects_without_copying_them(self) -> None:
        with WorktreeManager(self.project()).sandbox(self.task) as box:
            alternates = (box.path / ".git" / "objects" / "info" / "alternates").read_text()
            self.assertEqual(Path(alternates.strip()), (self.repo / ".git" / "objects").resolve())
            self.assertEqual(git(box.path, "cat-file", "-t", "HEAD"), "commit")

    def test_its_policy_closes_home_and_the_projects_beside_and_opens_what_it_needs(self) -> None:
        project = self.project(
            worktree_link_paths=["venv"],
            sandbox_allowed_hosts=["pypi.org"],
            sandbox_read_paths=["~/.pyenv", "/opt/tool"],
        )
        with WorktreeManager(project).sandbox(self.task) as box:
            policy = box.policy
            self.assertEqual(policy.allowed_hosts, ("pypi.org",))
            self.assertIn(Path.home().resolve(), policy.deny_roots)
            self.assertIn(self.repo.resolve().parent, policy.deny_roots)
            readable = set(policy.read_paths)
            self.assertIn(box.path.resolve(), readable)
            self.assertIn((self.repo / ".git" / "objects").resolve(), readable)
            self.assertIn((self.repo / "venv").resolve(), readable)
            self.assertIn((Path.home() / ".pyenv").resolve(), readable)
            self.assertIn(Path("/opt/tool"), readable)

    def test_a_moved_branch_is_put_back_and_named(self) -> None:
        # An escape from the sandbox (the clone cannot do this itself).
        before = self.head()
        with WorktreeManager(self.project()).sandbox(self.task) as box:
            git(self.repo, "commit", "--allow-empty", "-m", "moved")
            git(self.repo, "update-ref", "refs/heads/feat/x", "HEAD")
            self.assertNotEqual(self.head(), before)
            violation = box.check()
        self.assertIn("feat/x was at", violation)
        self.assertIn("may not commit to, move or push", violation)
        self.assertEqual(self.head(), before)

    def test_a_deleted_branch_is_put_back(self) -> None:
        before = self.head()
        with WorktreeManager(self.project()).sandbox(self.task) as box:
            git(self.repo, "update-ref", "-d", "refs/heads/feat/x")
            self.assertIn("was deleted", box.check())
        self.assertEqual(self.head(), before)

    def test_a_branch_moved_by_a_killed_step_is_put_back(self) -> None:
        before = self.head()
        with self.assertRaises(EngineShutdown):
            with WorktreeManager(self.project()).sandbox(self.task):
                git(self.repo, "commit", "--allow-empty", "-m", "c")
                git(self.repo, "update-ref", "refs/heads/feat/x", "HEAD")
                raise EngineShutdown("stop")
        self.assertEqual(self.head(), before)

    def test_git_works_in_a_sandbox_of_a_repository_with_a_remote(self) -> None:
        remote = self.repo.parent / "remote.git"
        git(self.repo.parent, "init", "--bare", str(remote))
        git(self.repo, "remote", "add", "origin", str(remote))
        with WorktreeManager(self.project()).sandbox(self.task) as box:
            for command in (["status", "--short"], ["log", "--oneline", "-1"], ["diff", "--stat", "HEAD"]):
                git(box.path, *command)


class StaleSandboxTests(SandboxCase):
    def test_sandboxes_a_killed_engine_left_are_removed_when_an_engine_starts(self) -> None:
        project = self.project()
        manager = WorktreeManager(project)
        left = manager.root / f"{SANDBOX_WORKTREE_PREFIX}T-1"
        git(self.repo, "worktree", "add", "--detach", str(left), "main")
        # A clone a killed engine left (the kind a sandbox is now).
        clone = manager.root / f"{SANDBOX_WORKTREE_PREFIX}T-2"
        manager._clone_without_remote(clone, self.head())
        # A directory a person put there is not ours and stays.
        stranger = manager.root / f"{SANDBOX_WORKTREE_PREFIX}other"
        stranger.mkdir()
        (stranger / "keep").write_text("mine")

        removed = manager.remove_stale_sandboxes()

        self.assertEqual(sorted(removed), sorted([left, clone]))
        self.assertFalse(left.exists())
        self.assertFalse(clone.exists())
        self.assertNotIn("T-1", git(self.repo, "worktree", "list"))
        self.assertTrue((stranger / "keep").exists())

    def test_the_orchestrator_removes_them_at_the_start_of_a_pass(self) -> None:
        from foreman.engine.orchestrator import ForemanOrchestrator
        from foreman.store import ForemanStore

        project = self.project()
        store = ForemanStore(self.repo.parent / "f.db")
        self.addCleanup(store.close)
        store.initialize()
        store.save_project(project)
        left = WorktreeManager(project).root / f"{SANDBOX_WORKTREE_PREFIX}T-1"
        git(self.repo, "worktree", "add", "--detach", str(left), "main")
        orchestrator = ForemanOrchestrator(store)

        # An idle wake does no housekeeping; the pass an engine starts with does.
        orchestrator.run_project(project.id, maintenance=False)
        self.assertTrue(left.exists())
        orchestrator.run_project(project.id)
        self.assertFalse(left.exists())


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
            # What a step that got out of its sandbox would do: the clone cannot.
            git(self.repo, "commit", "--allow-empty", "-m", "sneaky")
            git(self.repo, "update-ref", "refs/heads/feat/x", "HEAD")

        result = self.run_step(FakeRunner(act))

        self.assertEqual((result.outcome, result.status), ("error", "failed"))
        self.assertIn("changed the task's branch", result.detail)
        self.assertIn("feat/x", result.detail)
        self.assertEqual(self.head(), before)
        self.assertIsNone(result.record)

    def test_the_runner_is_given_the_policy_and_a_clone(self) -> None:
        runner = FakeRunner(lambda config: None)
        self.run_step(runner, self.project(sandbox_allowed_hosts=["pypi.org"]))
        config = runner.configs[0]
        self.assertIsNotNone(config.sandbox)
        self.assertEqual(config.sandbox.allowed_hosts, ("pypi.org",))
        self.assertIn(config.working_dir.resolve(), config.sandbox.read_paths)
        # No git settings in the step's environment: the sandbox is the guard.
        self.assertNotIn("GIT_CONFIG_PARAMETERS", config.env)

    def test_a_step_that_is_not_sandboxed_is_given_no_policy(self) -> None:
        runner = FakeRunner(lambda config: None)
        self.step_runner(runner).execute(
            role=load_role_text(role_text(), "r.toml"), project=self.project(), task=self.task,
            workflow_step="develop", prompt="p", session_id=None, carried_output=None, model="m",
        )
        self.assertIsNone(runner.configs[0].sandbox)

    def test_a_machine_that_cannot_sandbox_fails_the_step_with_the_reason(self) -> None:
        from foreman.runner import ClaudeCodeRunner

        runner = ClaudeCodeRunner(
            which=lambda name: None if name in ("bwrap", "socat") else f"/usr/bin/{name}",
            popen_factory=lambda *a, **k: self.fail("the step must never start without its sandbox"),
        )
        result = self.run_step(runner)

        self.assertEqual((result.outcome, result.status), ("error", "failed"))
        self.assertEqual(result.failure_type, "preflight")
        self.assertIn("bwrap and socat are not installed", result.detail)
        self.assertIn("never run without it", result.detail)

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

    def test_a_role_that_runs_nothing_is_refused_bash_whatever_it_lists(self) -> None:
        role = load_role_text(
            role_text(agent='run_scope = "none"', tools='allowed = ["Read"]'), "r.toml"
        )
        bare = load_role_text(role_text(agent='run_scope = "none"'), "r.toml")
        for each in (role, bare):
            runner = FakeRunner(lambda config: None)
            self.step_runner(runner).execute(
                role=each, project=self.project(), task=self.task, workflow_step="x",
                prompt="p", session_id=None, carried_output=None, model="m",
            )
            for tool in ("Bash", "Monitor", "PowerShell"):
                self.assertIn(tool, runner.configs[0].disallowed_tools)
        branch = FakeRunner(lambda config: None)
        self.step_runner(branch).execute(
            role=load_role_text(role_text(), "r.toml"), project=self.project(), task=self.task,
            workflow_step="x", prompt="p", session_id=None, carried_output=None, model="m",
        )
        self.assertNotIn("Bash", branch.configs[0].disallowed_tools)

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
