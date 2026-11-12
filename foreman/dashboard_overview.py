"""The workspace, needs-you and milestone reads of the dashboard.

These answer one question about every project at once, so they are built from
the grouped reads in :mod:`foreman.store.overview` rather than from the
per-sprint and per-task reads the project pages use. The query count depends
on the number of projects (the engine view costs a fixed few per project) and
never on the number of sprints or tasks.

:class:`~foreman.dashboard_service.DashboardService` exposes them; nothing
here writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .engine_control import (
    WorkflowGateSteps,
    blocked_kind,
    describe_engine,
    resolve_gate_steps,
)
from .models import DecisionGate, Project, Task
from .store import ForemanStore
from .store.overview import MILESTONE_KINDS, MilestoneRow

__all__ = [
    "NEEDS_YOU_KINDS",
    "MILESTONE_KINDS",
    "WorkspaceReader",
]

#: What a person can be asked for, in the order the API documents them. The
#: first four are the design's kinds, each about a task. ``settle_order`` is a
#: proposed sprint order (a decision gate): it is about a project's sprints, so
#: it has no task, and is settled by accepting or rejecting the proposal.
NEEDS_YOU_KINDS: tuple[str, ...] = (
    "accept_filed_work",
    "approve_plan",
    "approve_merge",
    "unblock",
    "settle_order",
)

#: The gate policy that asks for a plan to be approved. Every other human gate
#: is the merge gate: it is the one gate every shipped workflow has.
PLAN_APPROVAL_POLICY = "plan_approval"


@dataclass(frozen=True, slots=True)
class _Attention:
    kind: str
    project_id: str
    sprint_id: str
    since: str
    key: str
    task: Task | None = None
    gate: DecisionGate | None = None


class WorkspaceReader:
    """Read-side views across projects, over one store."""

    def __init__(self, store: ForemanStore, *, now: datetime) -> None:
        self.store = store
        self._now = now
        self._gates: dict[str, WorkflowGateSteps] = {}

    # ── needs you ─────────────────────────────────────────────────────────

    def needs_you(
        self, *, project_id: str | None, limit: int, offset: int
    ) -> dict[str, Any]:
        """Return one page of what is waiting for a person, newest first."""

        projects = {p.id: p for p in self.store.list_projects()}
        items = self._attention(projects, project_id)
        items.sort(key=lambda item: (item.since, item.key), reverse=True)
        page = items[offset : offset + limit]
        wanted: set[str] = set()
        for item in page:
            wanted.add(item.sprint_id)
            if item.gate is not None:
                wanted.update(item.gate.suggested_order)
        sprints = self._sprint_titles(wanted)
        return {
            "items": [
                self._serialize_attention(item, projects, sprints) for item in page
            ],
            "total": len(items),
            "limit": limit,
            "offset": offset,
        }

    def _attention(
        self, projects: dict[str, Project], project_id: str | None
    ) -> list[_Attention]:
        found: list[_Attention] = []
        for task, since in self.store.list_tasks_awaiting_person(project_id=project_id):
            project = projects.get(task.project_id)
            if project is None:
                continue
            if task.status == "triage":
                found.append(_attention("accept_filed_work", task, since))
                continue
            gates = self._gate_steps(project)
            if blocked_kind(task, gates) == "gate":
                policy = gates.gate_policies.get(task.workflow_current_step or "")
                kind = "approve_plan" if policy == PLAN_APPROVAL_POLICY else "approve_merge"
            else:
                kind = "unblock"
            found.append(_attention(kind, task, since))
        for gate in self.store.list_pending_decision_gates(project_id=project_id):
            if gate.project_id not in projects:
                continue
            found.append(
                _Attention(
                    "settle_order", gate.project_id, gate.sprint_id, gate.raised_at,
                    gate.id, gate=gate,
                )
            )
        return found

    def _serialize_attention(
        self,
        item: _Attention,
        projects: dict[str, Project],
        sprint_titles: dict[str, str],
    ) -> dict[str, Any]:
        task = item.task
        entry: dict[str, Any] = {
            "kind": item.kind,
            "project_id": item.project_id,
            "project_name": projects[item.project_id].name,
            "sprint_id": item.sprint_id,
            "sprint_title": sprint_titles.get(item.sprint_id),
            "task_id": task.id if task else None,
            "task_key": task.task_key if task else None,
            "task_title": task.title if task else None,
            "since": item.since,
        }
        gate = item.gate
        if gate is not None:
            entry["gate"] = {
                "id": gate.id,
                "conflict_description": gate.conflict_description,
                "suggested_reason": gate.suggested_reason,
                "suggested_order": [
                    {"sprint_id": sprint_id, "title": sprint_titles.get(sprint_id)}
                    for sprint_id in gate.suggested_order
                ],
            }
        if item.kind == "approve_merge" and task is not None:
            entry["evidence"] = _merge_facts(task)
        return entry

    # ── milestones ────────────────────────────────────────────────────────

    def milestones(
        self,
        *,
        project_id: str | None,
        kinds: list[str] | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        """Return one page of milestones, newest first."""

        rows, total = self.store.page_milestones(
            project_id=project_id, kinds=kinds, limit=limit, offset=offset
        )
        return {
            "milestones": [_serialize_milestone(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    # ── workspace ─────────────────────────────────────────────────────────

    def workspace(self) -> dict[str, Any]:
        """Return everything the workspace page shows, for every project."""

        projects = self.store.list_projects()
        by_id = {p.id: p for p in projects}
        active = self.store.list_active_sprints()
        sprint_ids = [sprint.id for sprint in active.values()]
        counts = self.store.task_counts_by_sprint(sprint_ids)
        spend = self.store.spend_by_sprint(sprint_ids)
        backlog = self.store.backlog_counts()
        latest = self.store.latest_milestones()

        needs_by_project: dict[str, int] = {}
        needs_by_sprint: dict[str, int] = {}
        for item in self._attention(by_id, None):
            needs_by_project[item.project_id] = needs_by_project.get(item.project_id, 0) + 1
            needs_by_sprint[item.sprint_id] = needs_by_sprint.get(item.sprint_id, 0) + 1

        entries = []
        for project in projects:
            engine = describe_engine(self.store, project.id, now=self._now)
            sprint = active.get(project.id)
            task = engine.current_task
            milestone = latest.get(project.id)
            entries.append(
                {
                    "id": project.id,
                    "name": project.name,
                    "repo_path": project.repo_path,
                    "default_branch": project.default_branch,
                    "workflow_id": project.workflow_id,
                    "engine": {
                        "state": (
                            "not_running"
                            if not engine.resident
                            else "paused" if engine.paused else "running"
                        ),
                        "task_id": task.id if task else None,
                        "task_key": task.task_key if task else None,
                        "task_title": task.title if task else None,
                        "step": task.workflow_current_step if task else None,
                    },
                    "active_sprint": (
                        {
                            "id": sprint.id,
                            "title": sprint.title,
                            "task_counts": counts[sprint.id],
                            "needs_you": needs_by_sprint.get(sprint.id, 0),
                            "spend_usd": spend[sprint.id],
                        }
                        if sprint is not None
                        else None
                    ),
                    "needs_you": needs_by_project.get(project.id, 0),
                    "backlog": backlog.get(project.id, 0),
                    "latest_milestone": (
                        _serialize_milestone(milestone) if milestone else None
                    ),
                }
            )
        return {"projects": entries}

    # ── helpers ───────────────────────────────────────────────────────────

    def _gate_steps(self, project: Project) -> WorkflowGateSteps:
        # Resolving a workflow reads every role and workflow TOML, so each
        # distinct workflow is resolved once per request.
        if project.workflow_id not in self._gates:
            self._gates[project.workflow_id] = resolve_gate_steps(project.workflow_id)
        return self._gates[project.workflow_id]

    def _sprint_titles(self, sprint_ids: set[str]) -> dict[str, str]:
        return self.store.sprint_titles(sorted(sprint_ids))


def _attention(kind: str, task: Task, since: str) -> _Attention:
    return _Attention(kind, task.project_id, task.sprint_id, since, task.id, task=task)


def _merge_facts(task: Task) -> dict[str, Any] | None:
    """The facts a person is asked to weigh at the merge gate (ADR-0018)."""

    evidence = task.completion_evidence
    if evidence is None:
        return None
    return {
        "tests_status": evidence.tests_status,
        "tested_sha": evidence.tested_sha,
        "review_outcome": evidence.review_outcome,
        "reviewed_sha": evidence.reviewed_sha,
        "head_sha": evidence.head_sha,
        "proof_status": evidence.proof_status,
    }


def _serialize_milestone(row: MilestoneRow) -> dict[str, Any]:
    return {
        "kind": row.kind,
        "at": row.at,
        "project_id": row.project_id,
        "project_name": row.project_name,
        "sprint_id": row.sprint_id,
        "sprint_title": row.sprint_title,
        "task_id": row.task_id,
        "task_key": row.task_key,
        "task_title": row.task_title,
        "actor": row.actor,
    }
