"""Coverage for the per-task git worktrees Foreman owns.

The engine never checks a branch out in the operator's repository any more.
These tests pin the layout, the create/reuse/remove lifecycle, the refusal
paths, and the pruning policy that keeps the worktree root from growing one
checkout per finished task.
"""

from __future__ import annotations

from pathlib import Path
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest

from foreman.migrations import MIGRATIONS
from foreman.models import Event, Project, Run, Sprint, Task
from foreman.orchestrator import ForemanOrchestrator, OrchestratorError
from foreman.runner.base import AgentEvent, AgentRunConfig
from foreman.store import ForemanStore
from foreman.git import is_worktree_clean
from foreman.worktrees import (
    DEFAULT_WORKTREE_ROOT,
    INTEGRATION_WORKTREE_NAME,
    SETUP_MARKER_NAME,
    WorktreeError,
    WorktreeManager,
    enforce_worktree_limit,
    prune_project_worktrees,
    task_slug,
    worktree_root,
)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed in {repo}\n{result.stdout}\n{result.stderr}"
        )
    return result


class WorktreeManagerTests(unittest.TestCase):
    """The manager creates, reuses, removes, and lists Foreman-owned trees."""

    def workspace(self, *, ignore_foreman: bool = True) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo = Path(temp_dir.name) / "repo"
        repo.mkdir()
        git(repo, "init")
        git(repo, "checkout", "-b", "main")
        git(repo, "config", "user.email", "worktree-tests@example.com")
        git(repo, "config", "user.name", "Worktree Tests")
        (repo / "README.md").write_text("# repo\n", encoding="utf-8")
        if ignore_foreman:
            (repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "chore: initial commit")
        return repo

    def project(self, repo: Path, **settings: object) -> Project:
        return Project(
            id="p1",
            name="Worktrees",
            repo_path=str(repo),
            workflow_id="development",
            default_branch="main",
            settings=dict(settings),
        )

    def task(self, *, task_key: str = "WT-1", branch: str | None = "feat/wt-1") -> Task:
        return Task(
            id="task-1",
            sprint_id="s1",
            project_id="p1",
            title="Implement the thing",
            task_key=task_key,
            branch_name=branch,
        )

    # ── Layout ──────────────────────────────────────────────────────────

    def test_default_root_lives_inside_the_ignored_context_directory(self) -> None:
        repo = self.workspace()
        project = self.project(repo)

        self.assertEqual(worktree_root(project), repo / DEFAULT_WORKTREE_ROOT)
        self.assertEqual(
            WorktreeManager(project).path_for(self.task()), repo / DEFAULT_WORKTREE_ROOT / "WT-1"
        )

    def test_worktree_root_setting_relocates_the_layout(self) -> None:
        repo = self.workspace()
        with tempfile.TemporaryDirectory() as elsewhere:
            project = self.project(repo, worktree_root=elsewhere)
            manager = WorktreeManager(project)

            path = manager.ensure(self.task())

            self.assertEqual(path, Path(elsewhere) / "WT-1")
            self.assertTrue((path / "README.md").is_file())

    def test_slug_prefers_the_task_key_and_never_collides_with_integration(self) -> None:
        self.assertEqual(task_slug(self.task(task_key="FOR-42")), "FOR-42")
        self.assertEqual(task_slug(self.task(task_key="")), "task-1")
        self.assertEqual(
            task_slug(self.task(task_key=INTEGRATION_WORKTREE_NAME)), "task-1"
        )
        self.assertEqual(task_slug(self.task(task_key="feat/odd key")), "feat-odd-key")

    # ── Lifecycle ───────────────────────────────────────────────────────

    def test_ensure_creates_the_branch_from_the_default_branch(self) -> None:
        repo = self.workspace()
        manager = WorktreeManager(self.project(repo))

        path = manager.ensure(self.task())

        self.assertTrue(path.is_dir())
        self.assertEqual(
            git(path, "branch", "--show-current").stdout.strip(), "feat/wt-1"
        )
        self.assertEqual(
            git(repo, "rev-parse", "feat/wt-1").stdout.strip(),
            git(repo, "rev-parse", "main").stdout.strip(),
        )
        # The operator's checkout is untouched: same branch, same files.
        self.assertEqual(git(repo, "branch", "--show-current").stdout.strip(), "main")

    def test_ensure_reuses_an_existing_worktree_and_its_uncommitted_work(self) -> None:
        repo = self.workspace()
        manager = WorktreeManager(self.project(repo))
        task = self.task()

        first = manager.ensure(task)
        (first / "in-progress.txt").write_text("half done\n", encoding="utf-8")

        second = manager.ensure(task)

        self.assertEqual(first, second)
        self.assertTrue((second / "in-progress.txt").is_file())

    def test_ensure_reuses_an_existing_branch_rather_than_recreating_it(self) -> None:
        repo = self.workspace()
        git(repo, "branch", "feat/wt-1")
        git(repo, "checkout", "feat/wt-1")
        (repo / "prior.txt").write_text("prior work\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "feat: prior work")
        git(repo, "checkout", "main")

        path = WorktreeManager(self.project(repo)).ensure(self.task())

        self.assertTrue((path / "prior.txt").is_file())

    def test_ensure_works_even_when_the_operator_has_the_branch_checked_out(self) -> None:
        repo = self.workspace()
        git(repo, "checkout", "-b", "feat/wt-1")

        path = WorktreeManager(self.project(repo)).ensure(self.task())

        self.assertEqual(
            git(path, "branch", "--show-current").stdout.strip(), "feat/wt-1"
        )
        # The operator keeps whatever they had checked out.
        self.assertEqual(
            git(repo, "branch", "--show-current").stdout.strip(), "feat/wt-1"
        )

    def test_ensure_without_a_branch_is_refused(self) -> None:
        repo = self.workspace()
        manager = WorktreeManager(self.project(repo))

        with self.assertRaises(WorktreeError) as caught:
            manager.ensure(self.task(branch=None))
        self.assertIn("no branch name", str(caught.exception))

    def test_ensure_integration_checks_out_the_default_branch(self) -> None:
        repo = self.workspace()
        manager = WorktreeManager(self.project(repo))

        path = manager.ensure_integration()

        self.assertEqual(path.name, INTEGRATION_WORKTREE_NAME)
        self.assertEqual(git(path, "branch", "--show-current").stdout.strip(), "main")
        self.assertEqual(manager.ensure_integration(), path)

    def test_ensure_integration_aborts_a_merge_a_killed_engine_left_behind(self) -> None:
        repo = self.workspace()
        manager = WorktreeManager(self.project(repo))
        path = manager.ensure_integration()
        git(repo, "checkout", "-b", "feat/other")
        (repo / "README.md").write_text("# theirs\n", encoding="utf-8")
        git(repo, "commit", "-am", "feat: theirs")
        (path / "README.md").write_text("# ours\n", encoding="utf-8")
        git(path, "commit", "-am", "feat: ours")
        merge = subprocess.run(
            ["git", "merge", "--no-ff", "feat/other"], cwd=path, capture_output=True
        )
        self.assertNotEqual(merge.returncode, 0)
        self.assertTrue((path / ".git").exists())
        self.assertIn("UU", git(path, "status", "--porcelain").stdout)

        self.assertEqual(manager.ensure_integration(), path)

        self.assertEqual(git(path, "status", "--porcelain").stdout.strip(), "")
        self.assertEqual((path / "README.md").read_text(encoding="utf-8"), "# ours\n")

    def test_a_dirty_tree_on_the_wrong_branch_is_reported_not_overwritten(self) -> None:
        repo = self.workspace()
        manager = WorktreeManager(self.project(repo))
        task = self.task()
        path = manager.ensure(task)
        git(path, "checkout", "-b", "feat/strayed")
        (path / "README.md").write_text("# unsaved work\n", encoding="utf-8")

        with self.assertRaises(WorktreeError) as caught:
            manager.ensure(task)

        self.assertIn("uncommitted changes", str(caught.exception))
        self.assertEqual((path / "README.md").read_text(encoding="utf-8"), "# unsaved work\n")
        self.assertEqual(git(path, "branch", "--show-current").stdout.strip(), "feat/strayed")

    def test_a_clean_tree_on_the_wrong_branch_is_moved_back(self) -> None:
        repo = self.workspace()
        manager = WorktreeManager(self.project(repo))
        task = self.task()
        path = manager.ensure(task)
        git(path, "checkout", "-b", "feat/strayed")

        manager.ensure(task)

        self.assertEqual(git(path, "branch", "--show-current").stdout.strip(), "feat/wt-1")

    def test_remove_deletes_the_tree_and_the_registration(self) -> None:
        repo = self.workspace()
        manager = WorktreeManager(self.project(repo))
        task = self.task()
        path = manager.ensure(task)

        self.assertTrue(manager.remove(task))

        self.assertFalse(path.exists())
        self.assertNotIn(str(path), git(repo, "worktree", "list").stdout)
        # The branch survives: only the checkout was disposable.
        self.assertIn("feat/wt-1", git(repo, "branch", "--list").stdout)

    def test_remove_refuses_a_path_outside_the_worktree_root(self) -> None:
        repo = self.workspace()
        manager = WorktreeManager(self.project(repo))

        with self.assertRaises(WorktreeError) as caught:
            manager.remove_path(repo)
        self.assertIn("outside the Foreman worktree root", str(caught.exception))
        self.assertTrue((repo / "README.md").is_file())

    def test_ensure_recreates_a_worktree_an_operator_deleted_by_hand(self) -> None:
        repo = self.workspace()
        manager = WorktreeManager(self.project(repo))
        task = self.task()
        path = manager.ensure(task)
        subprocess.run(["rm", "-rf", str(path)], check=True)

        recreated = manager.ensure(task)

        self.assertEqual(recreated, path)
        self.assertTrue((recreated / "README.md").is_file())

    def test_list_reports_task_and_integration_worktrees(self) -> None:
        repo = self.workspace()
        manager = WorktreeManager(self.project(repo))
        manager.ensure(self.task())
        manager.ensure_integration()

        entries = manager.list()

        self.assertEqual(
            {(entry.slug, entry.branch, entry.is_integration) for entry in entries},
            {("WT-1", "feat/wt-1", False), (INTEGRATION_WORKTREE_NAME, "main", True)},
        )
        self.assertTrue(all(entry.exists for entry in entries))

    def test_link_paths_are_symlinked_into_every_new_worktree(self) -> None:
        repo = self.workspace()
        (repo / "venv" / "bin").mkdir(parents=True)
        (repo / "venv" / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")
        manager = WorktreeManager(self.project(repo, worktree_link_paths=["venv"]))

        path = manager.ensure(self.task())

        self.assertTrue((path / "venv").is_symlink())
        self.assertTrue((path / "venv" / "bin" / "python").is_file())

    def test_link_paths_reject_escaping_the_repository(self) -> None:
        repo = self.workspace()
        # Every setting is validated together, so the bad one is reported as
        # soon as the project's settings are read.
        with self.assertRaises(WorktreeError) as caught:
            WorktreeManager(self.project(repo, worktree_link_paths=["../secrets"])).ensure(
                self.task()
            )
        self.assertIn("relative path inside", str(caught.exception))

    # ── Preflight ───────────────────────────────────────────────────────

    def test_preflight_passes_when_the_context_directory_is_ignored(self) -> None:
        WorktreeManager(self.project(self.workspace())).preflight()

    def test_preflight_refuses_a_root_git_would_commit(self) -> None:
        repo = self.workspace(ignore_foreman=False)
        manager = WorktreeManager(self.project(repo))

        with self.assertRaises(WorktreeError) as caught:
            manager.preflight()
        message = str(caught.exception)
        self.assertIn("does not ignore", message)
        self.assertIn(".gitignore", message)

    def test_preflight_refuses_a_worktree_root_at_the_repository_root(self) -> None:
        repo = self.workspace()
        manager = WorktreeManager(self.project(repo, worktree_root=str(repo)))

        with self.assertRaises(WorktreeError):
            manager.preflight()

    def test_preflight_is_a_no_op_outside_a_git_repository(self) -> None:
        with tempfile.TemporaryDirectory() as plain:
            manager = WorktreeManager(self.project(Path(plain)))
            manager.preflight()
            self.assertFalse(manager.is_git_repository())


class WorktreePruningTests(unittest.TestCase):
    """`prune` keeps live tasks and the integration tree, drops everything else."""

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        git(self.repo, "init")
        git(self.repo, "checkout", "-b", "main")
        git(self.repo, "config", "user.email", "worktree-tests@example.com")
        git(self.repo, "config", "user.name", "Worktree Tests")
        (self.repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        (self.repo / "README.md").write_text("# repo\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "chore: initial commit")

        self.store = ForemanStore(root / "foreman.db")
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.project = Project(
            id="p1",
            name="Worktrees",
            repo_path=str(self.repo),
            workflow_id="development",
            default_branch="main",
        )
        self.store.save_project(self.project)
        self.store.save_sprint(
            Sprint(id="s1", project_id="p1", title="S", status="active")
        )

    def seed_task(self, task_id: str, status: str) -> Task:
        task = Task(
            id=task_id,
            sprint_id="s1",
            project_id="p1",
            title=task_id,
            status=status,
            branch_name=f"feat/{task_id}",
        )
        self.store.save_task(task)
        return task

    def test_prune_never_deletes_a_directory_that_is_not_a_worktree(self) -> None:
        """The root is a setting; a wrong value must not delete other files."""

        shared = Path(self.repo).parent / "shared"
        (shared / "precious").mkdir(parents=True)
        (shared / "precious" / "notes.txt").write_text("keep me\n", encoding="utf-8")
        self.project.settings = {"worktree_root": str(shared)}
        self.store.save_project(self.project)
        manager = WorktreeManager(self.project)
        finished_path = manager.ensure(self.seed_task("finished", "done"))

        removed, kept = prune_project_worktrees(self.store, self.project)

        self.assertEqual([entry.slug for entry in removed], [finished_path.name])
        self.assertFalse(finished_path.exists())
        self.assertTrue((shared / "precious" / "notes.txt").is_file())
        stray = next(entry for entry in kept if entry.slug == "precious")
        self.assertFalse(stray.owned)
        self.assertFalse(manager.remove_path(shared / "precious"))
        self.assertTrue((shared / "precious").is_dir())

    def test_the_worktree_root_itself_is_never_removed(self) -> None:
        manager = WorktreeManager(self.project)
        manager.ensure(self.seed_task("live", "in_progress"))
        with self.assertRaises(WorktreeError):
            manager.remove_path(manager.root)
        self.assertTrue(manager.root.is_dir())

    def test_a_tree_whose_registration_was_lost_is_still_recognised(self) -> None:
        manager = WorktreeManager(self.project)
        path = manager.ensure(self.seed_task("finished", "done"))
        admin = Path(self.repo) / ".git" / "worktrees" / path.name
        (admin / "gitdir").unlink()  # git no longer lists the tree
        self.assertTrue(manager.is_owned(path))

        removed, _ = prune_project_worktrees(self.store, self.project)

        self.assertIn(path.name, [entry.slug for entry in removed])
        self.assertFalse(path.exists())

    def test_prune_removes_finished_tasks_and_keeps_live_ones(self) -> None:
        manager = WorktreeManager(self.project)
        live = self.seed_task("live", "in_progress")
        finished = self.seed_task("finished", "done")
        cancelled = self.seed_task("cancelled", "cancelled")
        live_path = manager.ensure(live)
        finished_path = manager.ensure(finished)
        cancelled_path = manager.ensure(cancelled)
        integration_path = manager.ensure_integration()

        removed, kept = prune_project_worktrees(self.store, self.project)

        self.assertEqual(
            sorted(entry.slug for entry in removed),
            sorted([task_slug(finished), task_slug(cancelled)]),
        )
        self.assertEqual(
            sorted(entry.slug for entry in kept),
            sorted([task_slug(live), INTEGRATION_WORKTREE_NAME]),
        )
        self.assertFalse(finished_path.exists())
        self.assertFalse(cancelled_path.exists())
        self.assertTrue(live_path.is_dir())
        self.assertTrue(integration_path.is_dir())

    def test_prune_removes_a_directory_no_task_claims(self) -> None:
        manager = WorktreeManager(self.project)
        orphan = self.seed_task("orphan", "in_progress")
        orphan_path = manager.ensure(orphan)
        self.store.delete_task(orphan.id)

        removed, _ = prune_project_worktrees(self.store, self.project)

        self.assertEqual([entry.slug for entry in removed], [task_slug(orphan)])
        self.assertFalse(orphan_path.exists())

    def test_prune_drops_registrations_for_directories_that_are_gone(self) -> None:
        manager = WorktreeManager(self.project)
        task = self.seed_task("vanished", "in_progress")
        path = manager.ensure(task)
        subprocess.run(["rm", "-rf", str(path)], check=True)

        prune_project_worktrees(self.store, self.project)

        self.assertNotIn(str(path), git(self.repo, "worktree", "list").stdout)


class WorktreeSetupCommandTests(unittest.TestCase):
    """`worktree_setup_command` gives each tree its own environment, once."""

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.repo = Path(temp_dir.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init")
        git(self.repo, "checkout", "-b", "main")
        git(self.repo, "config", "user.email", "worktree-tests@example.com")
        git(self.repo, "config", "user.name", "Worktree Tests")
        (self.repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        (self.repo / "README.md").write_text("# repo\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "chore: initial commit")

    def project(self, **settings: object) -> Project:
        return Project(
            id="p1",
            name="Worktrees",
            repo_path=str(self.repo),
            workflow_id="development",
            default_branch="main",
            settings=dict(settings),
        )

    def task(self, task_id: str = "task-1") -> Task:
        return Task(
            id=task_id,
            sprint_id="s1",
            project_id="p1",
            title=task_id,
            task_key=task_id.upper(),
            branch_name=f"feat/{task_id}",
        )

    def test_setup_command_runs_inside_the_new_worktree(self) -> None:
        project = self.project(
            worktree_setup_command="printf 'env' > .git-ignored-env.txt"
        )
        manager = WorktreeManager(project)

        path = manager.ensure(self.task())

        self.assertEqual(
            (path / ".git-ignored-env.txt").read_text(encoding="utf-8"), "env"
        )
        # The operator's checkout must not be provisioned as a side effect.
        self.assertFalse((self.repo / ".git-ignored-env.txt").exists())

    def test_setup_command_sees_the_repo_and_worktree_paths(self) -> None:
        project = self.project(
            worktree_setup_command=(
                'printf "%s\n%s\n%s" "$FOREMAN_REPO_PATH" "$FOREMAN_WORKTREE_PATH" '
                '"$FOREMAN_WORKTREE_BRANCH" > paths.txt'
            )
        )
        manager = WorktreeManager(project)

        path = manager.ensure(self.task())

        self.assertEqual(
            (path / "paths.txt").read_text(encoding="utf-8").splitlines(),
            [str(self.repo), str(path), "feat/task-1"],
        )

    def test_setup_marker_lives_outside_the_tree_so_it_stays_clean(self) -> None:
        """A marker inside the tree would be untracked and block the merge."""

        project = self.project(worktree_setup_command="true")
        manager = WorktreeManager(project)

        path = manager.ensure(self.task())

        self.assertTrue(is_worktree_clean(path))
        marker = manager.admin_dir(path) / SETUP_MARKER_NAME
        self.assertTrue(marker.is_file())

    def test_setup_command_runs_once_and_is_skipped_on_reuse(self) -> None:
        project = self.project(
            worktree_setup_command="printf 'x' >> $FOREMAN_REPO_PATH/setup-log.txt"
        )
        manager = WorktreeManager(project)
        task = self.task()

        manager.ensure(task)
        manager.ensure(task)
        manager.ensure(task)

        log = (self.repo / "setup-log.txt").read_text(encoding="utf-8")
        self.assertEqual(log, "x")

    def test_changing_the_command_reprovisions_the_tree(self) -> None:
        first = self.project(worktree_setup_command="printf 'one' > marker.txt")
        task = self.task()
        path = WorktreeManager(first).ensure(task)
        self.assertEqual((path / "marker.txt").read_text(encoding="utf-8"), "one")

        second = self.project(worktree_setup_command="printf 'two' > marker.txt")
        WorktreeManager(second).ensure(task)

        self.assertEqual((path / "marker.txt").read_text(encoding="utf-8"), "two")

    def test_clearing_the_command_drops_the_marker(self) -> None:
        project = self.project(worktree_setup_command="true")
        manager = WorktreeManager(project)
        task = self.task()
        path = manager.ensure(task)
        marker = manager.admin_dir(path) / SETUP_MARKER_NAME
        self.assertTrue(marker.is_file())

        WorktreeManager(self.project()).ensure(task)

        self.assertFalse(marker.exists())

    def test_a_failing_setup_command_fails_the_worktree(self) -> None:
        project = self.project(
            worktree_setup_command="echo 'no interpreter here' >&2; exit 3"
        )
        manager = WorktreeManager(project)

        with self.assertRaises(WorktreeError) as caught:
            manager.ensure(self.task())

        message = str(caught.exception)
        self.assertIn("exit code 3", message)
        self.assertIn("no interpreter here", message)

    def test_a_failed_setup_is_retried_on_the_next_visit(self) -> None:
        """No marker is written on failure, so the tree is not left unprovisioned."""

        flag = self.repo / "fail-flag"
        flag.write_text("fail\n", encoding="utf-8")
        project = self.project(
            worktree_setup_command=(
                f'if [ -f "{flag}" ]; then rm "{flag}"; exit 1; fi; printf ok > done.txt'
            )
        )
        manager = WorktreeManager(project)
        task = self.task()

        with self.assertRaises(WorktreeError):
            manager.ensure(task)

        path = manager.ensure(task)
        self.assertEqual((path / "done.txt").read_text(encoding="utf-8"), "ok")

    def test_setup_command_honours_its_timeout(self) -> None:
        project = self.project(
            worktree_setup_command="sleep 30",
            worktree_setup_timeout_seconds=1,
        )
        manager = WorktreeManager(project)

        with self.assertRaises(WorktreeError) as caught:
            manager.ensure(self.task())

        self.assertIn("timed out", str(caught.exception))

    def test_the_integration_tree_is_not_provisioned(self) -> None:
        """Only `_builtin:merge` works there, and it runs git and nothing else."""

        project = self.project(
            worktree_setup_command="printf 'x' > provisioned.txt"
        )
        manager = WorktreeManager(project)

        integration = manager.ensure_integration()

        self.assertTrue(integration.is_dir())
        self.assertFalse((integration / "provisioned.txt").exists())

    def test_no_setup_command_leaves_the_tree_alone(self) -> None:
        manager = WorktreeManager(self.project())

        path = manager.ensure(self.task())

        self.assertTrue(path.is_dir())
        self.assertIsNone(
            _read_optional(manager.admin_dir(path) / SETUP_MARKER_NAME)
        )


def _read_optional(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


class WorktreeLimitTests(unittest.TestCase):
    """`max_live_worktrees` bounds disk use without destroying unmerged work."""

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        git(self.repo, "init")
        git(self.repo, "checkout", "-b", "main")
        git(self.repo, "config", "user.email", "worktree-tests@example.com")
        git(self.repo, "config", "user.name", "Worktree Tests")
        (self.repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        (self.repo / "README.md").write_text("# repo\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "chore: initial commit")

        self.store = ForemanStore(root / "foreman.db")
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(
            Project(
                id="p1",
                name="Worktrees",
                repo_path=str(self.repo),
                workflow_id="development",
                default_branch="main",
            )
        )
        self.store.save_sprint(
            Sprint(id="s1", project_id="p1", title="S", status="active")
        )

    def project(self, limit: int) -> Project:
        project = self.store.get_project("p1")
        project.settings = {"max_live_worktrees": limit}
        self.store.save_project(project)
        return project

    def seed_task(self, task_id: str, status: str = "in_progress") -> Task:
        task = Task(
            id=task_id,
            sprint_id="s1",
            project_id="p1",
            title=task_id,
            # Explicit so the slug is the readable name in assertions; the
            # store would otherwise mint one, and the slug follows the key.
            task_key=task_id,
            status=status,
            branch_name=f"feat/{task_id}",
        )
        self.store.save_task(task)
        return task

    def make_tree(self, manager: WorktreeManager, task: Task) -> Path:
        path = manager.ensure(task)
        task.worktree_path = str(path)
        self.store.save_task(task)
        return path

    def test_the_oldest_clean_tree_is_reclaimed_to_make_room(self) -> None:
        project = self.project(limit=2)
        manager = WorktreeManager(project)
        oldest = self.make_tree(manager, self.seed_task("oldest"))
        newer = self.make_tree(manager, self.seed_task("newer"))
        # `last_used_at` reads the tree's git index mtime; age them explicitly
        # rather than relying on the resolution of two adjacent creations.
        _age(manager, oldest, seconds=600)
        _age(manager, newer, seconds=60)
        arriving = self.seed_task("arriving")

        outcome = enforce_worktree_limit(
            self.store, project, keep_slug=task_slug(arriving)
        )

        self.assertEqual([entry.slug for entry in outcome.reclaimed], ["oldest"])
        self.assertFalse(oldest.exists())
        self.assertTrue(newer.is_dir())
        self.assertFalse(outcome.over_limit)

    def test_a_reclaimed_task_forgets_its_path_but_keeps_its_branch(self) -> None:
        project = self.project(limit=1)
        manager = WorktreeManager(project)
        victim = self.seed_task("victim")
        self.make_tree(manager, victim)
        arriving = self.seed_task("arriving")

        enforce_worktree_limit(self.store, project, keep_slug=task_slug(arriving))

        reloaded = self.store.get_task(victim.id)
        self.assertIsNone(reloaded.worktree_path)
        self.assertEqual(reloaded.branch_name, "feat/victim")
        self.assertIn("feat/victim", git(self.repo, "branch", "--list").stdout)

    def test_a_dirty_tree_is_never_reclaimed(self) -> None:
        """Uncommitted work is not on the branch; reclaiming would destroy it."""

        project = self.project(limit=1)
        manager = WorktreeManager(project)
        paused = self.seed_task("paused")
        paused_path = self.make_tree(manager, paused)
        (paused_path / "half-done.py").write_text("work in progress\n", encoding="utf-8")
        arriving = self.seed_task("arriving")

        outcome = enforce_worktree_limit(
            self.store, project, keep_slug=task_slug(arriving)
        )

        self.assertEqual(outcome.reclaimed, ())
        self.assertEqual([entry.slug for entry in outcome.retained_dirty], ["paused"])
        self.assertTrue(outcome.over_limit)
        self.assertEqual(
            (paused_path / "half-done.py").read_text(encoding="utf-8"),
            "work in progress\n",
        )

    def test_finished_tasks_are_reclaimed_before_live_ones(self) -> None:
        project = self.project(limit=2)
        manager = WorktreeManager(project)
        done = self.seed_task("finished", status="done")
        done_path = self.make_tree(manager, done)
        live = self.seed_task("live")
        live_path = self.make_tree(manager, live)
        # The live tree is older, but a finished task's tree is worth less.
        _age(manager, live_path, seconds=600)
        _age(manager, done_path, seconds=1)
        arriving = self.seed_task("arriving")

        outcome = enforce_worktree_limit(
            self.store, project, keep_slug=task_slug(arriving)
        )

        self.assertEqual([entry.slug for entry in outcome.reclaimed], ["finished"])
        self.assertFalse(done_path.exists())
        self.assertTrue(live_path.is_dir())

    def test_the_integration_tree_is_never_reclaimed(self) -> None:
        project = self.project(limit=1)
        manager = WorktreeManager(project)
        integration = manager.ensure_integration()
        self.make_tree(manager, self.seed_task("older"))
        arriving = self.seed_task("arriving")

        outcome = enforce_worktree_limit(
            self.store, project, keep_slug=task_slug(arriving)
        )

        self.assertNotIn(
            INTEGRATION_WORKTREE_NAME, [entry.slug for entry in outcome.reclaimed]
        )
        self.assertTrue(integration.is_dir())

    def test_the_arriving_task_own_tree_is_never_reclaimed(self) -> None:
        project = self.project(limit=1)
        manager = WorktreeManager(project)
        resuming = self.seed_task("resuming")
        path = self.make_tree(manager, resuming)

        outcome = enforce_worktree_limit(
            self.store, project, keep_slug=task_slug(resuming)
        )

        self.assertEqual(outcome.reclaimed, ())
        self.assertTrue(path.is_dir())

    def test_a_zero_limit_disables_the_cap(self) -> None:
        project = self.project(limit=0)
        manager = WorktreeManager(project)
        for name in ("a", "b", "c"):
            self.make_tree(manager, self.seed_task(name))
        arriving = self.seed_task("arriving")

        outcome = enforce_worktree_limit(
            self.store, project, keep_slug=task_slug(arriving)
        )

        self.assertEqual(outcome.reclaimed, ())
        self.assertFalse(outcome.over_limit)
        self.assertEqual(outcome.live_before, 3)

    def test_the_engine_enforces_the_cap_when_it_makes_a_worktree(self) -> None:
        project = self.project(limit=1)
        manager = WorktreeManager(project)
        victim = self.seed_task("victim")
        victim_path = self.make_tree(manager, victim)
        arriving = self.seed_task("arriving")

        orchestrator = ForemanOrchestrator(self.store)
        path = orchestrator._ensure_task_worktree(project, arriving)

        self.assertTrue(path.is_dir())
        self.assertFalse(victim_path.exists())
        events = [
            event.event_type
            for event in self.store.list_events(project_id="p1")
        ]
        self.assertIn("engine.worktrees_reclaimed", events)


def _age(manager: WorktreeManager, path: Path, *, seconds: int) -> None:
    """Backdate a worktree's last-used signal by `seconds`."""

    index = manager.admin_dir(path) / "index"
    stamp = time.time() - seconds
    os.utime(index, (stamp, stamp))


class Migration16Tests(unittest.TestCase):
    """`tasks.worktree_path` must appear at version 16 and only at version 16."""

    @staticmethod
    def _connection_at_version(version: int) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at  TEXT NOT NULL
            );
            """
        )
        now = "2026-09-05T00:00:00Z"
        for number, description, sql in sorted(MIGRATIONS, key=lambda entry: entry[0]):
            if number > version:
                break
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, description, applied_at)"
                " VALUES (?, ?, ?)",
                (number, description, now),
            )
        conn.commit()
        return conn

    @staticmethod
    def _store_on(conn: sqlite3.Connection) -> ForemanStore:
        store = ForemanStore.__new__(ForemanStore)
        store.db_path = ":memory:"
        store._connection = conn
        store._write_retries = 3
        return store

    def _task_columns(self, conn: sqlite3.Connection) -> set[str]:
        return {str(row["name"]) for row in conn.execute("PRAGMA table_info(tasks)")}

    def test_a_database_at_version_15_has_no_worktree_path_column(self) -> None:
        conn = self._connection_at_version(15)
        self.addCleanup(conn.close)

        self.assertEqual(self._store_on(conn).schema_version(), 15)
        self.assertNotIn("worktree_path", self._task_columns(conn))

    def test_migration_16_applies_cleanly_to_a_version_15_database(self) -> None:
        conn = self._connection_at_version(15)
        self.addCleanup(conn.close)
        store = self._store_on(conn)

        applied = store.migrate()

        self.assertIn(16, applied)
        # migrate() catches the database up to head, which moves as later
        # migrations land; what this test owns is that 16 applied and left the
        # column behind.
        self.assertEqual(store.schema_version(), max(v for v, _, _ in MIGRATIONS))
        self.assertIn("worktree_path", self._task_columns(conn))

    def test_worktree_path_is_nullable_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with ForemanStore(Path(tmp) / "foreman.db") as store:
                store.initialize()
                store.save_project(
                    Project(id="p1", name="P", repo_path=tmp, workflow_id="development")
                )
                store.save_sprint(
                    Sprint(id="s1", project_id="p1", title="S", status="active")
                )
                task = Task(id="t1", sprint_id="s1", project_id="p1", title="T")
                store.save_task(task)

                self.assertIsNone(store.get_task("t1").worktree_path)

                task.worktree_path = f"{tmp}/.foreman/worktrees/T-1"
                store.save_task(task)
                self.assertEqual(
                    store.get_task("t1").worktree_path,
                    f"{tmp}/.foreman/worktrees/T-1",
                )

                task.worktree_path = None
                store.save_task(task)
                self.assertIsNone(store.get_task("t1").worktree_path)


class _ScriptedRunner:
    """A fake agent backend that records the tree each step was given."""

    def __init__(self, behaviours) -> None:
        self._behaviours = list(behaviours)
        self.working_dirs: list[Path] = []

    def run(self, config: AgentRunConfig):
        self.working_dirs.append(Path(config.working_dir))
        behaviour = self._behaviours.pop(0)
        yield from behaviour(config)


def _developer_commits(config: AgentRunConfig):
    work_dir = Path(config.working_dir)
    (work_dir / "feature.py").write_text("def feature():\n    return 1\n", encoding="utf-8")
    (work_dir / "ready.txt").write_text("ready\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: implement the feature"],
        cwd=work_dir,
        check=True,
        capture_output=True,
    )
    yield AgentEvent("agent.started", payload={"command": "fake"})
    yield AgentEvent(
        "agent.message",
        payload={"text": "Implemented the feature with tests.\nTASK_COMPLETE", "phase": "result"},
    )
    yield AgentEvent("agent.completed", payload={"session_id": "s"})


def _reviewer_approves(config: AgentRunConfig):
    yield AgentEvent("agent.started", payload={"command": "fake"})
    yield AgentEvent(
        "agent.message",
        payload={"text": "The diff is sound.\n\nAPPROVE", "phase": "result"},
    )
    yield AgentEvent("agent.completed", payload={"session_id": "s"})


def _quota_exhausted(config: AgentRunConfig):
    yield AgentEvent("agent.started", payload={"command": "fake"})
    yield AgentEvent(
        "agent.error",
        payload={
            "error": "You've hit your session limit",
            "quota_exhausted": True,
            "retry_after": "2026-09-05T13:20:00Z",
            "session_id": "s-quota",
        },
    )


class EngineWorktreeIsolationTests(unittest.TestCase):
    """The engine drives tasks without ever touching the operator's checkout."""

    def workspace(self, *, ignore_foreman: bool = True) -> tuple[Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init")
        git(repo, "checkout", "-b", "main")
        git(repo, "config", "user.email", "worktree-tests@example.com")
        git(repo, "config", "user.name", "Worktree Tests")
        (repo / "README.md").write_text("# repo\n", encoding="utf-8")
        if ignore_foreman:
            (repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "chore: initial commit")
        return repo, root / "foreman.db"

    def seed(
        self,
        store: ForemanStore,
        repo: Path,
        *,
        settings: dict | None = None,
    ) -> tuple[Project, Task]:
        store.initialize()
        project = Project(
            id="p1",
            name="Worktrees",
            repo_path=str(repo),
            workflow_id="development",
            default_branch="main",
            settings={
                "task_selection_mode": "directed",
                "test_command": "test -f ready.txt",
                "default_model": "m",
                "completion_guard_enabled": False,
                **(settings or {}),
            },
        )
        store.save_project(project)
        store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        task = Task(
            id="t1",
            sprint_id="s1",
            project_id="p1",
            title="Implement the feature",
            status="todo",
            acceptance_criteria="Implemented the feature with tests.",
        )
        store.save_task(task)
        return project, task

    def test_a_full_task_never_moves_the_operator_checkout(self) -> None:
        repo, db_path = self.workspace()
        head_before = git(repo, "rev-parse", "HEAD").stdout.strip()
        with ForemanStore(db_path) as store:
            project, task = self.seed(store, repo)
            runner = _ScriptedRunner([_developer_commits, _reviewer_approves])
            orchestrator = ForemanOrchestrator(
                store, agent_runners={"claude_code": runner}
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(
                result.stop_reason, "idle", store.get_task(task.id).blocked_reason
            )
            self.assertEqual(store.get_task(task.id).status, "done")

        # The operator's checkout is still on `main` with the working tree it
        # started with; only the ref moved under it.
        self.assertEqual(git(repo, "branch", "--show-current").stdout.strip(), "main")
        self.assertFalse((repo / "feature.py").exists())
        self.assertNotEqual(git(repo, "rev-parse", "main").stdout.strip(), head_before)
        self.assertIn("feature.py", git(repo, "ls-tree", "-r", "--name-only", "main").stdout)

    def test_agent_steps_and_the_test_command_run_in_the_task_worktree(self) -> None:
        repo, db_path = self.workspace()
        with ForemanStore(db_path) as store:
            project, task = self.seed(store, repo)
            runner = _ScriptedRunner([_developer_commits, _reviewer_approves])
            orchestrator = ForemanOrchestrator(
                store, agent_runners={"claude_code": runner}
            )

            orchestrator.run_project(project.id)

            expected = repo / DEFAULT_WORKTREE_ROOT / task_slug(store.get_task(task.id))
            self.assertEqual(runner.working_dirs, [expected, expected])

            test_events = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "engine.test_run"
            ]
            self.assertEqual(len(test_events), 1)
            self.assertEqual(test_events[0].payload["working_dir"], str(expected))
            self.assertEqual(test_events[0].payload["exit_code"], 0)

    def test_the_projection_is_mirrored_into_the_worktree_the_agent_works_in(self) -> None:
        repo, db_path = self.workspace()
        seen: list[str] = []

        with ForemanStore(db_path) as store:
            project, _ = self.seed(store, repo)

            def developer(config: AgentRunConfig):
                # Read it from inside the tree the agent was handed: the point
                # is that `.foreman/context.md` is there, not only in the
                # operator's checkout.
                context = Path(config.working_dir) / ".foreman" / "context.md"
                seen.append(context.read_text(encoding="utf-8"))
                yield from _developer_commits(config)

            orchestrator = ForemanOrchestrator(
                store,
                agent_runners={
                    "claude_code": _ScriptedRunner([developer, _reviewer_approves])
                },
            )
            orchestrator.run_project(project.id)

        self.assertEqual(len(seen), 1)
        self.assertIn("# Sprint Context", seen[0])
        self.assertIn("Implement the feature", seen[0])

    def test_the_merge_lands_through_the_integration_worktree(self) -> None:
        repo, db_path = self.workspace()
        with ForemanStore(db_path) as store:
            project, task = self.seed(store, repo)
            orchestrator = ForemanOrchestrator(
                store,
                agent_runners={
                    "claude_code": _ScriptedRunner(
                        [_developer_commits, _reviewer_approves]
                    )
                },
            )

            orchestrator.run_project(project.id)

            merge_events = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "engine.merge"
            ]
            self.assertEqual(len(merge_events), 1)
            integration = repo / DEFAULT_WORKTREE_ROOT / INTEGRATION_WORKTREE_NAME
            self.assertEqual(merge_events[0].payload["worktree"], str(integration))
            self.assertTrue(integration.is_dir())
            self.assertEqual(
                git(integration, "branch", "--show-current").stdout.strip(), "main"
            )
            # The integration tree, not the operator's, carries the merge result.
            self.assertTrue((integration / "feature.py").is_file())
            self.assertFalse((repo / "feature.py").exists())

    def test_the_merge_is_backed_by_tests_and_review_of_the_head_commit(self) -> None:
        repo, db_path = self.workspace()
        with ForemanStore(db_path) as store:
            project, task = self.seed(store, repo)
            orchestrator = ForemanOrchestrator(
                store,
                agent_runners={
                    "claude_code": _ScriptedRunner(
                        [_developer_commits, _reviewer_approves]
                    )
                },
            )

            orchestrator.run_project(project.id)

            finished = store.get_task(task.id)
            self.assertEqual(finished.status, "done")
            evidence = finished.completion_evidence
            self.assertIsNotNone(evidence)
            self.assertEqual(evidence.proof_status, "passed")
            self.assertEqual(evidence.tests_status, "passed")
            self.assertTrue(evidence.head_sha)
            self.assertEqual(evidence.tested_sha, evidence.head_sha)
            self.assertEqual(evidence.review_outcome, "approve")
            self.assertEqual(evidence.reviewed_sha, evidence.head_sha)
            recorded = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "engine.review_recorded"
            ]
            self.assertEqual(len(recorded), 1)
            self.assertEqual(recorded[0].payload["head_sha"], evidence.head_sha)

    def test_guidance_reaches_the_next_agent_step_once_and_is_marked_delivered(self) -> None:
        repo, db_path = self.workspace()
        with ForemanStore(db_path) as store:
            project, task = self.seed(store, repo)
            note_run = Run(
                id="run-note",
                task_id=task.id,
                project_id=project.id,
                role_id="human",
                workflow_step="message",
                agent_backend="human",
                status="completed",
                outcome="message",
            )
            store.save_run(note_run)
            store.save_event(
                Event(
                    id="evt-note-1",
                    run_id=note_run.id,
                    task_id=task.id,
                    project_id=project.id,
                    event_type="human.message",
                    timestamp="2026-01-01T00:00:00+00:00",
                    role_id="human",
                    payload={"text": "Name the function feature_flag."},
                )
            )
            prompts: list[str] = []

            def recording(behaviour):
                def run(config: AgentRunConfig):
                    prompts.append(config.prompt)
                    yield from behaviour(config)

                return run

            orchestrator = ForemanOrchestrator(
                store,
                agent_runners={
                    "claude_code": _ScriptedRunner(
                        [recording(_developer_commits), recording(_reviewer_approves)]
                    )
                },
            )

            orchestrator.run_project(project.id)

            self.assertEqual(len(prompts), 2)
            self.assertIn("## Guidance from a person", prompts[0])
            self.assertIn("Name the function feature_flag.", prompts[0])
            # Delivered once: the reviewer's prompt does not repeat it.
            self.assertNotIn("Name the function feature_flag.", prompts[1])
            delivered = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "human.message_delivered"
            ]
            self.assertEqual(len(delivered), 1)
            self.assertEqual(delivered[0].payload["message_event_ids"], ["evt-note-1"])
            self.assertEqual(delivered[0].payload["role"], "developer")
            self.assertEqual(delivered[0].payload["step"], "develop")

    def test_mark_done_removes_the_worktree_and_forgets_the_path(self) -> None:
        repo, db_path = self.workspace()
        with ForemanStore(db_path) as store:
            project, task = self.seed(store, repo)
            orchestrator = ForemanOrchestrator(
                store,
                agent_runners={
                    "claude_code": _ScriptedRunner(
                        [_developer_commits, _reviewer_approves]
                    )
                },
            )

            orchestrator.run_project(project.id)

            finished = store.get_task(task.id)
            self.assertEqual(finished.status, "done")
            self.assertIsNone(finished.worktree_path)
            removals = [
                event
                for event in store.list_events(task_id=task.id)
                if event.event_type == "engine.worktree_removed"
            ]
            self.assertEqual(len(removals), 1)
            self.assertFalse(Path(removals[0].payload["path"]).exists())

    def test_a_human_gate_pause_keeps_the_worktree(self) -> None:
        repo, db_path = self.workspace()
        with ForemanStore(db_path) as store:
            project, task = self.seed(store, repo, settings={"merge_approval": "human"})
            orchestrator = ForemanOrchestrator(
                store,
                agent_runners={
                    "claude_code": _ScriptedRunner(
                        [_developer_commits, _reviewer_approves]
                    )
                },
            )

            orchestrator.run_project(project.id)

            paused = store.get_task(task.id)
            self.assertEqual(paused.workflow_current_step, "merge_approval")
            self.assertIsNotNone(paused.worktree_path)
            worktree = Path(paused.worktree_path)
            self.assertTrue(worktree.is_dir())
            self.assertTrue((worktree / "feature.py").is_file())

    def test_a_quota_pause_keeps_the_worktree(self) -> None:
        repo, db_path = self.workspace()
        with ForemanStore(db_path) as store:
            project, task = self.seed(store, repo)
            orchestrator = ForemanOrchestrator(
                store, agent_runners={"claude_code": _ScriptedRunner([_quota_exhausted])}
            )

            result = orchestrator.run_project(project.id)

            self.assertEqual(result.stop_reason, "quota_exhausted")
            paused = store.get_task(task.id)
            self.assertEqual(paused.status, "in_progress")
            self.assertIsNotNone(paused.worktree_path)
            self.assertTrue(Path(paused.worktree_path).is_dir())

    def test_an_in_progress_task_without_a_worktree_gets_one_on_its_next_visit(self) -> None:
        repo, db_path = self.workspace()
        with ForemanStore(db_path) as store:
            project, task = self.seed(store, repo)
            # A task from before this feature: branch already created by an
            # older engine, no worktree recorded.
            git(repo, "branch", "feat/t1-implement-the-feature")
            task.status = "in_progress"
            task.branch_name = "feat/t1-implement-the-feature"
            task.workflow_current_step = "develop"
            task.worktree_path = None
            store.save_task(task)

            orchestrator = ForemanOrchestrator(
                store,
                agent_runners={
                    "claude_code": _ScriptedRunner(
                        [_developer_commits, _reviewer_approves]
                    )
                },
            )
            result = orchestrator.run_project(project.id)

            self.assertEqual(
                result.stop_reason, "idle", store.get_task(task.id).blocked_reason
            )
            self.assertEqual(store.get_task(task.id).status, "done")

    def test_uncommitted_work_in_the_operator_checkout_never_blocks_a_task(self) -> None:
        """The engine judges the task's tree, not the operator's."""
        repo, db_path = self.workspace()
        with ForemanStore(db_path) as store:
            project, task = self.seed(store, repo)
            # A person is mid-edit in their own checkout while the task runs.
            (repo / "operator-scratch.txt").write_text("half a thought\n", encoding="utf-8")

            orchestrator = ForemanOrchestrator(
                store,
                agent_runners={
                    "claude_code": _ScriptedRunner(
                        [_developer_commits, _reviewer_approves]
                    )
                },
            )
            result = orchestrator.run_project(project.id)

            self.assertEqual(
                result.stop_reason, "idle", store.get_task(task.id).blocked_reason
            )
            self.assertEqual(store.get_task(task.id).status, "done")

        # Their edit is still there, untracked and untouched.
        self.assertEqual(
            (repo / "operator-scratch.txt").read_text(encoding="utf-8"),
            "half a thought\n",
        )

    def test_a_run_fails_at_the_start_when_the_worktree_root_is_not_ignored(self) -> None:
        repo, db_path = self.workspace(ignore_foreman=False)
        with ForemanStore(db_path) as store:
            project, task = self.seed(store, repo)
            orchestrator = ForemanOrchestrator(
                store, agent_runners={"claude_code": _ScriptedRunner([])}
            )

            with self.assertRaises(OrchestratorError) as caught:
                orchestrator.run_project(project.id)

            self.assertIn("does not ignore", str(caught.exception))
            # Nothing was started: the task is untouched.
            self.assertEqual(store.get_task(task.id).status, "todo")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
