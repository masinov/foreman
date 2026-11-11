"""What an agent is told: the pieces of repository state a prompt carries."""

from __future__ import annotations

from pathlib import Path

from ..git import GitError, changed_files, recent_commits, status_text


def load_repo_instructions(repo_path: str) -> str:
    agents_path = Path(repo_path) / "AGENTS.md"
    if not agents_path.is_file():
        return ""
    return agents_path.read_text(encoding="utf-8")


def safe_git_status(repo_path: str | Path) -> str:
    try:
        return status_text(repo_path)
    except GitError:
        return ""


def safe_changed_files(
    repo_path: str,
    target_branch: str,
    branch_name: str | None,
) -> str:
    try:
        return changed_files(
            repo_path,
            target_branch=target_branch,
            branch_name=branch_name,
        )
    except GitError:
        return ""


def safe_recent_commits(repo_path: str, branch_name: str | None) -> str:
    try:
        return recent_commits(repo_path, branch_name=branch_name)
    except GitError:
        return ""
