"""Reads that span a project's sprints, tasks, runs and engine for the dashboard.

The workspace page, the needs-you list and the milestone feed each answer one
question about every project at once. Asking it through the per-aggregate
reads (one ``task_counts`` per sprint, one ``run_totals`` per sprint) costs a
query per sprint or per task, so these reads group in SQL instead. Each method
here is one statement, however many projects, sprints or tasks there are.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Any, Sequence

from ..domain.models import DecisionGate, Sprint, Task, TASK_STATUSES
from .base import ENGINE_RESOURCE_TYPE, StoreBase
from .rows import _row_to_gate, _row_to_sprint, _row_to_task

#: Every kind of milestone, in the order the API documents them.
MILESTONE_KINDS: tuple[str, ...] = (
    "sprint_started",
    "sprint_finished",
    "plan_confirmed",
    "engine_started",
    "engine_stopped",
    "engine_lost",
    "engine_paused",
    "engine_resumed",
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

# One row per milestone: what happened to a project's sprints and to its
# engine, the project's own level of activity. What happened to a task is the
# sprint's activity (``RunStore.list_sprint_activity_page``), not a milestone.
# Every row comes from rows already written: sprint columns, proposals,
# completed engine commands and the engine lock's lease history. Nothing is
# stored for the feed itself.
#
# Columns: kind, at, project, sprint, actor (who, when it is recorded), ref
# (a stable id), merged_count (a finished sprint's) and detail (a confirmed
# plan's reason).
#
# - The backlog is not a sprint (ADR-0021), so it has no start or finish.
# - A plan confirmed is a manager proposal a person confirmed; its sprint is
#   the one its first operation names. One that names none says what it is
#   about in ``subject``: the backlog it files into, or the new sprint it
#   plans.
# - Every change of the engine's state is a milestone, and nothing else is
#   (owner, 2026-11-21): it starts when it acquires its lease
#   (``engine_started``), pauses and resumes by command, and stops when the
#   lease is released (``engine_stopped``; when a ``shutdown`` command
#   completed during the lease, the command names who asked) or runs out
#   with nobody releasing it, the engine having died or been killed
#   (``engine_lost``, at the expiry; a lease still active past its expiry is
#   lost too). Start on the dashboard sends a ``resume`` that the new engine
#   applies as it starts: requested before the lease and completed after,
#   it is the start's, naming who started the engine, not a resume.
_MILESTONES_SQL = f"""
    SELECT 'sprint_started' AS kind, s.started_at AS at, s.project_id AS project_id,
           s.id AS sprint_id, NULL AS actor, s.id AS ref, NULL AS merged_count,
           NULL AS detail, NULL AS subject
    FROM sprints s
    WHERE s.started_at IS NOT NULL AND s.kind = 'sprint'
    UNION ALL
    SELECT 'sprint_finished', s.completed_at, s.project_id, s.id, NULL, s.id,
           (SELECT COUNT(DISTINCT e.task_id) FROM events e JOIN tasks t ON t.id = e.task_id
             WHERE t.sprint_id = s.id AND e.event_type = 'engine.merge'),
           NULL, NULL
    FROM sprints s
    WHERE s.status = 'completed' AND s.completed_at IS NOT NULL
      AND s.kind = 'sprint'
    UNION ALL
    SELECT 'plan_confirmed', pr.decided_at, pr.project_id,
           json_extract(pr.operations_json, '$[0].sprint_id'), pr.decided_by, pr.id,
           NULL, pr.reason,
           CASE json_extract(pr.operations_json, '$[0].kind')
             WHEN 'file_task' THEN 'Backlog'
             WHEN 'plan_tasks' THEN json_extract(pr.operations_json, '$[0].new_sprint.title')
           END
    FROM proposals pr
    WHERE pr.state = 'confirmed' AND pr.decided_at IS NOT NULL
    UNION ALL
    SELECT CASE c.command WHEN 'pause' THEN 'engine_paused' ELSE 'engine_resumed' END,
           COALESCE(c.completed_at, c.requested_at), c.project_id, NULL,
           c.requested_by, c.id, NULL, NULL, NULL
    FROM engine_commands c
    WHERE c.status = 'completed' AND c.command IN ('pause', 'resume')
      AND NOT EXISTS (
        SELECT 1 FROM leases l
        WHERE l.project_id = c.project_id AND l.resource_type = '{ENGINE_RESOURCE_TYPE}'
          AND julianday(c.requested_at) <= julianday(l.acquired_at)
          AND julianday(c.completed_at) >= julianday(l.acquired_at))
    UNION ALL
    SELECT 'engine_started', l.acquired_at, l.project_id, NULL,
           (SELECT c.requested_by FROM engine_commands c
             WHERE c.project_id = l.project_id AND c.command = 'resume'
               AND c.status = 'completed'
               AND julianday(c.requested_at) <= julianday(l.acquired_at)
               AND julianday(c.completed_at) >= julianday(l.acquired_at)
             ORDER BY c.requested_at DESC LIMIT 1),
           l.id, NULL, NULL, NULL
    FROM leases l
    WHERE l.resource_type = '{ENGINE_RESOURCE_TYPE}'
    UNION ALL
    SELECT 'engine_stopped', COALESCE(l.released_at, l.expires_at), l.project_id, NULL,
           (SELECT c.requested_by FROM engine_commands c
             WHERE c.project_id = l.project_id AND c.command = 'shutdown'
               AND c.status = 'completed'
               AND c.completed_at BETWEEN l.acquired_at
                   AND COALESCE(l.released_at, l.expires_at)
             ORDER BY c.completed_at DESC LIMIT 1),
           l.id, NULL, NULL, NULL
    FROM leases l
    WHERE l.resource_type = '{ENGINE_RESOURCE_TYPE}' AND l.status = 'released'
    UNION ALL
    SELECT 'engine_lost', l.expires_at, l.project_id, NULL, NULL, l.id, NULL, NULL, NULL
    FROM leases l
    WHERE l.resource_type = '{ENGINE_RESOURCE_TYPE}'
      AND (l.status = 'expired'
           OR (l.status = 'active' AND julianday(l.expires_at) < julianday('now')))
"""


# A finished sprint's checkpoint (spec 6.4, ADR-0036): the sprint's own
# record of its last completion (ADR-0037), as {tag, sha, problem}; a
# sprint finished before tagging existed has none. Read over the milestone
# ``m`` joined to its sprint ``s``.
_CHECKPOINT_SQL = """
    CASE WHEN m.kind = 'sprint_finished' THEN (
      SELECT json_object(
               'tag', json_extract(e.payload_json, '$.tag'),
               'sha', json_extract(e.payload_json, '$.sha'),
               'problem', CASE WHEN e.event_type = 'engine.checkpoint_failed'
                               THEN json_extract(e.payload_json, '$.reason') END)
      FROM events e
      WHERE e.sprint_id = s.id
        AND e.event_type IN ('engine.checkpoint', 'engine.checkpoint_failed')
        AND json_extract(e.payload_json, '$.completed_at') = s.completed_at
      ORDER BY e.timestamp DESC, e.rowid DESC LIMIT 1)
    END
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
    actor: str | None
    #: How many tasks a finished sprint merged.
    merged_count: int | None = None
    #: A confirmed plan's reason.
    detail: str | None = None
    #: A finished sprint's tag: ``{tag, sha, problem}``, or None.
    checkpoint: dict[str, Any] | None = None


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

    def backlog_unplanned_origins(self, project_id: str) -> dict[str, dict[str, Any]]:
        """Return, by task id, the sprint each backlog task was last moved back from.

        One statement for the whole backlog, however many tasks it holds: the
        latest ``human.task_unplanned`` audit event of every task now in the
        project's backlog. A task that was never planned has no entry.
        """

        rows = self._connection.execute(
            """
            SELECT e.task_id AS task_id,
                   json_extract(e.payload_json, '$.from_sprint_id') AS sprint_id,
                   json_extract(e.payload_json, '$.from_sprint_title') AS sprint_title
            FROM events e
            JOIN tasks t ON t.id = e.task_id
            JOIN sprints b ON b.id = t.sprint_id
            WHERE b.project_id = ? AND b.kind = 'backlog'
              AND e.event_type = 'human.task_unplanned'
            ORDER BY e.timestamp ASC, e.rowid ASC
            """,
            (project_id,),
        ).fetchall()
        origins: dict[str, dict[str, Any]] = {}
        for row in rows:  # ascending, so the latest event for a task wins
            if row["sprint_id"]:
                origins[row["task_id"]] = {"id": row["sprint_id"], "title": row["sprint_title"]}
        return origins

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

    def list_pending_decision_gates(
        self, *, project_id: str | None = None
    ) -> list[DecisionGate]:
        """Return every decision gate (a proposed sprint order) nobody settled."""

        sql = "SELECT * FROM decision_gates WHERE status = 'pending'"
        params: tuple[Any, ...] = ()
        if project_id is not None:
            sql += " AND project_id = ?"
            params = (project_id,)
        return [_row_to_gate(row) for row in self._connection.execute(sql, params).fetchall()]

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
                   ranked.merged_count, ranked.detail,
                   p.name AS project_name,
                   s.id AS sprint_id, COALESCE(s.title, ranked.subject) AS sprint_title
            FROM ranked
            JOIN projects p ON p.id = ranked.project_id
            LEFT JOIN sprints s ON s.id = ranked.sprint_id
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
            SELECT m.kind, m.at, m.project_id, m.actor, m.ref, m.merged_count, m.detail,
                   p.name AS project_name,
                   s.id AS sprint_id, COALESCE(s.title, m.subject) AS sprint_title,
                   {_CHECKPOINT_SQL} AS checkpoint_json
            FROM m
            JOIN projects p ON p.id = m.project_id
            LEFT JOIN sprints s ON s.id = m.sprint_id
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
        actor=row["actor"],
        merged_count=row["merged_count"],
        detail=row["detail"],
        checkpoint=_checkpoint(row),
    )


def _checkpoint(row: Any) -> dict[str, Any] | None:
    """The finished sprint's ``{tag, sha, problem}``, where the row was read with it."""

    if "checkpoint_json" not in row.keys() or not row["checkpoint_json"]:
        return None
    value = _json.loads(row["checkpoint_json"])
    return value if isinstance(value, dict) else None
