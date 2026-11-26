"""A merge that changes a document unfinished tasks rest on says so to each.

Assay's "stale binding", kept small: each such task gets one line in its
Activity and its next agent step is told (``domain.rests_on.changed_text``).
Nothing in the task is changed and it is not stopped: a person or the manager
decides what the change means for it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ..domain.models import Project, Task
from ..domain.rests_on import DocumentRef
from ..history.records import RunRecords
from ..repo.git import run_git
from ..store import ForemanStore

#: The tasks that are still to be done: a paused one is one of these held by a person.
UNFINISHED_STATUSES: tuple[str, ...] = ("todo", "in_progress", "blocked")

EVENT_TYPE = "engine.document_changed"
STEP = "document_changed"


def changed_paths(repo_path: str | Path, from_sha: str, to_sha: str) -> set[str] | None:
    """The paths that differ between two commits (a rename names both), or None when git cannot say."""

    result = run_git(repo_path, "diff", "--name-only", "--no-renames", "-z", from_sha, to_sha, "--", check=False)
    if result.returncode != 0:
        return None
    return {path for path in result.stdout.split("\0") if path}


def line_for(ref: DocumentRef, merged: Task, sha: str) -> str:
    """The Activity line: what changed, in whose merge, and the commit it was named at."""

    who = f"{merged.task_key}'s" if merged.task_key else f"“{merged.title}”'s"
    return f"{ref.label()} changed in {who} merge ({sha[:7]}) since this task named it at {ref.commit[:7]}"


def note_document_changes(
    records: RunRecords,
    store: ForemanStore,
    project: Project,
    merged: Task,
    *,
    from_sha: str | None,
    sha: str | None,
) -> list[str]:
    """Write one line to each unfinished task that rests on a document the merge changed.

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
        for ref in task.rests_on:
            if ref.path not in changed:
                continue
            line = line_for(ref, merged, sha)
            run = records.create_system_run(task, workflow_step=STEP, outcome="noted", detail=line)
            records.emit_event(run, EVENT_TYPE, event_payload(ref, merged, sha))
            lines.append(line)
    return lines


def event_payload(ref: DocumentRef, merged: Task, sha: str) -> dict[str, str]:
    return {
        "path": ref.path,
        "heading": ref.heading,
        "named_commit": ref.commit,
        "merge_sha": sha,
        "merged_task_id": merged.id,
        "merged_task_key": merged.task_key or "",
    }


def changes_by_document(store: ForemanStore, task: Task) -> dict[tuple[str, str], Mapping[str, str]]:
    """For each document the task rests on that changed since it was named, the latest change.

    Only a change noted against the commit the document is named at counts, so
    naming the document again (at the commit now) clears it.
    """

    found: dict[tuple[str, str], Mapping[str, str]] = {}
    named = {ref.key: ref.commit for ref in task.rests_on}
    for event in store.list_events(task_id=task.id):
        if event.event_type != EVENT_TYPE:
            continue
        payload = event.payload
        key = (str(payload.get("path") or ""), str(payload.get("heading") or ""))
        if named.get(key) and named[key] == payload.get("named_commit"):
            found[key] = {**payload, "timestamp": event.timestamp}
    return found
