"""What a step did to the repository, as the facts the engine records (ADR-0038).

Git is read here, when a step ends, and the answer is stored on the step's
events. Nothing that shows it asks git again. A read that fails leaves its
fact out: the step it describes is never failed by it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..repo.git import FileChange, GitError, commit_changes, commits_between, is_ancestor

#: Most files one ``engine.step_changes`` event lists; ``files_total`` says how many there were.
STEP_FILES_CAP = 200
#: Most commits one ``engine.merge`` event lists; ``commits_total`` says how many there were.
MERGE_COMMITS_CAP = 50


def _file_item(change: FileChange) -> dict[str, Any]:
    """One file as recorded: a binary file has no line counts."""

    return {
        "path": change.path,
        "added": None if change.binary else change.added,
        "removed": None if change.binary else change.deleted,
        "status": change.status,
    }


def changes_between(repo_path: str | Path, from_sha: str, to_sha: str) -> dict[str, Any] | None:
    """The files, and the lines added and removed, going from one commit to another.

    ``None`` when git cannot compare them.
    """

    try:
        changes = commit_changes(repo_path, from_sha, to_sha)
    except (GitError, OSError):
        return None
    changes.sort(key=lambda change: change.path)
    return {
        "files": [_file_item(change) for change in changes[:STEP_FILES_CAP]],
        "files_total": len(changes),
        "added": sum(change.added for change in changes if not change.binary),
        "removed": sum(change.deleted for change in changes if not change.binary),
    }


def step_changes_payload(
    repo_path: str | Path,
    default_branch: str,
    from_sha: str | None,
    to_sha: str | None,
) -> dict[str, Any] | None:
    """The ``engine.step_changes`` payload, or None when the branch did not move or git could not say."""

    if not from_sha or not to_sha or from_sha == to_sha:
        return None
    changes = changes_between(repo_path, from_sha, to_sha)
    if changes is None:
        return None
    try:
        # Said now, while it is known: the reader does not ask git.
        from_default = is_ancestor(repo_path, from_sha, f"refs/heads/{default_branch}")
    except (GitError, OSError):
        from_default = False
    return {
        "from_sha": from_sha,
        "to_sha": to_sha,
        "from_default_branch": from_default,
        **changes,
    }


def merge_facts(
    repo_path: str | Path,
    target_before: str | None,
    branch_head: str | None,
    merge_sha: str | None,
) -> dict[str, Any]:
    """What a landed merge brought in, as fields of the ``engine.merge`` payload.

    Only the fields git could give are present.
    """

    facts: dict[str, Any] = {}
    if not target_before:
        return facts
    facts["target_before"] = target_before
    if branch_head:
        try:
            commits = commits_between(repo_path, target_before, branch_head)
        except (GitError, OSError):
            commits = None
        if commits is not None:
            facts["commits"] = [
                {"sha": commit.sha, "subject": commit.subject} for commit in commits[:MERGE_COMMITS_CAP]
            ]
            facts["commits_total"] = len(commits)
    if merge_sha:
        changes = changes_between(repo_path, target_before, merge_sha)
        if changes is not None:
            facts["changes"] = changes
    return facts
