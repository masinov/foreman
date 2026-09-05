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
import hashlib
import os
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

from .errors import ForemanError
from .git import GitError, branch_exists, is_worktree_clean, run_git, worktree_branch
from .models import Project, Task

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .store import ForemanStore

#: Directory (relative to the repository root) holding per-task worktrees when
#: the project does not override ``worktree_root``.
DEFAULT_WORKTREE_ROOT = ".foreman/worktrees"

#: Directory name, inside the worktree root, of the shared worktree that the
#: merge built-in uses to land task branches on the default branch.
INTEGRATION_WORKTREE_NAME = "_integration"

#: Default ceiling on live task worktrees when the project does not set
#: ``max_live_worktrees``. 0 means unlimited.
DEFAULT_MAX_LIVE_WORKTREES = 4

#: Default wall-clock cap for ``worktree_setup_command``.
DEFAULT_SETUP_TIMEOUT_SECONDS = 1800

#: Marker file, written inside a worktree's git admin directory, recording the
#: setup command that last provisioned it. It lives in the admin directory
#: rather than the tree so it never shows up as an untracked file (which would
#: make the tree dirty and block the merge built-in), and so
#: ``git worktree remove`` takes it away with the tree.
SETUP_MARKER_NAME = "foreman-worktree-setup"

#: How much of a failed setup command's output to carry into the error.
_SETUP_OUTPUT_TAIL_CHARS = 2000

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
            # A tree created before the setting existed, or one whose setup was
            # interrupted, is provisioned on this visit rather than silently
            # running steps in an environment that was never built.
            self._run_setup_command(path)
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
        self._run_setup_command(path)
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

    # ── Per-worktree environment ────────────────────────────────────────────

    def _run_setup_command(self, path: Path) -> bool:
        """Build this worktree's own environment, once per tree.

        ``worktree_link_paths`` shares the operator's tooling with a worktree;
        this builds the tree its *own*. The command runs with the worktree as
        its working directory, so a project can create a virtualenv, install
        dependencies, or seed a fixture database that belongs to this tree
        alone, and a test run inside it stops depending on whatever state the
        operator's checkout happens to be in.

        Returns whether the command ran. It is skipped when the tree's marker
        already records the same command, which makes reuse across gates,
        quota pauses, and engine restarts free. Changing the setting
        re-provisions every tree on its next visit.
        """

        command = _setup_command(self.project)
        marker = self._setup_marker_path(path)
        if not command:
            # Clearing the setting must not leave a stale marker behind that
            # would suppress a later command with the same fingerprint.
            if marker is not None and marker.exists():
                marker.unlink(missing_ok=True)
            return False
        fingerprint = _fingerprint(command)
        if marker is not None and _read_marker(marker) == fingerprint:
            return False

        env = dict(os.environ)
        env.update(
            {
                "FOREMAN_WORKTREE_PATH": str(path),
                "FOREMAN_REPO_PATH": str(self.repo_path),
                "FOREMAN_WORKTREE_BRANCH": worktree_branch(path) or "",
                "FOREMAN_DEFAULT_BRANCH": self.project.default_branch,
            }
        )
        timeout = _setup_timeout(self.project)
        try:
            result = subprocess.run(
                ["bash", "-lc", command],
                cwd=path,
                env=env,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout if timeout > 0 else None,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorktreeError(
                f"worktree_setup_command timed out after {timeout}s in {path}. "
                f"Raise worktree_setup_timeout_seconds or simplify the command. "
                f"Command: {command}"
            ) from exc
        except OSError as exc:  # pragma: no cover - platform dependent
            raise WorktreeError(
                f"Could not run worktree_setup_command in {path}: {exc}"
            ) from exc

        if result.returncode != 0:
            tail = _output_tail(result.stdout, result.stderr)
            # The marker stays unwritten, so the next visit retries setup. The
            # tree is left in place for the operator to inspect.
            raise WorktreeError(
                f"worktree_setup_command failed with exit code {result.returncode} in "
                f"{path}. The worktree has no usable environment, so no step ran in "
                f"it. Command: {command}\n{tail}"
            )
        if marker is not None:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(fingerprint, encoding="utf-8")
        return True

    def admin_dir(self, path: Path) -> Path | None:
        """Return a worktree's git admin directory, or None if it has none.

        For a worktree this is ``<repo>/.git/worktrees/<name>``: private to the
        tree, outside it, and removed by ``git worktree remove``.
        """

        result = run_git(path, "rev-parse", "--absolute-git-dir", check=False)
        if result.returncode != 0:
            return None
        admin_dir = result.stdout.strip()
        return Path(admin_dir) if admin_dir else None

    def _setup_marker_path(self, path: Path) -> Path | None:
        """Return the setup marker inside this worktree's git admin directory."""

        admin_dir = self.admin_dir(path)
        return None if admin_dir is None else admin_dir / SETUP_MARKER_NAME

    def last_used_at(self, path: Path) -> float:
        """Return when this worktree was last worked in, as a POSIX timestamp.

        Git rewrites the tree's private index on every checkout, commit, and
        status, so the index mtime tracks engine activity in that tree far more
        closely than anything Foreman persists. Falls back to the directory
        itself, then to 0 so an unreadable tree sorts as the oldest and is
        reclaimed first.
        """

        admin_dir = self.admin_dir(path)
        for candidate in ((admin_dir / "index") if admin_dir else None, path):
            if candidate is None:
                continue
            try:
                return candidate.stat().st_mtime
            except OSError:
                continue
        return 0.0


def _setup_command(project: Project) -> str:
    """Return the project's ``worktree_setup_command``, if any."""

    return str(project.settings.get("worktree_setup_command", "") or "").strip()


def _setup_timeout(project: Project) -> int:
    """Return the wall-clock cap for ``worktree_setup_command`` in seconds."""

    raw = project.settings.get(
        "worktree_setup_timeout_seconds", DEFAULT_SETUP_TIMEOUT_SECONDS
    )
    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_SETUP_TIMEOUT_SECONDS
    return max(timeout, 0)


def _fingerprint(command: str) -> str:
    """Return the marker contents identifying one setup command."""

    return hashlib.sha256(command.encode("utf-8")).hexdigest()


def _read_marker(marker: Path) -> str | None:
    try:
        return marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _output_tail(stdout: str | None, stderr: str | None) -> str:
    """Return the tail of a failed setup command's output, for the error."""

    combined = "\n".join(part for part in (stdout or "", stderr or "") if part.strip())
    combined = combined.strip()
    if len(combined) > _SETUP_OUTPUT_TAIL_CHARS:
        return "…" + combined[-_SETUP_OUTPUT_TAIL_CHARS:]
    return combined


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


@dataclass(frozen=True, slots=True)
class ReclaimOutcome:
    """What enforcing ``max_live_worktrees`` did on one ``ensure`` call."""

    limit: int
    live_before: int
    live_after: int
    reclaimed: tuple[WorktreeEntry, ...] = ()
    #: Trees that were over the limit but held uncommitted work, so removing
    #: them would have destroyed it. They are the reason a project can sit
    #: above its cap.
    retained_dirty: tuple[WorktreeEntry, ...] = ()

    @property
    def over_limit(self) -> bool:
        """Whether the cap could not be met without destroying unmerged work."""

        return self.limit > 0 and self.live_after > self.limit


def max_live_worktrees(project: Project) -> int:
    """Return the project's ceiling on live task worktrees. 0 means unlimited."""

    raw = project.settings.get("max_live_worktrees", DEFAULT_MAX_LIVE_WORKTREES)
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_LIVE_WORKTREES
    return max(limit, 0)


def enforce_worktree_limit(
    store: ForemanStore,
    project: Project,
    *,
    keep_slug: str,
    manager: WorktreeManager | None = None,
) -> ReclaimOutcome:
    """Reclaim worktrees so ``keep_slug`` can exist without breaching the cap.

    Without this, a project accumulates one full checkout per task that ever
    started and paused, and nothing ever gives the disk back until an operator
    runs ``foreman worktree prune``. The policy:

    - the integration tree and ``keep_slug`` (the task about to run) are never
      reclaimed,
    - trees of done, cancelled, or vanished tasks go first — nothing wants
      them,
    - then the least recently used of the rest,
    - **a tree with uncommitted changes is never reclaimed.** That work is not
      on the branch, so removing the tree would destroy it. A project whose
      trees are all dirty therefore stays above its cap, and the caller reports
      that rather than silently discarding an agent's unfinished work.

    Reclaiming is safe for everything else because a clean tree holds nothing
    the branch does not: the next visit recreates it from the same branch.
    """

    manager = manager or WorktreeManager(project)
    limit = max_live_worktrees(project)
    entries = [entry for entry in manager.list() if not entry.is_integration]
    live_before = sum(1 for entry in entries if entry.exists)
    if limit <= 0:
        return ReclaimOutcome(
            limit=limit, live_before=live_before, live_after=live_before
        )

    # The task about to run counts against the cap whether or not its tree is
    # on disk yet: the point is to make room *for* it.
    live_after = live_before + (
        0 if any(e.slug == keep_slug and e.exists for e in entries) else 1
    )

    disposable = _disposable_slugs(store, project, entries)
    candidates = sorted(
        (entry for entry in entries if entry.slug != keep_slug),
        key=lambda entry: (
            entry.slug not in disposable,
            manager.last_used_at(entry.path),
        ),
    )

    reclaimed: list[WorktreeEntry] = []
    retained: list[WorktreeEntry] = []
    for entry in candidates:
        if live_after <= limit:
            break
        if entry.exists and entry.slug not in disposable and not is_worktree_clean(
            entry.path
        ):
            retained.append(entry)
            continue
        manager.remove_path(entry.path)
        reclaimed.append(entry)
        if entry.exists:
            live_after -= 1

    _forget_reclaimed_paths(store, project, reclaimed)
    return ReclaimOutcome(
        limit=limit,
        live_before=live_before,
        live_after=live_after,
        reclaimed=tuple(reclaimed),
        retained_dirty=tuple(retained),
    )


def _disposable_slugs(
    store: ForemanStore,
    project: Project,
    entries: list[WorktreeEntry],
) -> set[str]:
    """Return the slugs of trees no live task claims any more."""

    claimed: set[str] = set()
    for task in store.list_tasks(project_id=project.id):
        if task.status in {"done", "cancelled"}:
            continue
        try:
            claimed.add(task_slug(task))
        except WorktreeError:  # pragma: no cover - defensive
            continue
    return {entry.slug for entry in entries if entry.slug not in claimed}


def _forget_reclaimed_paths(
    store: ForemanStore,
    project: Project,
    reclaimed: list[WorktreeEntry],
) -> None:
    """Clear ``worktree_path`` on tasks whose tree was just reclaimed.

    A task keeps its branch and its place in the workflow; only the checkout
    went away, and the next visit makes a new one from the same branch.
    """

    if not reclaimed:
        return
    removed_paths = {str(entry.path) for entry in reclaimed}
    for task in store.list_tasks(project_id=project.id):
        if task.worktree_path and task.worktree_path in removed_paths:
            task.worktree_path = None
            store.save_task(task)


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
