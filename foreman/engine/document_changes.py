"""A merge that changes a document unfinished tasks rest on says so to each.

Assay's "stale binding", kept small: each such task gets one line in its
Activity and its next agent step is told (``domain.rests_on.changed_text``).
Nothing in the task is changed and it is not stopped: a person or the manager
decides what the change means for it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..domain.models import Project, Task
from ..domain.rests_on import DocumentRef
from ..history.records import RunRecords
from ..repo.git import run_git
from ..store import ForemanStore

#: The tasks that are still to be done, filed work not yet accepted included.
#: A paused task is one of these held by a person (a pause is not a status).
#: A declined task is kept for the record and never runs, so it is not told.
UNFINISHED_STATUSES: tuple[str, ...] = ("triage", "todo", "in_progress", "blocked")

EVENT_TYPE = "engine.document_changed"
STEP = "document_changed"


def changed_paths(repo_path: str | Path, from_sha: str, to_sha: str) -> set[str] | None:
    """The paths that differ between two commits (a rename names both), or None when git cannot say."""

    result = run_git(repo_path, "diff", "--name-only", "--no-renames", "-z", from_sha, to_sha, "--", check=False)
    if result.returncode != 0:
        return None
    return {path for path in result.stdout.split("\0") if path}


def line_for(refs: Sequence[DocumentRef], merged: Task, sha: str) -> str:
    """The Activity line for one changed path: what changed, in whose merge, and the commit it was named at.

    ``refs`` are the task's entries for that path (one per heading it names).
    """

    who = f"{merged.task_key}'s" if merged.task_key else f"“{merged.title}”'s"
    commits = " and ".join(dict.fromkeys(ref.commit[:7] for ref in refs))
    label = ", ".join(ref.label() for ref in refs)
    return f"{label} changed in {who} merge ({sha[:7]}) since this task named it at {commits}"


def note_document_changes(
    records: RunRecords,
    store: ForemanStore,
    project: Project,
    merged: Task,
    *,
    from_sha: str | None,
    sha: str | None,
) -> list[str]:
    """Write one line to each unfinished task for each document it rests on that the merge changed.

    A path the task names under several headings is one line, not one per heading.

    ``from_sha`` and ``sha`` are the default branch before and after the merge.
    Returns the lines written. A merge git cannot compare writes nothing: the
    merge is done whatever happens here.
    """

    if not from_sha or not sha:
        return []
    changed = changed_paths(project.repo_path, from_sha, sha)
    if not changed:
        return []
    lines: list[str] = []
    for task in store.list_tasks(project_id=project.id, statuses=UNFINISHED_STATUSES):
        if task.id == merged.id:
            continue
        by_path: dict[str, list[DocumentRef]] = {}
        for ref in task.rests_on:
            if ref.path in changed:
                by_path.setdefault(ref.path, []).append(ref)
        for refs in by_path.values():
            line = line_for(refs, merged, sha)
            run = records.create_system_run(task, workflow_step=STEP, outcome="noted", detail=line)
            records.emit_event(run, EVENT_TYPE, event_payload(refs, merged, sha))
            lines.append(line)
    return lines


def event_payload(refs: Sequence[DocumentRef], merged: Task, sha: str) -> dict[str, Any]:
    """One path's change: ``heading`` and ``named_commit`` are the first entry's,
    ``headings`` and ``named_commits`` every entry's for that path."""

    first = refs[0]
    return {
        "path": first.path,
        "heading": first.heading,
        "headings": [ref.heading for ref in refs],
        "named_commit": first.commit,
        "named_commits": list(dict.fromkeys(ref.commit for ref in refs)),
        "merge_sha": sha,
        "merged_task_id": merged.id,
        "merged_task_key": merged.task_key or "",
    }


def changes_by_document(store: ForemanStore, task: Task) -> dict[tuple[str, str], Mapping[str, str]]:
    """For each entry the task rests on whose file changed since it was named, the latest change.

    Keyed by the entry (path and heading). A change counts for every entry of
    its path that is still named at a commit the change was noted against,
    whatever its heading: changing the heading does not clear it, and marking
    the document read (``Mutations.restamp_document``, which stamps the commit
    now) does.
    """

    found: dict[tuple[str, str], Mapping[str, str]] = {}
    for event in store.list_events(task_id=task.id):
        if event.event_type != EVENT_TYPE:
            continue
        payload = event.payload
        path = str(payload.get("path") or "")
        commits = payload.get("named_commits")
        noted = {str(item) for item in commits} if isinstance(commits, list) else set()
        noted.add(str(payload.get("named_commit") or ""))
        for ref in task.rests_on:
            if ref.path == path and ref.commit and ref.commit in noted:
                found[ref.key] = {**payload, "timestamp": event.timestamp}
    return found
