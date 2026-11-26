"""Git helper functions for Foreman workflow execution."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
from typing import Callable

from ..domain.errors import ForemanError


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
    #: The commit the target branch points at after a successful merge.
    sha: str | None = None
    #: The merge was undone because ``finish`` refused it; ``detail`` says why.
    refused: bool = False


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


#: How long a push may take before it is given up on.
PUSH_TIMEOUT_SECONDS = 120


def push_branch(
    repo_path: str | Path,
    *,
    remote: str,
    branch: str,
    timeout: float = PUSH_TIMEOUT_SECONDS,
) -> GitCommandResult:
    """Push one branch to a remote. Never raises; the result says what happened.

    Git is told not to ask for credentials: nobody is there to answer, and a
    prompt would hold the step open until the timeout.
    """

    return _push(repo_path, remote, f"refs/heads/{branch}:refs/heads/{branch}", timeout)


def push_tag(
    repo_path: str | Path,
    *,
    remote: str,
    tag: str,
    timeout: float = PUSH_TIMEOUT_SECONDS,
) -> GitCommandResult:
    """Push one tag to a remote. Never raises; the result says what happened."""

    return _push(repo_path, remote, f"refs/tags/{tag}:refs/tags/{tag}", timeout)


def _push(repo_path: str | Path, remote: str, refspec: str, timeout: float) -> GitCommandResult:
    args = ("push", remote, refspec)
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=Path(repo_path),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired:
        return GitCommandResult(
            args=args, returncode=124, stdout="", stderr=f"git push timed out after {timeout:.0f}s"
        )
    except OSError as exc:
        return GitCommandResult(args=args, returncode=1, stdout="", stderr=str(exc))
    return GitCommandResult(
        args=args,
        returncode=result.returncode,
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
    )


def tag_commit(repo_path: str | Path, tag: str) -> str | None:
    """The commit a tag points at, or None when there is no such tag."""

    result = run_git(repo_path, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}", check=False)
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


def create_tag(repo_path: str | Path, tag: str, sha: str, message: str) -> GitCommandResult:
    """Create an annotated tag at ``sha``. Never raises; the result says what happened."""

    return run_git(repo_path, "tag", "--annotate", tag, "--message", message, sha, check=False)


def merge_branch(
    repo_path: str | Path,
    source_branch: str,
    target_branch: str,
    *,
    finish: Callable[[Path], str | None] | None = None,
    message: str | None = None,
) -> GitMergeResult:
    """Merge one source branch into the target branch.

    ``message`` is the merge commit's message; git's own when it is None.

    With ``finish``, the merge is made without its commit and ``finish`` is
    called on the tree: it may change and stage files, which then land in the
    merge commit, or return a reason to refuse, which undoes the merge.
    """

    checkout_branch(repo_path, target_branch)
    result = run_git(
        repo_path,
        "merge",
        "--no-ff",
        *(("--no-commit",) if finish else ()),
        *(("--message", message) if message else ()),
        "--no-edit",
        source_branch,
        check=False,
    )
    if result.returncode == 0:
        if finish and merge_in_progress(repo_path):
            try:
                refusal = finish(Path(repo_path))
            except Exception as exc:  # noqa: BLE001 - the tree must never be left mid-merge
                # A merge left half made would refuse every merge after it.
                run_git(repo_path, "reset", "--hard", "HEAD", check=False)
                return GitMergeResult(
                    success=False,
                    detail=f"The merge was undone: finishing it failed ({type(exc).__name__}: {exc}).",
                )
            if refusal is not None:
                run_git(repo_path, "reset", "--hard", "HEAD", check=False)
                return GitMergeResult(success=False, detail=refusal, refused=True)
            # A plain merge runs no pre-commit hook; this commit is that merge's.
            committed = run_git(repo_path, "commit", "--no-edit", "--no-verify", check=False)
            if committed.returncode != 0:
                run_git(repo_path, "reset", "--hard", "HEAD", check=False)
                detail = committed.stderr or committed.stdout or "git commit failed"
                return GitMergeResult(success=False, detail=detail)
        detail = result.stdout or f"Merged {source_branch} into {target_branch}."
        head = run_git(repo_path, "rev-parse", "HEAD", check=False)
        sha = head.stdout.strip() if head.returncode == 0 else ""
        return GitMergeResult(success=True, detail=detail, sha=sha or None)

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


#: How far back the branch's first-parent history is searched for the commit
#: a checkout still shows. A checkout further behind than this is left alone.
FOLLOW_SEARCH_DEPTH = 1000


@dataclass(frozen=True, slots=True)
class CheckoutFollow:
    """What :func:`follow_branch_in_checkout` did to one checkout.

    ``state`` is ``other_branch`` (the checkout is not on the branch; nothing
    to do), ``current`` (its files already show the branch's head),
    ``updated`` (its files were brought from ``from_sha`` to the head) or
    ``left`` (they were not, for ``reason``).
    """

    state: str
    from_sha: str | None = None
    reason: str = ""


def follow_branch_in_checkout(repo_path: str | Path, branch: str, sha: str) -> CheckoutFollow:
    """Bring a checkout that has ``branch`` checked out up to ``sha`` (ADR-0031).

    A merge in another worktree moves the branch under a checkout sitting on
    it: its files go on describing the commit before, and git reports the
    merged work as staged deletions. This does what a fast-forward pull would
    have done there. The commit the checkout shows is found by its index: the
    index must equal the tree of a commit in the branch's first-parent
    history, so anything staged that was never committed makes it ``left``.
    ``git read-tree -m -u`` then moves index and files from that commit to
    ``sha``; it keeps a person's untracked files and unstaged edits and
    refuses, changing nothing, where the update would overwrite one.
    """

    if worktree_branch(repo_path) != branch:
        return CheckoutFollow("other_branch")
    if merge_in_progress(repo_path):
        return CheckoutFollow("left", reason="a merge is in progress there")
    index_tree = run_git(repo_path, "write-tree", check=False)
    if index_tree.returncode != 0:
        return CheckoutFollow("left", reason="its index has unresolved conflicts")
    target_tree = run_git(repo_path, "rev-parse", f"{sha}^{{tree}}", check=False)
    if target_tree.returncode != 0:
        return CheckoutFollow("left", reason=f"commit {sha} is not in that repository")
    if index_tree.stdout == target_tree.stdout:
        return CheckoutFollow("current")
    history = run_git(
        repo_path,
        "log",
        "--first-parent",
        f"-n{FOLLOW_SEARCH_DEPTH}",
        "--format=%H %T",
        sha,
        check=False,
    )
    shown = next(
        (
            commit
            for commit, _, tree in (line.partition(" ") for line in history.stdout.splitlines())
            if tree == index_tree.stdout
        ),
        None,
    )
    if shown is None:
        return CheckoutFollow(
            "left",
            reason=f"it holds staged changes that are not a commit of {branch}",
        )
    moved = run_git(repo_path, "read-tree", "-m", "-u", shown, sha, check=False)
    if moved.returncode != 0:
        detail = moved.stderr or moved.stdout or "git read-tree failed"
        return CheckoutFollow("left", from_sha=shown, reason=detail)
    return CheckoutFollow("updated", from_sha=shown)


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


def landed_as(repo_path: str | Path, head: str, base_branch: str) -> str | None:
    """Return the commit on ``base_branch`` that brought ``head`` in, if any.

    That is the oldest commit on the base branch's first-parent line that
    contains ``head``: the merge commit of a ``--no-ff`` merge. ``None`` when
    ``head`` is not in the base branch, or is itself on its first-parent line
    (a fast-forward, where no one commit holds the change).
    """

    if run_git(repo_path, "merge-base", "--is-ancestor", head, base_branch, check=False).returncode != 0:
        return None
    result = run_git(
        repo_path, "rev-list", "--first-parent", "--ancestry-path", f"{head}..{base_branch}", check=False
    )
    if result.returncode != 0 or not result.stdout:
        return None
    landed = result.stdout.splitlines()[-1].strip()
    parents = run_git(repo_path, "rev-list", "--parents", "-n", "1", landed, check=False)
    if parents.returncode != 0 or len(parents.stdout.split()) < 3:
        return None
    return landed


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

    return _diff_changes(repo_path, [f"{base_branch}...{branch_name}"])


def commit_changes(repo_path: str | Path, from_sha: str, to_sha: str) -> list[FileChange]:
    """Return the files that differ between two commits, ``from_sha`` to ``to_sha``.

    The comparison is of the two trees (not a merge base), so it is what a
    step did to the branch between the two heads. Raises ``GitError`` when git
    cannot compare.
    """

    return _diff_changes(repo_path, [from_sha, to_sha])


def _diff_changes(repo_path: str | Path, revisions: list[str]) -> list[FileChange]:
    """The files one ``git diff`` of ``revisions`` changes, with counts and kinds."""

    range_arg = " ".join(revisions)
    code, numstat = _git_bytes(repo_path, ["diff", "--numstat", "-z", "-M", *revisions, "--"])
    if code != 0:
        raise GitError(f"git could not compare {range_arg} in {repo_path}")
    code, name_status = _git_bytes(repo_path, ["diff", "--name-status", "-z", "-M", *revisions, "--"])
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


@dataclass(frozen=True, slots=True)
class CommitLine:
    """One commit: its full sha and its subject."""

    sha: str
    subject: str


def commits_between(repo_path: str | Path, from_sha: str, to_ref: str) -> list[CommitLine]:
    """Return the commits in ``to_ref`` that ``from_sha`` lacks, oldest first.

    Raises ``GitError`` when git cannot list them.
    """

    result = run_git(
        repo_path, "log", "--reverse", "--format=%H%x00%s", f"{from_sha}..{to_ref}", "--"
    )
    lines: list[CommitLine] = []
    for line in result.stdout.splitlines():
        sha, _, subject = line.partition("\0")
        if sha:
            lines.append(CommitLine(sha=sha, subject=subject))
    return lines


def is_ancestor(repo_path: str | Path, ancestor: str, descendant: str) -> bool:
    """Return whether ``ancestor`` is in the history of ``descendant``."""

    return run_git(repo_path, "merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0


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


def path_diff(repo_path: str | Path, from_sha: str, to_sha: str, path: str) -> str:
    """The unified diff of one path between two commits, as text.

    The path is a literal pathspec after ``--``, never parsed as a glob, a
    revision or an option.
    """

    code, output = _git_bytes(
        repo_path, ["--literal-pathspecs", "diff", from_sha, to_sha, "--", path]
    )
    if code != 0:
        raise GitError(f"git could not diff {path} between {from_sha[:10]} and {to_sha[:10]} in {repo_path}")
    return _decode(output)


def read_file_at(repo_path: str | Path, ref: str, path: str) -> str | None:
    """A file as it is at ``ref``, or None when there is no such file there."""

    result = run_git(repo_path, "show", f"{ref}:{path}", check=False)
    return result.stdout if result.returncode == 0 else None
