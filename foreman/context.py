"""Runtime context projection helpers for Foreman."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import Lease, Project, Sprint, Task
from .settings import settings_of
from .scaffold import DEFAULT_CONTEXT_DIR
from .store import ForemanStore


@dataclass(slots=True)
class ProjectContextProjection:
    """Rendered runtime context for one project.

    ``mirror_dirs`` are additional directories that receive the same two
    files. The engine passes the task worktree's own context directory so an
    agent working inside its worktree finds ``.foreman/context.md`` where it
    is working, not only in the operator's checkout.
    """

    context_path: Path
    status_path: Path
    context_markdown: str
    status_markdown: str
    mirror_dirs: tuple[Path, ...] = ()

    @property
    def written_paths(self) -> tuple[Path, ...]:
        """Return the runtime files written by this projection."""

        paths: list[Path] = [self.context_path, self.status_path]
        for directory in self.mirror_dirs:
            paths.append(directory / self.context_path.name)
            paths.append(directory / self.status_path.name)
        return tuple(paths)

    def write(self) -> tuple[Path, ...]:
        """Write the rendered runtime context to disk."""

        for path in self.written_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            markdown = (
                self.context_markdown
                if path.name == self.context_path.name
                else self.status_markdown
            )
            path.write_text(markdown, encoding="utf-8")
        return self.written_paths


def build_project_context(
    store: ForemanStore,
    project: Project,
    *,
    current_task: Task | None = None,
    carried_output: str | None = None,
    mirror_dirs: tuple[Path, ...] = (),
) -> ProjectContextProjection:
    """Render the runtime context snapshot for one project."""

    sprints = store.list_sprints(project.id)
    tasks = [_coalesce_current_task(task, current_task) for task in store.list_tasks(project_id=project.id)]
    active_sprint = next((sprint for sprint in sprints if sprint.status == "active"), None)
    active_tasks = [
        task for task in tasks if active_sprint is not None and task.sprint_id == active_sprint.id
    ]

    # If there's a current task, look up its active lease (without the secret token)
    active_lease: Lease | None = None
    if current_task is not None:
        lease = store.get_active_lease(
            project_id=project.id,
            resource_type="task",
            resource_id=current_task.id,
        )
        if lease is not None:
            # Create a safe view of the lease (no lease_token)
            active_lease = Lease(
                id=lease.id,
                project_id=lease.project_id,
                resource_type=lease.resource_type,
                resource_id=lease.resource_id,
                holder_id=lease.holder_id,
                lease_token="[REDACTED]",  # Never expose token in context
                fencing_token=lease.fencing_token,
                status=lease.status,
                acquired_at=lease.acquired_at,
                heartbeat_at=lease.heartbeat_at,
                expires_at=lease.expires_at,
                released_at=lease.released_at,
            )

    runtime_dir = context_directory(project)
    return ProjectContextProjection(
        context_path=runtime_dir / "context.md",
        status_path=runtime_dir / "status.md",
        mirror_dirs=tuple(
            directory for directory in mirror_dirs if directory != runtime_dir
        ),
        context_markdown=render_sprint_context(
            project,
            active_sprint,
            active_tasks,
            current_task=current_task,
            carried_output=carried_output,
            active_lease=active_lease,
        ),
        status_markdown=render_project_status(
            project,
            sprints,
            tasks,
            active_sprint=active_sprint,
        ),
    )


def write_project_context(
    store: ForemanStore,
    project: Project,
    *,
    current_task: Task | None = None,
    carried_output: str | None = None,
    mirror_dirs: tuple[Path, ...] = (),
) -> ProjectContextProjection:
    """Render and write the runtime context snapshot for one project."""

    projection = build_project_context(
        store,
        project,
        current_task=current_task,
        carried_output=carried_output,
        mirror_dirs=mirror_dirs,
    )
    projection.write()
    return projection


def context_directory(project: Project, *, root: Path | None = None) -> Path:
    """Return the configured runtime context directory for one project.

    ``root`` renders the same relative layout under another checkout — the
    task's worktree — so the agent finds the projection where it works. An
    absolute ``context_dir`` is shared by every checkout and ignores ``root``.
    """

    configured = settings_of(project).context_dir.strip()
    raw_path = Path(configured or DEFAULT_CONTEXT_DIR).expanduser()
    if raw_path.is_absolute():
        return raw_path
    return (root or Path(project.repo_path)) / raw_path


def relative_project_path(project: Project, path: Path) -> str:
    """Return a project-relative path when possible."""

    repo_root = Path(project.repo_path)
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def render_sprint_context(
    project: Project,
    sprint: Sprint | None,
    tasks: list[Task],
    *,
    current_task: Task | None = None,
    carried_output: str | None = None,
    active_lease: Lease | None = None,
) -> str:
    """Render the sprint-scoped runtime context markdown."""

    lines = [
        "# Sprint Context",
        "",
        f"Project: {project.name}",
        f"Workflow: {project.workflow_id}",
    ]
    if sprint is None:
        lines.extend(["", "No active sprint."])
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            f"Sprint: {sprint.title}",
            f"Status: {sprint.status}",
        ]
    )
    if sprint.goal:
        lines.append(f"Goal: {sprint.goal}")

    lines.extend(["", "## Tasks"])
    if not tasks:
        lines.append("- No tasks recorded for the active sprint.")
    else:
        current_task_id = current_task.id if current_task is not None else None
        for task in tasks:
            marker = "* " if task.id == current_task_id else "- "
            branch = f" | branch={task.branch_name}" if task.branch_name else ""
            lines.append(f"{marker}[{task.status}] {task.title} ({task.id}){branch}")

    lines.extend(["", "## Current Task"])
    if current_task is None:
        lines.append("No current task selected.")
    else:
        lines.extend(
            [
                f"Title: {current_task.title}",
                f"ID: {current_task.id}",
                f"Type: {current_task.task_type}",
                f"Status: {current_task.status}",
            ]
        )
        if current_task.branch_name:
            lines.append(f"Branch: {current_task.branch_name}")
        if current_task.worktree_path:
            lines.append(f"Worktree: {current_task.worktree_path}")
        if current_task.blocked_reason:
            lines.append(f"Blocked reason: {current_task.blocked_reason}")
        if current_task.workflow_current_step:
            lines.append(f"Workflow step: {current_task.workflow_current_step}")
        lines.extend(
            [
                "",
                "### Description",
                current_task.description or "(none)",
                "",
                "### Acceptance Criteria",
                current_task.acceptance_criteria or "(none)",
                "",
                "### Carried Feedback",
                carried_output or "(none)",
            ]
        )
        if settings_of(project).task_selection_mode == "autonomous":
            # Only autonomous projects carry the self-selection contract; a
            # directed task has its title, branch, and criteria already.
            lines.extend(
                [
                    "",
                    "### Autonomous Signal Contract",
                    "You choose what this task is. In the first developer step, name it",
                    "by emitting signal.task_started with: title, criteria (the acceptance",
                    "criteria you will meet), and task_type. The engine has already put",
                    "you on this task's branch in its own worktree; stay on it.",
                ]
            )

        if active_lease is not None:
            lines.extend(
                [
                    "",
                    "### Active Lease",
                    f"Holder: {active_lease.holder_id}",
                    f"Status: {active_lease.status}",
                    f"Expires: {active_lease.expires_at}",
                ]
            )

    return "\n".join(lines) + "\n"


def render_project_status(
    project: Project,
    sprints: list[Sprint],
    tasks: list[Task],
    *,
    active_sprint: Sprint | None = None,
) -> str:
    """Render the project-scoped runtime status markdown."""

    lines = [
        "# Project Status",
        "",
        f"Project: {project.name}",
        f"Workflow: {project.workflow_id}",
        f"Default branch: {project.default_branch}",
        f"Context directory: {relative_project_path(project, context_directory(project))}",
        _format_task_counts(tasks),
        "",
        "## Sprints",
    ]
    if not sprints:
        lines.append("- No sprints recorded.")
    else:
        for sprint in sprints:
            lines.append(f"- [{sprint.status}] {sprint.title} ({sprint.id})")

    lines.extend(["", "## Completed Sprint Summaries"])
    completed_sprints = [sprint for sprint in sprints if sprint.status == "completed"]
    if not completed_sprints:
        lines.append("- No completed sprints yet.")
    else:
        tasks_by_sprint = _group_tasks_by_sprint(tasks)
        for sprint in completed_sprints:
            sprint_tasks = tasks_by_sprint.get(sprint.id, [])
            done_tasks = [task for task in sprint_tasks if task.status == "done"]
            lines.extend(
                [
                    f"### {sprint.title}",
                    f"Tasks completed: {len(done_tasks)}/{len(sprint_tasks)}",
                ]
            )
            if done_tasks:
                lines.append("Key deliverables:")
                for task in done_tasks:
                    lines.append(f"- {task.title}")
            else:
                lines.append("Key deliverables: (none recorded)")
            lines.append("")
        if lines[-1] == "":
            lines.pop()

    lines.extend(["", "## Current Sprint Detail"])
    if active_sprint is None:
        lines.append("No active sprint.")
    else:
        active_tasks = [task for task in tasks if task.sprint_id == active_sprint.id]
        lines.extend(
            [
                f"Title: {active_sprint.title}",
                f"Status: {active_sprint.status}",
            ]
        )
        if active_sprint.goal:
            lines.append(f"Goal: {active_sprint.goal}")
        lines.append(_format_task_counts(active_tasks))

    blocked_tasks = [task for task in tasks if task.status == "blocked"]
    lines.extend(["", "## Blocked Items"])
    if not blocked_tasks:
        lines.append("- No blocked tasks.")
    else:
        for task in blocked_tasks:
            reason = task.blocked_reason or "No reason recorded."
            lines.append(f"- {task.title} ({task.id}): {reason}")

    lines.extend(["", "## Open Decisions", "- Not yet persisted in SQLite."])
    return "\n".join(lines) + "\n"


def _coalesce_current_task(task: Task, current_task: Task | None) -> Task:
    if current_task is not None and current_task.id == task.id:
        return current_task
    return task


def _format_task_counts(tasks: list[Task]) -> str:
    counts = {
        "todo": 0,
        "in_progress": 0,
        "blocked": 0,
        "done": 0,
        "cancelled": 0,
    }
    for task in tasks:
        if task.status in counts:
            counts[task.status] += 1
    return (
        "Task counts: "
        f"todo={counts['todo']} "
        f"in_progress={counts['in_progress']} "
        f"blocked={counts['blocked']} "
        f"done={counts['done']} "
        f"cancelled={counts['cancelled']}"
    )


def _group_tasks_by_sprint(tasks: list[Task]) -> dict[str, list[Task]]:
    grouped: dict[str, list[Task]] = {}
    for task in tasks:
        grouped.setdefault(task.sprint_id, []).append(task)
    return grouped
