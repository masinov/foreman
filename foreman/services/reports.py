"""The terminal's reports: the workspace status, a board, a task's history, a run's transcript, cost.

The CLI prints these as text or, with ``--json``, as the dict itself, so the
two never disagree (ADR-0032). Reads the API already serves (a project, a
sprint and its tasks) are taken from those services rather than read again.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..definitions.gate_steps import blocked_kind, blocked_kind_counts, resolve_gate_steps
from ..domain.models import Event, Run
from ..engine.control import describe_engine
from .base import Service
from .errors import NotFoundError
from .sprints import SprintService
from .views import task_filed_from


def run_payload(run: Run) -> dict[str, Any]:
    """One run, every field, as plain values."""

    payload = asdict(run)
    payload["token_usage"] = run.token_usage.as_dict()
    return payload


def event_payload(event: Event) -> dict[str, Any]:
    """One event, every field, as plain values."""

    return {
        "id": event.id,
        "run_id": event.run_id,
        "task_id": event.task_id,
        "sprint_id": event.sprint_id,
        "project_id": event.project_id,
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "role_id": event.role_id,
        "payload": event.payload,
    }


def event_from_payload(payload: dict[str, Any]) -> Event:
    """The event a payload of ``event_payload`` describes."""

    return Event(**payload)


class ReportService(Service):
    """What `foreman status`, `board`, `history`, `transcript` and `cost` show."""

    def projects(self) -> dict[str, Any]:
        """Every project with its active sprint and where its tasks stand."""

        rows = []
        for project in self.store.list_projects():
            active = self.store.get_active_sprint(project.id)
            rows.append(
                {
                    "id": project.id,
                    "name": project.name,
                    "repo_path": project.repo_path,
                    "workflow_id": project.workflow_id,
                    "default_branch": project.default_branch,
                    "active_sprint_id": active.id if active else None,
                    "active_sprint_title": active.title if active else None,
                    "task_counts": self.store.task_counts(project.id),
                }
            )
        return {"database": str(self.store.db_path), "projects": rows}

    def project(self, project_id: str) -> dict[str, Any]:
        """One project: where it lives, its sprints, its tasks, its runs, its settings."""

        project = self._require_project(project_id)
        active = self.store.get_active_sprint(project.id)
        return {
            "database": str(self.store.db_path),
            "id": project.id,
            "name": project.name,
            "repo_path": project.repo_path,
            "spec_path": project.spec_path,
            "workflow_id": project.workflow_id,
            "methodology": project.methodology,
            "default_branch": project.default_branch,
            "active_sprint": {"id": active.id, "title": active.title} if active else None,
            "sprint_count": len(self.store.list_sprints(project.id)),
            "task_counts": self.store.task_counts(project_id=project.id),
            "totals": self.store.run_totals(project_id=project.id),
            "settings": dict(project.settings or {}),
        }

    def sprints(self, project_id: str) -> dict[str, Any]:
        """A project's sprints in order, each with its task counts and run totals."""

        project = self._require_project(project_id)
        return {
            "database": str(self.store.db_path),
            "project_id": project.id,
            "project_name": project.name,
            "sprints": [
                {
                    "id": sprint.id,
                    "title": sprint.title,
                    "goal": sprint.goal,
                    "status": sprint.status,
                    "order_index": sprint.order_index,
                    "started_at": sprint.started_at,
                    "completed_at": sprint.completed_at,
                    "task_counts": self.store.task_counts(sprint_id=sprint.id),
                    "run_totals": self.store.run_totals(project_id=project.id, sprint_id=sprint.id),
                }
                for sprint in self.store.list_sprints(project.id)
            ],
        }

    def tasks(self, project_id: str, *, sprint_id: str | None = None) -> dict[str, Any]:
        """A project's tasks, sprint by sprint, each with its run totals."""

        project = self._require_project(project_id)
        sprints = self.store.list_sprints(project.id)
        if sprint_id:
            sprints = [sprint for sprint in sprints if sprint.id == sprint_id]
        sprint_ids = {sprint.id for sprint in sprints}
        tasks = [
            task for task in self.store.list_tasks(project_id=project.id) if task.sprint_id in sprint_ids
        ]
        totals = {
            str(row["task_id"]): row for row in self.store.task_run_totals(project_id=project.id)
        }
        order = {sprint.id: index for index, sprint in enumerate(sprints)}
        tasks.sort(key=lambda task: order[task.sprint_id])
        return {
            "database": str(self.store.db_path),
            "project_id": project.id,
            "project_name": project.name,
            "sprints": [
                {"id": sprint.id, "title": sprint.title, "status": sprint.status} for sprint in sprints
            ],
            "tasks": [
                {
                    "id": task.id,
                    "key": task.task_key,
                    "sprint_id": task.sprint_id,
                    "title": task.title,
                    "task_type": task.task_type,
                    "status": task.status,
                    "blocked_reason": task.blocked_reason,
                    "branch_name": task.branch_name,
                    "workflow_current_step": task.workflow_current_step,
                    "runs": totals.get(task.id, {}).get("run_count", 0),
                    "tokens": totals.get(task.id, {}).get("total_token_count", 0),
                    "cost_usd": float(totals.get(task.id, {}).get("total_cost_usd", 0.0)),
                }
                for task in tasks
            ],
        }

    def engine(self, project_id: str, *, command_limit: int) -> dict[str, Any]:
        """The project's engine: who holds it, its heartbeat, its task in hand, recent orders."""

        project = self._require_project(project_id)
        # A `pause` that has been applied but not yet resumed is the engine's
        # current state, so the most recent applied pause/resume is what
        # makes "paused" visible to an operator who did not queue it.
        engine = describe_engine(self.store, project.id, command_limit=command_limit)
        lock = engine.lock
        now = self._now()
        running = self.store.list_tasks(project_id=project.id, statuses=("in_progress",))
        return {
            "database": str(self.store.db_path),
            "project_id": project.id,
            "project_name": project.name,
            "state": engine.state,
            "resident": lock is not None,
            "paused": engine.paused,
            "holder_id": lock.holder_id if lock is not None else None,
            "heartbeat_at": lock.heartbeat_at if lock is not None else None,
            "heartbeat_age_seconds": lock.heartbeat_age_seconds(now) if lock is not None else None,
            "acquired_at": lock.acquired_at if lock is not None else None,
            "lease_expires_at": lock.expires_at if lock is not None else None,
            "lease_expired": lock.is_expired(now) if lock is not None else False,
            "running_tasks": [{"id": task.id, "title": task.title} for task in running],
            "commands": [
                {
                    "id": command.id,
                    "command": command.command,
                    "task_id": command.task_id,
                    "status": command.status,
                    "requested_by": command.requested_by,
                    "requested_at": command.requested_at,
                    "result_detail": command.result_detail,
                }
                for command in engine.commands
            ],
        }

    def status(self) -> dict[str, Any]:
        """Every project at once: how many, how many sprints run, where tasks stand."""

        # Blocked splits by workflow, so the kinds are counted per project
        # and summed: "12 blocked" is not actionable, "10 waiting on me, 2
        # dead letters" is.
        blocked = {"gate": 0, "engine": 0}
        for project in self.store.list_projects():
            gates = resolve_gate_steps(self.store, project)
            counts = blocked_kind_counts(
                self.store.list_tasks(project_id=project.id, status="blocked"), gates
            )
            for kind, value in counts.items():
                blocked[kind] += value
        return {
            "database": self.store.db_path,
            "projects": self.store.count_projects(),
            "active_sprints": self.store.count_active_sprints(),
            "task_counts": self.store.task_counts(),
            "blocked": blocked,
        }

    def board(self, project_id: str) -> dict[str, Any]:
        """The project's active sprint and its tasks, or no sprint."""

        project = self._require_project(project_id)
        active = self.store.get_active_sprint(project.id)
        payload: dict[str, Any] = {
            "database": self.store.db_path,
            "project": {"id": project.id, "name": project.name},
            "sprint": None,
            "tasks": [],
        }
        if active is None:
            return payload
        sprints = SprintService(self.store, now_factory=self._now)
        payload["sprint"] = sprints.get_sprint(active.id)
        payload["tasks"] = sprints.list_sprint_tasks(active.id)["tasks"]
        return payload

    def history(self, task_id: str) -> dict[str, Any]:
        """One task with every run and event it has (`foreman history`, `task show`)."""

        task = self.store.get_task(task_id)
        if task is None:
            raise NotFoundError(f"Unknown task: {task_id}")
        project = self.store.get_project(task.project_id)
        sprint = self.store.get_sprint(task.sprint_id) if task.sprint_id else None
        kind = blocked_kind(task, resolve_gate_steps(self.store, project)) if project else None
        return {
            "database": self.store.db_path,
            "task": {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "task_type": task.task_type,
                "created_by": task.created_by,
                "branch_name": task.branch_name,
                "worktree_path": task.worktree_path,
                "assigned_role": task.assigned_role,
                "blocked_reason": task.blocked_reason,
                "blocked_kind": kind,
                "workflow_current_step": task.workflow_current_step,
                "complexity": task.complexity,
                "executor_overrides": task.executor_overrides,
                "step_visit_counts": dict(task.step_visit_counts),
            },
            "filed_from": task_filed_from(
                self.store, self.store.list_events(task_id=task.id)
            ),
            "project": {"id": task.project_id, "name": project.name if project else None},
            "sprint": {"id": task.sprint_id, "title": sprint.title if sprint else None},
            "totals": self.store.run_totals(task_id=task.id),
            # Prompts are long; `transcript` shows a run's.
            "runs": [
                {**run_payload(run), "prompt_text": None}
                for run in self.store.list_runs(task_id=task.id)
            ],
            "events": [event_payload(e) for e in self.store.list_events(task_id=task.id)],
        }

    def transcript(self, run_id: str) -> dict[str, Any]:
        """One run, its prompt, and every event it recorded."""

        run = self.store.get_run(run_id)
        if run is None:
            raise NotFoundError(f"Unknown run: {run_id}")
        task = self.store.get_task(run.task_id)
        project = self.store.get_project(run.project_id)
        return {
            "database": self.store.db_path,
            "run": run_payload(run),
            "task": {"id": run.task_id, "title": task.title if task else None},
            "project": {"id": run.project_id, "name": project.name if project else None},
            "events": [event_payload(e) for e in self.store.list_events(run_id=run.id)],
        }

    def cost(self, project_id: str, *, sprint_id: str | None = None) -> dict[str, Any]:
        """What the project's runs, or one sprint's, cost in total and per task."""

        project = self._require_project(project_id)
        sprint = None
        if sprint_id:
            sprint = self.store.get_sprint(sprint_id)
            if sprint is None:
                raise NotFoundError(f"Unknown sprint: {sprint_id}")
            if sprint.project_id != project.id:
                raise NotFoundError(f"Sprint {sprint.id} does not belong to project {project.id}.")
        return {
            "database": self.store.db_path,
            "project": {"id": project.id, "name": project.name},
            "sprint": {"id": sprint.id, "title": sprint.title} if sprint else None,
            "totals": self.store.run_totals(
                project_id=project.id, sprint_id=sprint.id if sprint else None
            ),
            "tasks": self.store.task_run_totals(
                sprint_id=sprint.id if sprint else None,
                project_id=None if sprint else project.id,
            ),
        }
