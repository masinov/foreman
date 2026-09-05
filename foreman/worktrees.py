"""Per-task git worktrees owned by Foreman.

Every agent step used to run inside the operator's checkout: the engine
checked the task branch out in ``project.repo_path``, the agent edited there,
and the merge step checked the default branch out in the same directory. A
person working in that directory, a second engine, or an interrupted merge
corrupted the run.

This module gives every task its own worktree under a Foreman-owned directory
(``<repo>/.foreman/worktrees/<task-key>/`` by default) plus one shared
*integration* worktree used to land merges on the default branch. The
operator's checkout is never checked out, merged, or restored by the engine
again; it only ever sees refs move.

Ownership rules:

- everything under the worktree root belongs to Foreman. The engine creates,
  reuses, and deletes those directories without asking.
- the operator's checkout belongs to the operator. Foreman reads it (refs,
  ``AGENTS.md``) and writes its context projection into the configured context
  directory, and does nothing else to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
from typing import TYPE_CHECKING

from .errors import ForemanError
from .git import GitError, branch_exists, run_git, worktree_branch
from .models import Project, Task

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .store import ForemanStore

#: Directory (relative to the repository root) holding per-task worktrees when
#: the project does not override ``worktree_root``.
DEFAULT_WORKTREE_ROOT = ".foreman/worktrees"

#: Directory name, inside the worktree root, of the shared worktree that the
#: merge built-in uses to land task branches on the default branch.
INTEGRATION_WORKTREE_NAME = "_integration"

_SLUG_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class WorktreeError(ForemanError):
    """Raised when Foreman cannot provide a usable worktree for a task."""


@dataclass(frozen=True, slots=True)
class WorktreeEntry:
    """One worktree registered with git under the Foreman worktree root."""

    path: Path
    branch: str | None
    slug: str
    exists: bool
    is_integration: bool = False


def worktree_root(project: Project) -> Path:
    """Return the directory holding this project's Foreman-owned worktrees.

    ``worktree_root`` may be absolute (a repository that wants its worktrees on
    another filesystem) or relative to the repository root.
    """

    configured = str(project.settings.get("worktree_root", "") or "").strip()
    raw_path = Path(configured or DEFAULT_WORKTREE_ROOT).expanduser()
    if raw_path.is_absolute():
        return raw_path
    return Path(project.repo_path) / raw_path


def task_slug(task: Task) -> str:
    """Return the directory name for one task's worktree.

    The Jira-style task key is used when the task has one because it is what an
    operator sees in `foreman task list`; the opaque id is the fallback.
    """

    candidate = (task.task_key or "").strip() or task.id
    slug = _SLUG_SAFE.sub("-", candidate).strip("-.")
    if not slug or slug == INTEGRATION_WORKTREE_NAME:
        slug = _SLUG_SAFE.sub("-", task.id).strip("-.")
    if not slug:
        raise WorktreeError(f"Task {task.id!r} has no usable worktree name.")
    return slug


class WorktreeManager:
    """Create, reuse, and remove the worktrees owned by one project."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self.repo_path = Path(project.repo_path)
        self.root = worktree_root(project)

    # ── Preflight ───────────────────────────────────────────────────────────

    def is_git_repository(self) -> bool:
        """Return whether ``repo_path`` is a git repository at all."""

        if not self.repo_path.is_dir():
            return False
        result = run_git(self.repo_path, "rev-parse", "--git-dir", check=False)
        return result.returncode == 0

    def preflight(self) -> None:
        """Fail fast when this repository cannot host Foreman worktrees.

        Called once at run start so a project whose git is too old, or whose
        worktree root would be committed, stops with an explanation instead of
        failing halfway through a task.
        """

        if not self.is_git_repository():
            return

        support = run_git(self.repo_path, "worktree", "list", "--porcelain", check=False)
        if support.returncode != 0:
            detail = support.stderr or support.stdout or "git worktree is unavailable"
            raise WorktreeError(
                f"This git installation does not support worktrees, which Foreman "
                f"needs to run a task without touching {self.repo_path}. Upgrade git "
                f"to 2.5 or newer. Detail: {detail}"
            )

        self._assert_root_is_ignored()

    def _assert_root_is_ignored(self) -> None:
        """Refuse to place worktrees somewhere git would try to commit them."""

        try:
            relative = self.root.resolve().relative_to(self.repo_path.resolve())
        except (ValueError, OSError):
            # Root lives outside the repository: nothing for git to track.
            return
        if not str(relative) or str(relative) == ".":
            raise WorktreeError(
                "worktree_root must not be the repository root itself."
            )
        probe = f"{relative.as_posix()}/{INTEGRATION_WORKTREE_NAME}"
        result = run_git(self.repo_path, "check-ignore", "-q", probe, check=False)
        if result.returncode != 0:
            raise WorktreeError(
                f"Foreman worktrees would live in {relative.as_posix()!r}, which git "
                f"does not ignore in {self.repo_path}. Add it to .gitignore (the "
                f"scaffolded default is `.foreman/`) or point the `worktree_root` "
                f"setting somewhere ignored, then run again."
            )

    # ── Layout ──────────────────────────────────────────────────────────────

    def path_for(self, task: Task) -> Path:
        """Return where this task's worktree lives, whether or not it exists."""

        return self.root / task_slug(task)

    @property
    def integration_path(self) -> Path:
        """Return the shared worktree used to land merges on the default branch."""

        return self.root / INTEGRATION_WORKTREE_NAME

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def ensure(self, task: Task) -> Path:
        """Return the task's worktree, creating it when it does not exist yet.

        The task branch is created from the default branch when it is missing,
        which is what happens on a task's first develop visit. An existing
        worktree is reused as it is, so work paused at a gate, a quota reset,
        or a review round comes back to the same tree.
        """

        branch = (task.branch_name or "").strip()
        if not branch:
            raise WorktreeError(
                f"Task {task.id!r} has no branch name; a worktree needs one."
            )
        path = self.path_for(task)
        return self._ensure_at(path, branch)

    def ensure_integration(self) -> Path:
        """Return the worktree checked out at the default branch for merges."""

        return self._ensure_at(self.integration_path, self.project.default_branch)

    def _ensure_at(self, path: Path, branch: str) -> Path:
        if self._is_live_worktree(path):
            if worktree_branch(path) != branch:
                self._checkout(path, branch)
            return path

        # A registered worktree whose directory an operator deleted, or a
        # leftover empty directory, must not block the new one.
        self.prune_registrations()
        if path.exists():
            if any(path.iterdir()):
                raise WorktreeError(
                    f"{path} exists but is not a git worktree. Remove it and run again."
                )
            path.rmdir()

        path.parent.mkdir(parents=True, exist_ok=True)
        # ``--force`` because the worktree root belongs to Foreman: whether the
        # operator happens to have this branch checked out in their own tree is
        # not allowed to decide whether a task can run.
        if branch_exists(self.repo_path, branch):
            args = ("worktree", "add", "--force", str(path), branch)
        else:
            args = (
                "worktree",
                "add",
                "--force",
                "-b",
                branch,
                str(path),
                self.project.default_branch,
            )
        try:
            run_git(self.repo_path, *args)
        except GitError as exc:
            raise WorktreeError(f"Could not create worktree at {path}: {exc}") from exc
        self._link_shared_paths(path)
        return path

    def remove(self, task: Task) -> bool:
        """Remove one task's worktree. Returns whether anything was removed."""

        return self.remove_path(self.path_for(task))

    def remove_path(self, path: Path) -> bool:
        """Remove one Foreman-owned worktree directory and its registration."""

        if not self._is_inside_root(path):
            raise WorktreeError(
                f"Refusing to remove {path}: it is outside the Foreman worktree root "
                f"{self.root}."
            )
        removed = False
        if path.exists() or self._is_registered(path):
            result = run_git(
                self.repo_path, "worktree", "remove", "--force", str(path), check=False
            )
            removed = result.returncode == 0
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            removed = True
        self.prune_registrations()
        return removed

    def prune_registrations(self) -> None:
        """Drop git's registrations for worktree directories that are gone."""

        run_git(self.repo_path, "worktree", "prune", check=False)

    def list(self) -> tuple[WorktreeEntry, ...]:
        """Return every Foreman-owned worktree git knows about, plus stray dirs."""

        entries: list[WorktreeEntry] = []
        seen: set[Path] = set()
        for path, branch in self._registered_worktrees():
            if not self._is_inside_root(path):
                continue
            seen.add(path)
            entries.append(
                WorktreeEntry(
                    path=path,
                    branch=branch,
                    slug=path.name,
                    exists=path.exists(),
                    is_integration=path.name == INTEGRATION_WORKTREE_NAME,
                )
            )
        if self.root.is_dir():
            for child in sorted(self.root.iterdir()):
                if not child.is_dir() or child.resolve() in seen:
                    continue
                entries.append(
                    WorktreeEntry(
                        path=child,
                        branch=None,
                        slug=child.name,
                        exists=True,
                        is_integration=child.name == INTEGRATION_WORKTREE_NAME,
                    )
                )
        return tuple(sorted(entries, key=lambda entry: entry.slug))

    # ── Internals ───────────────────────────────────────────────────────────

    def _registered_worktrees(self) -> tuple[tuple[Path, str | None], ...]:
        result = run_git(self.repo_path, "worktree", "list", "--porcelain", check=False)
        if result.returncode != 0:
            return ()
        found: list[tuple[Path, str | None]] = []
        path: Path | None = None
        branch: str | None = None
        for line in result.stdout.splitlines() + [""]:
            if line.startswith("worktree "):
                path = Path(line[len("worktree ") :])
                branch = None
            elif line.startswith("branch "):
                branch = line[len("branch ") :].removeprefix("refs/heads/")
            elif not line.strip() and path is not None:
                found.append((_resolve(path), branch))
                path = None
                branch = None
        return tuple(found)

    def _is_registered(self, path: Path) -> bool:
        target = _resolve(path)
        return any(known == target for known, _ in self._registered_worktrees())

    def _is_live_worktree(self, path: Path) -> bool:
        if not (path / ".git").exists():
            return False
        result = run_git(path, "rev-parse", "--is-inside-work-tree", check=False)
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _is_inside_root(self, path: Path) -> bool:
        try:
            _resolve(path).relative_to(_resolve(self.root))
        except ValueError:
            return False
        return True

    def _checkout(self, path: Path, branch: str) -> None:
        if branch_exists(self.repo_path, branch):
            args = ("checkout", "--force", branch)
        else:
            args = ("checkout", "--force", "-b", branch, self.project.default_branch)
        try:
            run_git(path, *args)
        except GitError as exc:
            raise WorktreeError(
                f"Worktree {path} could not be moved to branch {branch!r}: {exc}"
            ) from exc

    def _link_shared_paths(self, path: Path) -> None:
        """Symlink the operator checkout's untracked tooling into a new worktree.

        A worktree is a clean checkout, so it has none of the ignored local
        build state a test command needs — a virtualenv, ``node_modules``. The
        ``worktree_link_paths`` setting names the repository-relative paths to
        link back to the operator's checkout so the project's own
        ``test_command`` keeps working inside a worktree.
        """

        for name in _link_paths(self.project):
            source = self.repo_path / name
            target = path / name
            if not source.exists() or target.exists() or target.is_symlink():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.symlink(source.resolve(), target)
            except OSError as exc:  # pragma: no cover - platform dependent
                raise WorktreeError(
                    f"Could not link {name!r} into worktree {path}: {exc}"
                ) from exc


def _link_paths(project: Project) -> tuple[str, ...]:
    """Return the validated ``worktree_link_paths`` setting."""

    raw = project.settings.get("worktree_link_paths") or []
    if isinstance(raw, str):
        raw = [raw]
    names: list[str] = []
    for value in raw:
        name = str(value).strip()
        if not name:
            continue
        candidate = Path(name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise WorktreeError(
                f"worktree_link_paths entry {name!r} must be a relative path inside "
                "the repository."
            )
        names.append(name)
    return tuple(names)


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:  # pragma: no cover - defensive
        return path


def prune_project_worktrees(
    store: ForemanStore,
    project: Project,
) -> tuple[tuple[WorktreeEntry, ...], tuple[WorktreeEntry, ...]]:
    """Remove worktrees no task needs any more.

    Returns ``(removed, kept)``. A worktree is removed when it belongs to a
    task that is done or cancelled, or when no task in the project claims it
    any more (a task that was deleted, or a directory left by an older
    layout). The integration worktree and the worktrees of live tasks stay.
    """

    manager = WorktreeManager(project)
    manager.prune_registrations()
    slugs_to_keep: set[str] = set()
    for task in store.list_tasks(project_id=project.id):
        if task.status in {"done", "cancelled"}:
            continue
        try:
            slugs_to_keep.add(task_slug(task))
        except WorktreeError:  # pragma: no cover - defensive
            continue

    removed: list[WorktreeEntry] = []
    kept: list[WorktreeEntry] = []
    for entry in manager.list():
        if entry.is_integration or entry.slug in slugs_to_keep:
            kept.append(entry)
            continue
        manager.remove_path(entry.path)
        removed.append(entry)
    return tuple(removed), tuple(kept)
