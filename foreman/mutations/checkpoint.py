"""A finished sprint's checkpoint (spec 6.4): a tag on the default branch,
and a note, the generated ``CHANGELOG.md`` and the generated copies
(``docs/STATUS.md``, ``docs/sprints/current.md``, ``docs/sprints/backlog.md``
and the sprint's archive copy) committed before it where the project asks for them (one commit).

Whoever finishes a sprint, a user (``transition_sprint``) or the engine
(``SprintFlow``), the same checkpoint follows. The sprint is finished
whatever happens here: a tag, a note or a changelog that could not be made is recorded
as ``engine.checkpoint_failed``, with the reason, and the sprint stays
completed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from ..domain.models import Project, Sprint, Task
from ..domain.settings import SettingsError, settings_of
from ..history.records import RunRecords
from ..notifications.delivery import NotificationDispatcher
from ..repo.git import (
    GitError,
    create_tag,
    follow_branch_in_checkout,
    head_sha,
    push_branch,
    push_tag,
    run_git,
    tag_commit,
)
from ..repo.worktrees import WorktreeError, WorktreeManager
from ..store import ForemanStore
from .changelog import CHANGELOG_FILE, stage_changelog
from .copies import render_copies, stage_copies

#: Where checkpoint notes go, in the repository.
NOTES_DIR = "docs/checkpoints"

#: The longest a tag's sprint part may be.
_SLUG_LIMIT = 48


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """What the checkpoint did: the tag and where it points, or why not."""

    tag: str | None = None
    sha: str | None = None
    note_path: str | None = None
    changelog_path: str | None = None
    problem: str | None = None


def tag_name(sprint: Sprint, completed: datetime) -> str:
    """``checkpoint-20261120-weight-of-evidence``: the day and the sprint's title."""

    slug = re.sub(r"[^a-z0-9]+", "-", (sprint.title or "").lower()).strip("-")
    slug = slug[:_SLUG_LIMIT].rstrip("-") or re.sub(r"[^a-z0-9]+", "-", sprint.id.lower()).strip("-")
    return f"checkpoint-{completed.astimezone(timezone.utc):%Y%m%d}-{slug}"


def note_text(
    sprint: Sprint,
    *,
    tag: str,
    completed: datetime,
    tasks: list[Task],
    follow_ups: list[Task],
) -> str:
    """The checkpoint note: the sprint, its tasks as they ended, and what it left to do."""

    def line(task: Task) -> str:
        return f"- {task.task_key or task.id}: {task.title}"

    done = [task for task in tasks if task.status == "done"]
    cancelled = [task for task in tasks if task.status == "cancelled"]
    parts = [
        f"# {sprint.title}",
        "",
        f"- Finished: {completed.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC",
        f"- Tag: `{tag}`",
    ]
    if (sprint.goal or "").strip():
        parts += ["", "## Goal", "", sprint.goal.strip()]
    parts += ["", "## Done", ""] + ([line(task) for task in done] or ["None."])
    if cancelled:
        parts += ["", "## Cancelled", ""] + [line(task) for task in cancelled]
    parts += ["", "## Follow-ups", ""]
    if follow_ups:
        parts += [f"{line(task)} ({_where(task)})" for task in follow_ups]
    else:
        parts += ["None filed during the sprint."]
    return "\n".join(parts) + "\n"


def _where(task: Task) -> str:
    return task.status.replace("_", " ")


def _completed_at(sprint: Sprint) -> datetime:
    text = sprint.completed_at or ""
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


class SprintCheckpoints:
    """Tags a finished sprint and, where asked, commits its note first."""

    def __init__(self, store: ForemanStore, records: RunRecords | None = None) -> None:
        self.store = store
        self.records = records or RunRecords(store, NotificationDispatcher(store))

    def record(self, project: Project, sprint: Sprint) -> Checkpoint:
        """Make the checkpoint of a completed sprint, once per time it is completed."""

        done = self._already(sprint)
        if done is not None:
            return done
        records: list[tuple[str, dict[str, Any]]] = []
        try:
            checkpoint = self._make(project, sprint, records)
        except (GitError, WorktreeError, SettingsError, OSError, ValueError) as exc:
            checkpoint = Checkpoint(problem=str(exc))
        if checkpoint.problem is None:
            records.append(
                (
                    "engine.checkpoint",
                    {
                        "sprint_id": sprint.id,
                        "sprint_title": sprint.title,
                        "completed_at": sprint.completed_at,
                        "tag": checkpoint.tag,
                        "sha": checkpoint.sha,
                        "note_path": checkpoint.note_path,
                        "changelog_path": checkpoint.changelog_path,
                    },
                )
            )
        else:
            records.append(
                (
                    "engine.checkpoint_failed",
                    {
                        "sprint_id": sprint.id,
                        "sprint_title": sprint.title,
                        "completed_at": sprint.completed_at,
                        "reason": checkpoint.problem,
                    },
                )
            )
        self._emit(project, sprint, records)
        return checkpoint

    def _already(self, sprint: Sprint) -> Checkpoint | None:
        """The checkpoint made for this completion, if there is one."""

        for event in reversed(self.store.list_sprint_events(sprint.id, event_types=["engine.checkpoint"])):
            if event.payload.get("sprint_id") == sprint.id and event.payload.get("completed_at") == sprint.completed_at:
                return Checkpoint(
                    tag=event.payload.get("tag"),
                    sha=event.payload.get("sha"),
                    note_path=event.payload.get("note_path"),
                    changelog_path=event.payload.get("changelog_path"),
                )
        return None

    def _make(
        self, project: Project, sprint: Sprint, records: list[tuple[str, dict[str, Any]]]
    ) -> Checkpoint:
        settings = settings_of(project)
        repo = Path(project.repo_path)
        branch = project.default_branch
        sha = head_sha(repo, f"refs/heads/{branch}")
        if sha is None:
            return Checkpoint(problem=f"The repository has no branch {branch!r} to tag.")
        completed = _completed_at(sprint)
        tag = self._free_tag(repo, tag_name(sprint, completed))

        note_path: str | None = None
        changelog_path: str | None = None
        integration: Path | None = None
        if settings.write_checkpoint_notes or settings.generate_changelog or settings.generate_copies:
            integration = WorktreeManager(project).ensure_integration()
            if settings.write_checkpoint_notes:
                note_path = f"{NOTES_DIR}/{tag}.md"
            committed = self._commit_files(
                integration,
                project,
                sprint,
                tag,
                completed,
                note_path=note_path,
                changelog=settings.generate_changelog,
                copies=settings.generate_copies,
            )
            if isinstance(committed, Checkpoint):
                return committed
            sha, changelog_path = committed
            followed = _checkout_record(project, sha)
            if followed is not None:
                records.append(followed)

        made = create_tag(repo, tag, sha, f"Sprint finished: {sprint.title}")
        if made.returncode != 0:
            return Checkpoint(
                problem=f"git could not tag {sha[:7]} as {tag}: {made.stderr or made.stdout}".strip(),
            )

        remote = settings.merge_push_remote
        if remote:
            # The default branch first, when the note moved it: a tag on a
            # commit the remote does not have would point at nothing there.
            if integration is not None:
                pushed = push_branch(integration, remote=remote, branch=branch)
                records.append(_push_record(pushed, {"remote": remote, "branch": branch, "sha": sha}))
            pushed = push_tag(repo, remote=remote, tag=tag)
            records.append(_push_record(pushed, {"remote": remote, "tag": tag, "sha": sha}))
        return Checkpoint(tag=tag, sha=sha, note_path=note_path, changelog_path=changelog_path)

    @staticmethod
    def _free_tag(repo: Path, name: str) -> str:
        """``name``, or ``name-2`` and on when a sprint of that title already finished that day."""

        candidate, number = name, 1
        while tag_commit(repo, candidate) is not None:
            number += 1
            candidate = f"{name}-{number}"
        return candidate

    def _commit_files(
        self,
        integration: Path,
        project: Project,
        sprint: Sprint,
        tag: str,
        completed: datetime,
        *,
        note_path: str | None,
        changelog: bool,
        copies: bool = False,
    ) -> tuple[str, str | None] | Checkpoint:
        """Write and commit the note, the changelog and the copies on the default branch.

        One commit. The new head and the changelog's path (``None`` when there
        were no change files), or why not.
        """

        paths: list[str] = []
        changelog_path: str | None = None
        written: list[Path] = []
        dirty = _dirty(integration)
        if dirty:
            return Checkpoint(problem=dirty)
        try:
            if note_path is not None:
                tasks = self.store.list_tasks(sprint_id=sprint.id)
                text = note_text(
                    sprint, tag=tag, completed=completed, tasks=tasks, follow_ups=self._follow_ups(tasks)
                )
                path = integration / note_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                written.append(path)
                run_git(integration, "add", "--", note_path)
                paths.append(note_path)
            if changelog:
                staged = stage_changelog(integration, sprint, completed)
                if staged:
                    changelog_path = CHANGELOG_FILE
                    paths += staged
            if copies:
                files = render_copies(self.store, project, finished=sprint, tag=tag or None, backlog=True)
                changed, created = stage_copies(integration, files)
                paths += changed
                written += created
        except (GitError, OSError, ValueError) as exc:
            # ValueError: a change file that is not UTF-8 text.
            self._undo(integration, paths, written)
            return Checkpoint(problem=f"The changelog, the copies or the checkpoint note could not be written: {exc}")
        what = "checkpoint note" if note_path else "changelog" if changelog_path else "status and sprint copies"
        done = self._commit(integration, paths, written, what, f"docs: {what}, {sprint.title}")
        if isinstance(done, Checkpoint):
            return done
        return done, changelog_path

    def _commit(
        self, integration: Path, paths: list[str], written: list[Path], what: str, message: str
    ) -> str | Checkpoint:
        """Commit ``paths`` and return the new head; the head as it is when there are none."""

        if not paths:
            head = head_sha(integration)
            return head if head else Checkpoint(problem="The default branch's head could not be read.")
        commit = run_git(integration, "commit", "--message", message, "--", *paths, check=False)
        if commit.returncode != 0:
            self._undo(integration, paths, written)
            return Checkpoint(
                problem=f"git could not commit the {what}: {commit.stderr or commit.stdout}".strip(),
            )
        new_head = head_sha(integration)
        if new_head is None:
            return Checkpoint(problem=f"The {what} was committed, but its commit could not be read.")
        return new_head

    @staticmethod
    def _undo(integration: Path, paths: list[str], written: list[Path]) -> None:
        """Leave the integration tree as it was after a commit that did not happen.

        The tree was clean before (``_dirty`` is checked first), so putting it
        back at its head, and removing what was created, restores it exactly,
        whatever was half written. A tree left dirty would block every merge.
        """

        run_git(integration, "reset", "--quiet", "--hard", "HEAD", check=False)
        run_git(integration, "clean", "--quiet", "-fd", check=False)
        for path in written:
            path.unlink(missing_ok=True)

    def active_sprint(self, project: Project) -> Sprint | None:
        """The project's active sprint, if one is."""

        return next((each for each in self.store.list_sprints(project.id) if each.status == "active"), None)

    def sprint_for_changelog(self, project: Project) -> Sprint | None:
        """The sprint a section written by hand is named after: the last finished."""

        sprints = self.store.list_sprints(project.id)
        finished = [sprint for sprint in sprints if sprint.status == "completed"]
        return max(finished, key=lambda sprint: sprint.completed_at or "", default=None)

    def write_changelog(self, project: Project, sprint: Sprint) -> Checkpoint:
        """Write the changelog by hand (``foreman changelog``): its own commit, no tag.

        ``problem`` says why when it could not be written; ``changelog_path`` is
        ``None`` when there were no change files.
        """

        records: list[tuple[str, dict[str, Any]]] = []
        try:
            integration = WorktreeManager(project).ensure_integration()
            committed = self._commit_files(
                integration, project, sprint, "", _completed_at(sprint), note_path=None, changelog=True
            )
            if isinstance(committed, Checkpoint):
                return committed
            sha, changelog_path = committed
            if changelog_path is None:
                return Checkpoint(sha=sha)
            followed = _checkout_record(project, sha)
            if followed is not None:
                records.append(followed)
            remote = settings_of(project).merge_push_remote
            if remote:
                pushed = push_branch(integration, remote=remote, branch=project.default_branch)
                records.append(_push_record(pushed, {"remote": remote, "branch": project.default_branch, "sha": sha}))
            return Checkpoint(sha=sha, changelog_path=changelog_path)
        except (GitError, WorktreeError, SettingsError, OSError, ValueError) as exc:
            return Checkpoint(problem=str(exc))
        finally:
            self._emit(project, sprint, records)

    def copies_on(self, project: Project) -> bool:
        """Whether the project has Foreman write its status and sprint copies."""

        try:
            return settings_of(project).generate_copies
        except SettingsError:
            return False

    def write_copies(
        self, project: Project, sprint: Sprint, *, why: str, archive: bool = False, backlog: bool = False
    ) -> Checkpoint:
        """Write ``docs/STATUS.md`` and ``docs/sprints/current.md`` (and more, as below) in a commit of their own.

        Done when a sprint starts and by ``foreman copies``; a sprint's finish
        writes them, and the backlog's copy, in its checkpoint's commit instead.
        With ``archive`` and a finished ``sprint``, its archive copy is written
        too; with ``backlog``, ``docs/sprints/backlog.md``. Never raises:
        ``problem`` says why nothing was written, and ``sha`` is the new head
        (``None`` when nothing differed). The outcome is recorded on the sprint
        (ADR-0037).
        """

        records: list[tuple[str, dict[str, Any]]] = []
        try:
            integration = WorktreeManager(project).ensure_integration()
            files = render_copies(
                self.store,
                project,
                finished=sprint if archive and sprint.status == "completed" else None,
                backlog=backlog,
            )
            dirty = _dirty(integration)
            if dirty:
                records.append(("engine.copies_failed", {"sprint_id": sprint.id, "reason": dirty}))
                return Checkpoint(problem=dirty)
            try:
                changed, created = stage_copies(integration, files)
            except (GitError, OSError):
                self._undo(integration, [], [])
                raise
            if not changed:
                return Checkpoint()
            done = self._commit(
                integration, changed, created, "status and sprint copies", f"docs: status and sprint copies, {why}"
            )
            if isinstance(done, Checkpoint):
                records.append(("engine.copies_failed", {"sprint_id": sprint.id, "reason": done.problem}))
                return done
            followed = _checkout_record(project, done)
            if followed is not None:
                records.append(followed)
            remote = settings_of(project).merge_push_remote
            if remote:
                pushed = push_branch(integration, remote=remote, branch=project.default_branch)
                records.append(_push_record(pushed, {"remote": remote, "branch": project.default_branch, "sha": done}))
            records.append(("engine.copies_written", {"sprint_id": sprint.id, "sha": done, "paths": changed, "why": why}))
            return Checkpoint(sha=done, changelog_path=None)
        except (GitError, WorktreeError, SettingsError, OSError, ValueError) as exc:
            records.append(("engine.copies_failed", {"sprint_id": sprint.id, "reason": str(exc)}))
            return Checkpoint(problem=str(exc))
        finally:
            self._emit(project, sprint, records)

    def _follow_ups(self, tasks: list[Task]) -> list[Task]:
        """The tasks agents filed while working on this sprint's tasks."""

        found: list[Task] = []
        seen: set[str] = set()
        for task in tasks:
            for event in self.store.list_events(task_id=task.id):
                if event.event_type != "engine.task_created":
                    continue
                filed_id = str(event.payload.get("task_id") or "")
                filed = self.store.get_task(filed_id) if filed_id and filed_id not in seen else None
                if filed is not None:
                    seen.add(filed_id)
                    found.append(filed)
        return found

    def _emit(self, project: Project, sprint: Sprint, records: list[tuple[str, dict[str, Any]]]) -> None:
        """Keep the records as the sprint's own (ADR-0037)."""

        for event_type, payload in records:
            self.records.emit_sprint_event(sprint, event_type, payload)


def _checkout_record(project: Project, sha: str) -> tuple[str, dict[str, Any]] | None:
    """Bring the project's own checkout to the note's commit, as a merge does (ADR-0031)."""

    try:
        followed = follow_branch_in_checkout(project.repo_path, project.default_branch, sha)
    except (GitError, OSError) as exc:
        return (
            "engine.checkout_behind",
            {"path": str(project.repo_path), "branch": project.default_branch, "sha": sha, "reason": str(exc)},
        )
    if followed.state == "updated":
        return (
            "engine.checkout_updated",
            {"path": str(project.repo_path), "branch": project.default_branch, "from_sha": followed.from_sha, "sha": sha},
        )
    if followed.state == "left":
        return (
            "engine.checkout_behind",
            {"path": str(project.repo_path), "branch": project.default_branch, "sha": sha, "reason": followed.reason},
        )
    return None


def _push_record(result: Any, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """What pushing a branch or a tag said: pushed, or why not."""

    if result.returncode == 0:
        return ("engine.push", payload)
    return ("engine.push_failed", {**payload, "error": result.stderr or result.stdout or "git push failed"})


def _dirty(integration: Path) -> str | None:
    """Why Foreman will not write in the integration tree now, or ``None`` when it is clean."""

    status = run_git(integration, "status", "--porcelain", "--untracked-files=all", check=False)
    if status.returncode != 0:
        return f"git could not read the integration worktree's state: {status.stderr or status.stdout}".strip()
    if status.stdout.strip():
        lines = status.stdout.strip().splitlines()
        shown = ", ".join(line[3:] for line in lines[:5]) + (" …" if len(lines) > 5 else "")
        return (
            f"The integration worktree ({integration}) has changes that are not committed ({shown}). "
            "Commit or discard them there, then try again."
        )
    return None
