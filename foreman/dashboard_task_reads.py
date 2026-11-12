"""A task's changes, checks and runs, read for the task page (sprint 58).

Everything here is a read. Changes come from git (``foreman/git.py``) over the
task's branch; checks come from what the engine already recorded (events, runs,
completion evidence, ADR-0018) and nothing is re-run.
"""

from __future__ import annotations

import json
from typing import Any

from . import git
from .dashboard.task_models import (
    DIFF_CAP_CHARS,
    OUTPUT_CAP_CHARS,
    BranchFact,
    ChangeTotals,
    ChecksClaims,
    ChecksFacts,
    CommitRef,
    CriterionClaim,
    FileChangeItem,
    FileDiff,
    ReviewClaim,
    RunItem,
    RunOutput,
    SizeFact,
    TaskChanges,
    TaskChecks,
    TaskRuns,
    TestsFact,
    TranscriptEntry,
)
from .dashboard_service import DashboardNotFoundError, DashboardValidationError
from .models import Event, Project, Run, Task
from .store import ForemanStore

_SUMMARY_CAP = 2000


class TaskReads:
    """Read-only views over one task, bound to a store."""

    def __init__(self, store: ForemanStore) -> None:
        self.store = store

    # ── lookups ──────────────────────────────────────────────────────────

    def _task_and_project(self, task_id: str) -> tuple[Task, Project]:
        task = self.store.get_task(task_id)
        if task is None:
            raise DashboardNotFoundError(f"Task not found: {task_id}")
        project = self.store.get_project(task.project_id)
        if project is None:
            raise DashboardNotFoundError(f"Project not found: {task.project_id}")
        return task, project

    @staticmethod
    def _branch_problem(task: Task, project: Project) -> str | None:
        """Why this task has no branch to compare, or ``None`` when it has one."""

        if not task.branch_name:
            return "This task has no branch yet, so there are no changes to show."
        try:
            if not git.branch_exists(project.repo_path, task.branch_name):
                return f"Branch {task.branch_name} no longer exists in the repository."
            if not git.branch_exists(project.repo_path, project.default_branch):
                return f"The default branch {project.default_branch} does not exist."
        except (OSError, git.GitError):
            return "The project repository could not be read."
        return None

    def _changes(self, task: Task, project: Project) -> tuple[list[git.FileChange], str | None]:
        problem = self._branch_problem(task, project)
        if problem is not None:
            return [], problem
        try:
            return (
                git.branch_changes(
                    project.repo_path,
                    base_branch=project.default_branch,
                    branch_name=str(task.branch_name),
                ),
                None,
            )
        except (OSError, git.GitError):
            return [], "Git could not compare the task branch with the default branch."

    # ── changes ──────────────────────────────────────────────────────────

    def get_changes(self, task_id: str) -> TaskChanges:
        task, project = self._task_and_project(task_id)
        changes, reason = self._changes(task, project)
        items = [
            FileChangeItem(
                path=c.path,
                status=c.status,  # type: ignore[arg-type]
                added=c.added,
                deleted=c.deleted,
                binary=c.binary,
                old_path=c.old_path,
            )
            for c in changes
        ]
        base = head = None
        if reason is None and task.branch_name:
            base = CommitRef(
                branch=project.default_branch,
                sha=git.merge_base(project.repo_path, project.default_branch, task.branch_name),
            )
            head = CommitRef(
                branch=task.branch_name,
                sha=git.head_sha(project.repo_path, f"refs/heads/{task.branch_name}"),
            )
        return TaskChanges(
            task_id=task.id,
            files=items,
            totals=ChangeTotals(
                files=len(items),
                added=sum(i.added for i in items),
                deleted=sum(i.deleted for i in items),
            ),
            base=base,
            head=head,
            empty_reason=reason if not items else None,
        )

    def get_file_diff(self, task_id: str, path: str) -> FileDiff:
        task, project = self._task_and_project(task_id)
        changes, reason = self._changes(task, project)
        # Only a path git itself listed as changed is ever handed back to git.
        match = next((c for c in changes if c.path == path), None)
        if match is None:
            raise DashboardValidationError(
                f"{path!r} is not one of the files this task changes."
            )
        text = git.file_diff(
            project.repo_path,
            base_branch=project.default_branch,
            branch_name=str(task.branch_name),
            change=match,
        )
        return FileDiff(
            task_id=task.id,
            path=match.path,
            status=match.status,
            old_path=match.old_path,
            diff=text[:DIFF_CAP_CHARS],
            truncated=len(text) > DIFF_CAP_CHARS,
            cap_chars=DIFF_CAP_CHARS,
            total_chars=len(text),
        )

    # ── checks ───────────────────────────────────────────────────────────

    def get_checks(self, task_id: str) -> TaskChecks:
        task, project = self._task_and_project(task_id)
        evidence = task.completion_evidence
        events = self.store.list_events(task_id=task.id)
        runs = {run.id: run for run in self.store.list_runs(task_id=task.id)}

        live_head: str | None = None
        ahead = behind = None
        state = "no_branch"
        if self._branch_problem(task, project) is None and task.branch_name:
            live_head = git.head_sha(project.repo_path, f"refs/heads/{task.branch_name}")
            ahead = git.commits_ahead(project.repo_path, task.branch_name, project.default_branch)
            behind = git.commits_behind(project.repo_path, task.branch_name, project.default_branch)
            state = "behind" if behind else "current"
        changes, _ = self._changes(task, project)

        facts = ChecksFacts(
            tests=self._tests_fact(events, live_head),
            branch=BranchFact(
                name=task.branch_name,
                default_branch=project.default_branch,
                ahead=ahead,
                behind=behind,
                state=state,  # type: ignore[arg-type]
            ),
            size=SizeFact(
                files=len(changes),
                added=sum(c.added for c in changes),
                deleted=sum(c.deleted for c in changes),
            ),
        )
        checklist = (
            [dict(item) for item in evidence.criteria_checklist]
            if evidence is not None and evidence.criteria_checklist
            else [
                {"criterion": line.strip(), "status": "unverified"}
                for line in (task.acceptance_criteria or "").splitlines()
                if line.strip()
            ]
        )
        claims = ChecksClaims(
            reviews=self._review_claims(events, runs, live_head),
            judged_by=evidence.judged_by if evidence is not None else "none",
            criteria=[
                CriterionClaim(
                    criterion=str(item.get("criterion", "")),
                    status=str(item.get("status", "unverified")),
                    evidence=(str(item["evidence"]) if item.get("evidence") else None),
                )
                for item in checklist
            ],
        )
        return TaskChecks(
            task_id=task.id,
            proof_status=evidence.proof_status if evidence is not None else None,
            outstanding=list(evidence.outstanding) if evidence is not None else [],
            built_at=evidence.built_at if evidence is not None else None,
            facts=facts,
            claims=claims,
            evidence_files=[],
        )

    @staticmethod
    def _tests_fact(events: list[Event], live_head: str | None) -> TestsFact:
        test_events = [e for e in events if e.event_type == "engine.test_run"]
        if not test_events:
            return TestsFact(status="not_run", head_sha=live_head)
        latest = sorted(test_events, key=lambda e: e.timestamp)[-1].payload
        exit_code = latest.get("exit_code")
        tested = str(latest.get("head_sha") or "") or None
        if tested and live_head and tested != live_head:
            status = "stale"
        else:
            status = "passed" if exit_code == 0 else "failed"
        tail = str(latest.get("output_tail") or "")
        lines = [line.strip() for line in tail.splitlines() if line.strip()]
        duration = latest.get("duration_seconds")
        return TestsFact(
            status=status,  # type: ignore[arg-type]
            exit_code=exit_code if isinstance(exit_code, int) else None,
            duration_seconds=float(duration) if isinstance(duration, (int, float)) else None,
            command=str(latest.get("command") or "") or None,
            result_line=lines[-1] if lines else None,
            commit=tested,
            head_sha=live_head,
        )

    @staticmethod
    def _review_claims(
        events: list[Event], runs: dict[str, Run], live_head: str | None
    ) -> list[ReviewClaim]:
        """The latest recorded decision of each kind, newest kind first."""

        latest: dict[str, Event] = {}
        for event in sorted(events, key=lambda e: e.timestamp):
            if event.event_type == "engine.review_recorded":
                latest[str(event.payload.get("review_kind") or "code")] = event
        claims: list[ReviewClaim] = []
        for kind, event in latest.items():
            run = runs.get(event.run_id)
            sha = str(event.payload.get("head_sha") or "") or None
            summary = (run.outcome_detail or "").strip() if run is not None else ""
            claims.append(
                ReviewClaim(
                    kind=kind,
                    decision=str(event.payload.get("outcome") or "") or None,
                    model=run.model if run is not None else None,
                    role_id=str(event.payload.get("role") or "") or None,
                    duration_seconds=(
                        round(run.duration_ms / 1000, 1)
                        if run is not None and run.duration_ms is not None
                        else None
                    ),
                    commit=sha,
                    summary=summary[:_SUMMARY_CAP] or None,
                    run_id=event.run_id,
                    current=(sha == live_head) if sha and live_head else None,
                )
            )
        return claims

    # ── runs ─────────────────────────────────────────────────────────────

    def list_runs(self, task_id: str, *, limit: int, offset: int) -> TaskRuns:
        if self.store.get_task(task_id) is None:
            raise DashboardNotFoundError(f"Task not found: {task_id}")
        runs, total = self.store.list_task_runs_page(task_id, limit=limit, offset=offset)
        return TaskRuns(
            runs=[
                RunItem(
                    id=run.id,
                    step=run.workflow_step,
                    role_id=run.role_id,
                    model=run.model,
                    backend=run.agent_backend,
                    status=run.status,
                    outcome=run.outcome,
                    commit_sha=run.commit_sha,
                    started_at=run.started_at,
                    finished_at=run.completed_at,
                    duration_ms=run.duration_ms,
                    cost_usd=run.cost_usd,
                    tokens=run.token_count,
                    token_usage=run.token_usage.as_dict(),
                )
                for run in runs
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_run_output(self, run_id: str) -> RunOutput:
        run = self.store.get_run(run_id)
        if run is None:
            raise DashboardNotFoundError(f"Run not found: {run_id}")
        events = self.store.list_events(run_id=run.id)

        prompt = run.prompt_text
        entries: list[TranscriptEntry] = []
        for event in events:
            if event.event_type == "agent.prompt":
                prompt = prompt or str(event.payload.get("text", ""))
                continue
            entry = _transcript_entry(event)
            if entry is not None:
                entries.append(entry)

        kept: list[TranscriptEntry] = []
        used = 0
        for entry in entries:
            if used + len(entry.text) > OUTPUT_CAP_CHARS:
                break
            kept.append(entry)
            used += len(entry.text)
        prompt_truncated = prompt is not None and len(prompt) > OUTPUT_CAP_CHARS
        return RunOutput(
            run_id=run.id,
            task_id=run.task_id,
            prompt=prompt[:OUTPUT_CAP_CHARS] if prompt is not None else None,
            prompt_truncated=prompt_truncated,
            transcript=kept,
            transcript_truncated=len(kept) < len(entries),
            total_entries=len(entries),
            cap_chars=OUTPUT_CAP_CHARS,
        )


def _transcript_entry(event: Event) -> TranscriptEntry | None:
    payload: dict[str, Any] = event.payload or {}
    stream: str | None = None
    if event.event_type == "agent.raw_output":
        stream = str(payload.get("stream") or "") or None
        if "line" in payload:
            text = str(payload.get("line", ""))
        else:
            text = json.dumps(payload.get("message"), sort_keys=True)
    elif event.event_type == "engine.test_output":
        stream = str(payload.get("stream") or "") or None
        text = str(payload.get("text", ""))
    elif event.event_type == "engine.test_run":
        text = f"$ {payload.get('command', '')}\n{payload.get('output_tail', '')}".rstrip()
    else:
        text = json.dumps(payload, sort_keys=True) if payload else ""
    return TranscriptEntry(at=event.timestamp, kind=event.event_type, stream=stream, text=text)
