"""Reads that span a project's sprints, tasks, runs and engine for the dashboard.

The workspace page, the needs-you list and the milestone feed each answer one
question about every project at once. Asking it through the per-aggregate
reads (one ``task_counts`` per sprint, one ``run_totals`` per sprint) costs a
query per sprint or per task, so these reads group in SQL instead. Each method
here is one statement, however many projects, sprints or tasks there are.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from ..models import Sprint, Task, TASK_STATUSES
from .base import ENGINE_RESOURCE_TYPE, StoreBase
from .rows import _row_to_sprint, _row_to_task

#: Every kind of milestone, in the order the API documents them.
MILESTONE_KINDS: tuple[str, ...] = (
    "sprint_started",
    "sprint_finished",
    "task_merged",
    "engine_started",
    "engine_paused",
    "engine_resumed",
    "engine_stopped",
)

#: Statuses a sprint can be listed by.
SPRINT_LIST_STATUSES: tuple[str, ...] = ("active", "planned", "completed")

#: Orders a sprint list can come in. ``queue`` is the order the sprints run
#: in; ``recent`` puts the most recently finished first, then the most
#: recently started, then the rest newest-queued first.
SPRINT_LIST_ORDERS: dict[str, str] = {
    "queue": "order_index ASC, created_at ASC, id ASC",
    "recent": (
        "completed_at IS NULL, completed_at DESC, started_at IS NULL, "
        "started_at DESC, order_index DESC, id DESC"
    ),
}

#: A moment as a number, so ``...Z`` and ``...+00:00`` timestamps (both are
#: stored) order against each other, which plain text comparison does not.
_INSTANT = "julianday({column})"

# One row per milestone, from rows the engine already writes: sprint columns,
# the merge event, completed engine commands, and the engine lock's lease
# history. Nothing is stored for the feed itself.
#
# The backlog is not a sprint (ADR-0021), so it has no start or finish.
#
# An engine stop is the end of an engine lease, released or expired. When a
# `shutdown` command completed during that lease, the command names who asked.
_MILESTONES_SQL = f"""
    SELECT 'sprint_started' AS kind, s.started_at AS at, s.project_id AS project_id,
           s.id AS sprint_id, NULL AS task_id, NULL AS actor, s.id AS ref
    FROM sprints s
    WHERE s.started_at IS NOT NULL AND s.kind = 'sprint'
    UNION ALL
    SELECT 'sprint_finished', s.completed_at, s.project_id, s.id, NULL, NULL, s.id
    FROM sprints s
    WHERE s.status = 'completed' AND s.completed_at IS NOT NULL
      AND s.kind = 'sprint'
    UNION ALL
    SELECT 'task_merged', e.timestamp, e.project_id, t.sprint_id, e.task_id, NULL, e.id
    FROM events e JOIN tasks t ON t.id = e.task_id
    WHERE e.event_type = 'engine.merge'
    UNION ALL
    SELECT CASE c.command WHEN 'pause' THEN 'engine_paused' ELSE 'engine_resumed' END,
           COALESCE(c.completed_at, c.requested_at), c.project_id, NULL, NULL,
           c.requested_by, c.id
    FROM engine_commands c
    WHERE c.status = 'completed' AND c.command IN ('pause', 'resume')
    UNION ALL
    SELECT 'engine_started', l.acquired_at, l.project_id, NULL, NULL, NULL, l.id
    FROM leases l
    WHERE l.resource_type = '{ENGINE_RESOURCE_TYPE}'
    UNION ALL
    SELECT 'engine_stopped',
           CASE l.status WHEN 'released' THEN COALESCE(l.released_at, l.expires_at)
                         ELSE l.expires_at END,
           l.project_id, NULL, NULL,
           (SELECT c.requested_by FROM engine_commands c
             WHERE c.project_id = l.project_id AND c.command = 'shutdown'
               AND c.status = 'completed'
               AND c.completed_at BETWEEN l.acquired_at
                   AND COALESCE(l.released_at, l.expires_at)
             ORDER BY c.completed_at DESC LIMIT 1),
           l.id
    FROM leases l
    WHERE l.resource_type = '{ENGINE_RESOURCE_TYPE}' AND l.status IN ('released', 'expired')
"""


@dataclass(frozen=True, slots=True)
class MilestoneRow:
    """One milestone as the database records it, before it is described."""

    kind: str
    at: str
    project_id: str
    project_name: str
    sprint_id: str | None
    sprint_title: str | None
    task_id: str | None
    task_key: str | None
    task_title: str | None
    actor: str | None


class OverviewStore(StoreBase):
    """Cross-project reads for the workspace, needs-you and milestone views."""

    # ── sprints ───────────────────────────────────────────────────────────

    def list_active_sprints(self) -> dict[str, Sprint]:
        """Return each project's active sprint, keyed by project id.

        The one ``get_active_sprint`` picks per project, in one statement.
        """

        rows = self._connection.execute(
            """
            SELECT s.* FROM sprints s
            WHERE s.status = 'active' AND s.kind = 'sprint'
              AND s.id = (
                SELECT a.id FROM sprints a
                WHERE a.project_id = s.project_id AND a.status = 'active'
                  AND a.kind = 'sprint'
                ORDER BY a.started_at DESC, a.created_at DESC, a.id DESC
                LIMIT 1
              )
            """
        ).fetchall()
        return {row["project_id"]: _row_to_sprint(row) for row in rows}

    def sprint_titles(self, sprint_ids: Sequence[str]) -> dict[str, str]:
        """Return the title of each named sprint, in one statement."""

        if not sprint_ids:
            return {}
        rows = self._connection.execute(
            f"SELECT id, title FROM sprints WHERE id IN ({', '.join('?' for _ in sprint_ids)})",
            tuple(sprint_ids),
        ).fetchall()
        return {row["id"]: row["title"] for row in rows}

    def page_project_sprints(
        self,
        project_id: str,
        *,
        statuses: Sequence[str] | None = None,
        query: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str = "queue",
    ) -> tuple[list[Sprint], int]:
        """Return one page of a project's sprints and how many match in all.

        Sprints keep their queue order unless ``order`` is ``recent`` (see
        :data:`SPRINT_LIST_ORDERS`). ``query`` matches, ignoring case, a part
        of the title (the sprint number is part of the title) or of the id.
        """

        if order not in SPRINT_LIST_ORDERS:
            raise ValueError(f"Unknown sprint order: {order}")

        filters = ["project_id = ?", "kind = 'sprint'"]
        params: list[Any] = [project_id]
        if statuses:
            filters.append(f"status IN ({', '.join('?' for _ in statuses)})")
            params.extend(statuses)
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            filters.append("(title LIKE ? ESCAPE '\\' OR id LIKE ? ESCAPE '\\')")
            params.extend([f"%{escaped}%", f"%{escaped}%"])
        where = " AND ".join(filters)
        total = int(
            self._connection.execute(
                f"SELECT COUNT(*) AS n FROM sprints WHERE {where}", tuple(params)
            ).fetchone()["n"]
        )
        sql = (
            f"SELECT * FROM sprints WHERE {where} "
            f"ORDER BY {SPRINT_LIST_ORDERS[order]}"
        )
        page_params = list(params)
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            page_params.extend([max(0, int(limit)), max(0, int(offset))])
        rows = self._connection.execute(sql, tuple(page_params)).fetchall()
        return [_row_to_sprint(row) for row in rows], total

    # ── counts and spend, grouped ─────────────────────────────────────────

    def task_counts_by_sprint(self, sprint_ids: Sequence[str]) -> dict[str, dict[str, int]]:
        """Return task counts by status for each named sprint, in one statement."""

        counts = {
            sprint_id: {status: 0 for status in TASK_STATUSES} for sprint_id in sprint_ids
        }
        if not sprint_ids:
            return counts
        rows = self._connection.execute(
            f"""
            SELECT sprint_id, status, COUNT(*) AS value FROM tasks
            WHERE sprint_id IN ({', '.join('?' for _ in sprint_ids)})
            GROUP BY sprint_id, status
            """,
            tuple(sprint_ids),
        ).fetchall()
        for row in rows:
            counts[row["sprint_id"]][str(row["status"])] = int(row["value"])
        return counts

    def spend_by_sprint(self, sprint_ids: Sequence[str]) -> dict[str, float]:
        """Return the cost of every run, in dollars, for each named sprint."""

        spend = {sprint_id: 0.0 for sprint_id in sprint_ids}
        if not sprint_ids:
            return spend
        rows = self._connection.execute(
            f"""
            SELECT t.sprint_id AS sprint_id, COALESCE(SUM(r.cost_usd), 0.0) AS cost
            FROM runs r JOIN tasks t ON t.id = r.task_id
            WHERE t.sprint_id IN ({', '.join('?' for _ in sprint_ids)})
            GROUP BY t.sprint_id
            """,
            tuple(sprint_ids),
        ).fetchall()
        for row in rows:
            spend[row["sprint_id"]] = float(row["cost"])
        return spend

    def backlog_counts(self) -> dict[str, int]:
        """Count the work waiting in each project's backlog, by project id.

        Waiting means filed (``triage``) or accepted (``todo``) and not yet
        planned into a sprint; declined work is not waiting.
        """

        rows = self._connection.execute(
            """
            SELECT t.project_id AS project_id, COUNT(*) AS value
            FROM tasks t JOIN sprints b ON b.id = t.sprint_id
            WHERE b.kind = 'backlog' AND t.status IN ('triage', 'todo')
            GROUP BY t.project_id
            """
        ).fetchall()
        return {row["project_id"]: int(row["value"]) for row in rows}

    def page_backlog_tasks(
        self,
        project_id: str,
        *,
        statuses: Sequence[str],
        query: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[Task], int, dict[str, int]]:
        """Return one page of a project's backlog, the match total, and counts.

        Filed (``triage``) first, then accepted (``todo``), then declined;
        within each, in priority and queue order like every task list.
        ``query`` matches, ignoring case, part of the title, the key or the
        id. The counts are per status over the whole backlog, unfiltered.
        """

        base = (
            "FROM tasks t JOIN sprints b ON b.id = t.sprint_id "
            "WHERE b.project_id = ? AND b.kind = 'backlog'"
        )
        counts = {status: 0 for status in ("triage", "todo", "declined")}
        for row in self._connection.execute(
            f"SELECT t.status AS status, COUNT(*) AS n {base} GROUP BY t.status",
            (project_id,),
        ).fetchall():
            if row["status"] in counts:
                counts[row["status"]] = int(row["n"])

        if not statuses:
            return [], 0, counts
        where = base + f" AND t.status IN ({', '.join('?' for _ in statuses)})"
        params: list[Any] = [project_id, *statuses]
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where += (
                " AND (t.title LIKE ? ESCAPE '\\' OR t.task_key LIKE ? ESCAPE '\\'"
                " OR t.id LIKE ? ESCAPE '\\')"
            )
            params.extend([f"%{escaped}%"] * 3)
        total = int(
            self._connection.execute(f"SELECT COUNT(*) AS n {where}", tuple(params)).fetchone()["n"]
        )
        sql = (
            f"SELECT t.* {where} ORDER BY "
            "CASE t.status WHEN 'triage' THEN 0 WHEN 'todo' THEN 1 ELSE 2 END, "
            "t.priority ASC, t.order_index ASC, t.created_at ASC, t.id ASC"
        )
        page_params = list(params)
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            page_params.extend([max(0, int(limit)), max(0, int(offset))])
        rows = self._connection.execute(sql, tuple(page_params)).fetchall()
        return [_row_to_task(row) for row in rows], total, counts

    # ── what is waiting for a person ──────────────────────────────────────

    def list_tasks_awaiting_person(
        self, *, project_id: str | None = None
    ) -> list[tuple[Task, str]]:
        """Return every ``triage`` or ``blocked`` task with when it began waiting.

        Whether a blocked task waits for a decision or for a fix depends on its
        workflow, which the caller resolves. The moment is the end of the
        task's last run, which is what parked it, or the task's creation for
        work filed and never run.
        """

        sql = """
            SELECT t.*, COALESCE(
                (SELECT MAX(COALESCE(r.completed_at, r.created_at))
                   FROM runs r WHERE r.task_id = t.id),
                t.created_at
            ) AS waiting_since
            FROM tasks t
            WHERE t.status IN ('triage', 'blocked')
        """
        params: tuple[Any, ...] = ()
        if project_id is not None:
            sql += " AND t.project_id = ?"
            params = (project_id,)
        return [
            (_row_to_task(row), str(row["waiting_since"]))
            for row in self._connection.execute(sql, params).fetchall()
        ]

    # ── milestones ────────────────────────────────────────────────────────

    def page_milestones(
        self,
        *,
        project_id: str | None = None,
        kinds: Sequence[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MilestoneRow], int]:
        """Return one page of milestones, newest first, and how many match in all."""

        where, params = self._milestone_filter(project_id, kinds)
        total = int(
            self._connection.execute(
                f"WITH m AS ({_MILESTONES_SQL}) SELECT COUNT(*) AS n FROM m {where}",
                params,
            ).fetchone()["n"]
        )
        rows = self._connection.execute(
            self._milestone_select(where)
            + f" ORDER BY {_INSTANT.format(column='m.at')} DESC, m.ref DESC LIMIT ? OFFSET ?",
            (*params, max(0, int(limit)), max(0, int(offset))),
        ).fetchall()
        return [_row_to_milestone(row) for row in rows], total

    def latest_milestones(self) -> dict[str, MilestoneRow]:
        """Return each project's most recent milestone, keyed by project id."""

        rows = self._connection.execute(
            f"""
            WITH m AS ({_MILESTONES_SQL}),
            ranked AS (
              SELECT m.*, ROW_NUMBER() OVER (
                PARTITION BY m.project_id
                ORDER BY {_INSTANT.format(column='m.at')} DESC, m.ref DESC
              ) AS position
              FROM m
            )
            SELECT ranked.kind, ranked.at, ranked.project_id, ranked.actor,
                   p.name AS project_name,
                   s.id AS sprint_id, s.title AS sprint_title,
                   t.id AS task_id, t.task_key AS task_key, t.title AS task_title
            FROM ranked
            JOIN projects p ON p.id = ranked.project_id
            LEFT JOIN sprints s ON s.id = ranked.sprint_id
            LEFT JOIN tasks t ON t.id = ranked.task_id
            WHERE ranked.position = 1
            """
        ).fetchall()
        return {row["project_id"]: _row_to_milestone(row) for row in rows}

    @staticmethod
    def _milestone_filter(
        project_id: str | None, kinds: Sequence[str] | None
    ) -> tuple[str, tuple[Any, ...]]:
        filters: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            filters.append("m.project_id = ?")
            params.append(project_id)
        if kinds:
            filters.append(f"m.kind IN ({', '.join('?' for _ in kinds)})")
            params.extend(kinds)
        return (f"WHERE {' AND '.join(filters)}" if filters else ""), tuple(params)

    @staticmethod
    def _milestone_select(where: str) -> str:
        return f"""
            WITH m AS ({_MILESTONES_SQL})
            SELECT m.kind, m.at, m.project_id, m.actor, m.ref,
                   p.name AS project_name,
                   s.id AS sprint_id, s.title AS sprint_title,
                   t.id AS task_id, t.task_key AS task_key, t.title AS task_title
            FROM m
            JOIN projects p ON p.id = m.project_id
            LEFT JOIN sprints s ON s.id = m.sprint_id
            LEFT JOIN tasks t ON t.id = m.task_id
            {where}
        """


def _row_to_milestone(row: Any) -> MilestoneRow:
    return MilestoneRow(
        kind=row["kind"],
        at=row["at"],
        project_id=row["project_id"],
        project_name=row["project_name"],
        sprint_id=row["sprint_id"],
        sprint_title=row["sprint_title"],
        task_id=row["task_id"],
        task_key=row["task_key"],
        task_title=row["task_title"],
        actor=row["actor"],
    )
