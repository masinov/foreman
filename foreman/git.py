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
    """Check out one branch, optionally creating it from a base branch."""

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
    return GitMergeResult(success=False, detail=detail)


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
