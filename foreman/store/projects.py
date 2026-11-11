"""Projects."""

from __future__ import annotations

from typing import Any

from ..models import (
    Project,
)

from .base import (
    StoreBase,
    retried_on_lock,
)
from .rows import (
    _json_dumps,
    _row_to_project,
)


class ProjectStore(StoreBase):
    """Projects."""

    def project_activity_token(self, project_id: str) -> tuple[Any, ...]:
        """Return a value that changes when a project has something new to do.

        ``data_version`` moves on every commit by any connection: another
        project's engine, a lock heartbeat, an agent's event stream. An idle
        engine uses this to tell those apart from a change to its own
        project's settings, sprints, tasks, commands or queued notifications.
        """

        row = self._connection.execute(
            """
            SELECT
                (SELECT COALESCE(updated_at, '') || ':' || COALESCE(settings_json, '')
                   FROM projects WHERE id = :project),
                (SELECT COALESCE(group_concat(id || '=' || status, ','), '')
                   FROM (SELECT id, status FROM sprints
                          WHERE project_id = :project ORDER BY id)),
                (SELECT COALESCE(group_concat(
                            id || '=' || status || '@' || COALESCE(workflow_current_step, '')
                               || '/' || COALESCE(sprint_id, ''), ','), '')
                   FROM (SELECT id, status, workflow_current_step, sprint_id FROM tasks
                          WHERE project_id = :project ORDER BY id)),
                (SELECT COUNT(*) FROM engine_commands
                  WHERE project_id = :project AND status = 'pending'),
                (SELECT COUNT(*) FROM notification_deliveries
                  WHERE project_id = :project AND status = 'pending')
            """,
            {"project": project_id},
        ).fetchone()
        return tuple(row) if row is not None else ()

    @retried_on_lock
    def save_project(self, project: Project) -> Project:
        """Insert or update a project record."""

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO projects (
                    id, name, repo_path, spec_path, methodology, workflow_id,
                    default_branch, autonomy_level, settings_json, task_key_prefix,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    repo_path = excluded.repo_path,
                    spec_path = excluded.spec_path,
                    methodology = excluded.methodology,
                    workflow_id = excluded.workflow_id,
                    default_branch = excluded.default_branch,
                    autonomy_level = excluded.autonomy_level,
                    settings_json = excluded.settings_json,
                    task_key_prefix = excluded.task_key_prefix,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    project.id,
                    project.name,
                    project.repo_path,
                    project.spec_path,
                    project.methodology,
                    project.workflow_id,
                    project.default_branch,
                    project.autonomy_level,
                    _json_dumps(project.settings),
                    project.task_key_prefix,
                    project.created_at,
                    project.updated_at,
                ),
            )
        return project

    def get_project(self, project_id: str) -> Project | None:
        """Return one project by identifier."""

        row = self._connection.execute(
            "SELECT * FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        return _row_to_project(row) if row else None

    def find_project_by_repo_path(self, repo_path: str) -> Project | None:
        """Return one project by repository path, if it exists."""

        row = self._connection.execute(
            "SELECT * FROM projects WHERE repo_path = ? ORDER BY created_at ASC, id ASC LIMIT 1",
            (repo_path,),
        ).fetchone()
        return _row_to_project(row) if row else None

    def list_projects(self) -> list[Project]:
        """List persisted projects in stable order."""

        rows = self._connection.execute(
            "SELECT * FROM projects ORDER BY created_at ASC, id ASC"
        ).fetchall()
        return [_row_to_project(row) for row in rows]

    def count_projects(self) -> int:
        """Return the number of tracked projects."""

        row = self._connection.execute(
            "SELECT COUNT(*) AS value FROM projects"
        ).fetchone()
        return int(row["value"])
