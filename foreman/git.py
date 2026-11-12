"""Git helper functions for Foreman workflow execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from .errors import ForemanError


class GitError(ForemanError):
    """Raised when a git command needed by Foreman fails."""


@dataclass(slots=True)
class GitCommandResult:
    """Captured output from one git invocation."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class GitMergeResult:
    """Result of merging one branch into another."""

    success: bool
    detail: str
    conflict: bool = False


def run_git(repo_path: str | Path, *args: str, check: bool = True) -> GitCommandResult:
    """Run one git command in the target repository."""

    result = subprocess.run(
        ["git", *args],
        cwd=Path(repo_path),
        capture_output=True,
        text=True,
        check=False,
    )
    command_result = GitCommandResult(
        args=tuple(args),
        returncode=result.returncode,
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
    )
    if check and result.returncode != 0:
        detail = command_result.stderr or command_result.stdout or "git command failed"
        raise GitError(f"git {' '.join(args)} failed in {repo_path}: {detail}")
    return command_result


def head_sha(repo_path: str | Path, ref: str = "HEAD") -> str | None:
    """Return the SHA of a given ref, or None if the ref does not exist."""
    result = run_git(repo_path, "rev-parse", ref, check=False)
    return result.stdout if result.returncode == 0 else None


def branch_exists(repo_path: str | Path, branch_name: str) -> bool:
    """Return whether the repository already has a local branch."""

    result = run_git(
        repo_path,
        "show-ref",
        "--verify",
        "--quiet",
        f"refs/heads/{branch_name}",
        check=False,
    )
    return result.returncode == 0


def checkout_branch(
    repo_path: str | Path,
    branch_name: str,
    *,
    create: bool = False,
    base_branch: str | None = None,
) -> None:
    """Check out one branch, optionally creating it from a base branch.

    Checking out the branch that is already checked out is a no-op. That is
    not just an optimisation: ``git checkout <current-branch>`` fails while
    the index holds unresolved conflicts ("you need to resolve your current
    index first"), and a develop pass resuming after an interrupted merge
    must be able to reach that tree exactly as it was left.
    """

    if worktree_branch(repo_path) == branch_name:
        return

    if create:
        if branch_exists(repo_path, branch_name):
            run_git(repo_path, "checkout", branch_name)
            return
        if base_branch is not None:
            run_git(repo_path, "checkout", base_branch)
        run_git(repo_path, "checkout", "-b", branch_name)
        return

    if not branch_exists(repo_path, branch_name):
        raise GitError(f"Branch {branch_name!r} does not exist in {repo_path}.")
    run_git(repo_path, "checkout", branch_name)


def current_branch(repo_path: str | Path) -> str:
    """Return the currently checked out branch name."""
    result = run_git(repo_path, "branch", "--show-current")
    return result.stdout


def worktree_branch(repo_path: str | Path) -> str | None:
    """Return the branch checked out in the worktree, or None if detached HEAD."""
    try:
        return current_branch(repo_path) or None
    except GitError:
        return None


def is_worktree_clean(repo_path: str | Path) -> bool:
    """Return whether the repository has no staged or unstaged file changes."""

    result = run_git(repo_path, "status", "--porcelain")
    return result.stdout == ""


def merge_branch(
    repo_path: str | Path,
    source_branch: str,
    target_branch: str,
) -> GitMergeResult:
    """Merge one source branch into the target branch."""

    checkout_branch(repo_path, target_branch)
    result = run_git(
        repo_path,
        "merge",
        "--no-ff",
        "--no-edit",
        source_branch,
        check=False,
    )
    if result.returncode == 0:
        detail = result.stdout or f"Merged {source_branch} into {target_branch}."
        return GitMergeResult(success=True, detail=detail)

    run_git(repo_path, "merge", "--abort", check=False)
    detail = result.stderr or result.stdout or "git merge failed"
    return GitMergeResult(
        success=False,
        detail=detail,
        conflict=_looks_like_merge_conflict(detail),
    )


def merge_in_progress(repo_path: str | Path) -> bool:
    """Return whether the worktree has an unconcluded merge (``MERGE_HEAD`` exists)."""

    result = run_git(repo_path, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False)
    return result.returncode == 0


def commits_behind(repo_path: str | Path, branch_name: str, base_branch: str) -> int:
    """Return how many commits ``base_branch`` has that ``branch_name`` lacks.

    Zero means the branch already contains the base branch's history, so a
    merge from the base would be a no-op.
    """

    result = run_git(
        repo_path,
        "rev-list",
        "--count",
        f"{branch_name}..{base_branch}",
        check=False,
    )
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip() or "0")
    except ValueError:
        return 0


def sync_branch_with_base(
    repo_path: str | Path,
    branch_name: str,
    base_branch: str,
) -> GitMergeResult:
    """Merge the current base branch into an existing task branch.

    Foreman uses this during merge-conflict recovery so a stale task branch can
    be refreshed against the latest default branch before the developer tries to
    resolve the conflict and return for another review cycle.
    """

    checkout_branch(repo_path, branch_name)
    result = run_git(
        repo_path,
        "merge",
        "--no-ff",
        "--no-edit",
        base_branch,
        check=False,
    )
    if result.returncode == 0:
        detail = result.stdout or f"Merged {base_branch} into {branch_name}."
        return GitMergeResult(success=True, detail=detail)

    run_git(repo_path, "merge", "--abort", check=False)
    detail = result.stderr or result.stdout or "git merge failed"
    return GitMergeResult(
        success=False,
        detail=detail,
        conflict=_looks_like_merge_conflict(detail),
    )


def status_text(repo_path: str | Path) -> str:
    """Return a compact git status string for prompt context."""

    result = run_git(repo_path, "status", "--short", "--branch")
    return result.stdout


def changed_files(
    repo_path: str | Path,
    *,
    target_branch: str,
    branch_name: str | None,
) -> str:
    """Return changed file names for one branch compared to the target branch."""

    if not branch_name:
        return ""
    result = run_git(
        repo_path,
        "diff",
        "--name-only",
        f"{target_branch}...{branch_name}",
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def recent_commits(
    repo_path: str | Path,
    *,
    branch_name: str | None,
    limit: int = 5,
) -> str:
    """Return recent commit subjects for one branch."""

    ref = branch_name or "HEAD"
    result = run_git(
        repo_path,
        "log",
        "--oneline",
        f"-n{limit}",
        ref,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


@dataclass(frozen=True, slots=True)
class FileChange:
    """One file a branch changes against its base.

    ``status`` is ``added``, ``modified``, ``deleted`` or ``renamed``;
    ``old_path`` is set only for a rename. A binary file has no line counts, so
    ``added`` and ``deleted`` are zero and ``binary`` is true.
    """

    path: str
    status: str
    added: int = 0
    deleted: int = 0
    binary: bool = False
    old_path: str | None = None


_STATUS_NAMES = {"A": "added", "M": "modified", "D": "deleted", "R": "renamed", "C": "added", "T": "modified"}


def _git_bytes(repo_path: str | Path, args: list[str]) -> tuple[int, bytes]:
    """Run git with a fixed argument list and return the exit code and raw stdout.

    Nothing goes through a shell, and the output is not stripped, so NUL
    separated records and diff text keep their exact bytes.
    """

    result = subprocess.run(
        ["git", *args],
        cwd=Path(repo_path),
        capture_output=True,
        check=False,
    )
    return result.returncode, result.stdout


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def merge_base(repo_path: str | Path, base_branch: str, branch_name: str) -> str | None:
    """Return the commit where ``branch_name`` left ``base_branch``, if any."""

    result = run_git(repo_path, "merge-base", base_branch, branch_name, check=False)
    return result.stdout if result.returncode == 0 and result.stdout else None


def commits_ahead(repo_path: str | Path, branch_name: str, base_branch: str) -> int:
    """Return how many commits ``branch_name`` has that ``base_branch`` lacks."""

    return commits_behind(repo_path, base_branch, branch_name)


def branch_changes(
    repo_path: str | Path,
    *,
    base_branch: str,
    branch_name: str,
) -> list[FileChange]:
    """Return the files ``branch_name`` changes since it left ``base_branch``.

    This is the comparison a merge would land (``base...branch``). It combines
    ``--numstat`` (line counts, as completion evidence reads them) with
    ``--name-status`` (the kind of change), both in ``-z`` form so a path with
    spaces or a newline is exact. Raises ``GitError`` when git cannot compare.
    """

    range_arg = f"{base_branch}...{branch_name}"
    code, numstat = _git_bytes(repo_path, ["diff", "--numstat", "-z", "-M", range_arg, "--"])
    if code != 0:
        raise GitError(f"git could not compare {range_arg} in {repo_path}")
    code, name_status = _git_bytes(repo_path, ["diff", "--name-status", "-z", "-M", range_arg, "--"])
    if code != 0:
        raise GitError(f"git could not compare {range_arg} in {repo_path}")

    counts: dict[str, tuple[int, int, bool]] = {}
    tokens = _decode(numstat).split("\0")
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if not token:
            continue
        parts = token.split("\t", 2)
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if path == "":
            path = tokens[i + 1] if i + 1 < len(tokens) else ""
            i += 2
        binary = added == "-" or deleted == "-"
        counts[path] = (
            int(added) if added.isdigit() else 0,
            int(deleted) if deleted.isdigit() else 0,
            binary,
        )

    changes: list[FileChange] = []
    tokens = _decode(name_status).split("\0")
    i = 0
    while i < len(tokens):
        code_text = tokens[i]
        i += 1
        if not code_text:
            continue
        kind = code_text[0]
        if kind in ("R", "C"):
            old_path = tokens[i] if i < len(tokens) else ""
            path = tokens[i + 1] if i + 1 < len(tokens) else ""
            i += 2
        else:
            old_path = None
            path = tokens[i] if i < len(tokens) else ""
            i += 1
        if not path:
            continue
        added_n, deleted_n, binary = counts.get(path, (0, 0, False))
        changes.append(
            FileChange(
                path=path,
                status=_STATUS_NAMES.get(kind, "modified") if kind != "C" else "added",
                added=added_n,
                deleted=deleted_n,
                binary=binary,
                old_path=old_path if kind == "R" else None,
            )
        )
    return changes


def file_diff(
    repo_path: str | Path,
    *,
    base_branch: str,
    branch_name: str,
    change: FileChange,
) -> str:
    """Return the unified diff of one changed file, as text.

    The path is passed as a literal pathspec after ``--`` (never parsed as a
    glob, a revision or an option); a rename names both paths so git shows it
    as a rename.
    """

    paths = [change.path] if change.old_path is None else [change.old_path, change.path]
    code, output = _git_bytes(
        repo_path,
        [
            "--literal-pathspecs",
            "diff",
            "-M",
            f"{base_branch}...{branch_name}",
            "--",
            *paths,
        ],
    )
    if code != 0:
        raise GitError(f"git could not diff {change.path} in {repo_path}")
    return _decode(output)


def _looks_like_merge_conflict(detail: str) -> bool:
    normalized = detail.lower()
    return (
        "conflict (" in normalized
        or "automatic merge failed" in normalized
        or "fix conflicts and then commit" in normalized
    )


def task_commits_on_default_branch(
    repo_path: str,
    *,
    task_branch: str,
    default_branch: str,
    default_shas_seen: tuple[str | None, ...],
) -> tuple[str, ...]:
    """Return this task's own commits that are already on the default branch.

    The default branch is allowed to move while a task runs: an operator
    commits to it, another task merges into it. What must not happen is the
    task's own work reaching it before the merge step, unreviewed.

    A task's own commits are those on its branch that were not on the default
    branch at any point the engine looked at it (``default_shas_seen``: when
    the step began and when the engine last refreshed the task branch from
    it). Commits the refresh brought in from the default branch are therefore
    not the task's own, and a default branch that merely moved on is not a
    violation.
    """

    current = head_sha(repo_path, f"refs/heads/{default_branch}")
    task_tip = head_sha(repo_path, f"refs/heads/{task_branch}")
    if current is None or task_tip is None:
        return ()
    seen = [sha for sha in default_shas_seen if sha]
    if not seen or current in seen:
        return ()
    exclusions = [f"^{sha}" for sha in seen]
    own = run_git(repo_path, "rev-list", task_tip, *exclusions, check=False)
    if own.returncode != 0:
        return ()
    own_commits = own.stdout.split()
    if not own_commits:
        return ()
    still_off = run_git(
        repo_path, "rev-list", task_tip, *exclusions, f"^{current}", check=False
    )
    if still_off.returncode != 0:
        return ()
    off_default = set(still_off.stdout.split())
    return tuple(sha for sha in own_commits if sha not in off_default)


@dataclass(frozen=True)
class MergePreflightResult:
    """Result of merge preflight checks."""

    success: bool
    detail: str
    reason: str | None = None  # 'missing_source', 'missing_target', 'dirty_worktree', 'same_branch', 'no_delta', 'checkout_failed'


def merge_preflight(
    repo_path: str | Path,
    *,
    source_branch: str,
    target_branch: str,
) -> MergePreflightResult:
    """Validate repository state before attempting a merge.

    Checks:
    - source branch exists
    - target branch exists
    - worktree is clean
    - source is not the same as target
    - source contains commits ahead of target
    """
    # Source must exist
    if not branch_exists(repo_path, source_branch):
        return MergePreflightResult(
            success=False,
            detail=f"Source branch {source_branch!r} does not exist.",
            reason="missing_source",
        )

    # Target must exist
    if not branch_exists(repo_path, target_branch):
        return MergePreflightResult(
            success=False,
            detail=f"Target branch {target_branch!r} does not exist.",
            reason="missing_target",
        )

    # Source and target must not be the same
    if source_branch == target_branch:
        return MergePreflightResult(
            success=False,
            detail="Source and target branch are the same.",
            reason="same_branch",
        )

    # Worktree must be clean
    if not is_worktree_clean(repo_path):
        return MergePreflightResult(
            success=False,
            detail="Worktree has uncommitted changes. Commit before merging.",
            reason="dirty_worktree",
        )

    # Source must have commits ahead of target
    result = run_git(
        repo_path,
        "log",
        "--oneline",
        f"{target_branch}..{source_branch}",
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return MergePreflightResult(
            success=False,
            detail=f"Source branch {source_branch!r} has no commits ahead of {target_branch!r}.",
            reason="no_delta",
        )

    return MergePreflightResult(success=True, detail="Merge preflight passed.")
