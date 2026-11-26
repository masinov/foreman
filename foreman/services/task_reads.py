"""A task's changes, checks and runs, read for the task page (sprint 58).

Everything here is a read. Changes come from git (``foreman/git.py``) over the
task's branch; checks come from what the engine already recorded (events, runs,
completion evidence, ADR-0018) and nothing is re-run.
"""

from __future__ import annotations

import json
from typing import Any

from ..engine.verdict import REVIEW_VERDICT, command_was_run
from ..repo import git
from .task_models import (
    DIFF_CAP_CHARS,
    OUTPUT_CAP_CHARS,
    BranchFact,
    ChangeTotals,
    ChecksClaims,
    ChecksFacts,
    ChangedAgainst,
    CommitRef,
    CriterionClaim,
    FileChangeItem,
    FileDiff,
    TaskDocument,
    MergeFacts,
    ReviewClaim,
    RunItem,
    RunOutput,
    SessionFact,
    SizeFact,
    StepChanges,
    StepReads,
    SprintActivity,
    SprintActivityItem,
    TaskChanges,
    TaskChecks,
    TaskRuns,
    TestsFact,
    test_counts,
    TranscriptEntry,
)
from .errors import NotFoundError, InvalidRequestError
from ..domain.activity import (
    ENGINE_RECORD_ROLE,
    GATE_ROLE,
    HAND_EVENTS,
    NOT_STEP_ROLES,
    PROBLEM_OUTCOMES,
    PROBLEM_STATUSES,
    RECORD_OUTCOMES,
    RECORD_ROLES,
    STEP_COMMIT_EVENTS,
    STEP_REPORT_EVENT,
    WHO,
)
from ..domain.models import Event, Project, Run, Task
from ..domain.step_reads import STEP_READS_EVENT
from ..store import ForemanStore

_SUMMARY_CAP = 2000


class TaskReads:
    """Read-only views over one task, bound to a store."""

    def __init__(self, store: ForemanStore) -> None:
        self.store = store

    # ── lookups ──────────────────────────────────────────────────────────

    def _task_and_project(self, task_id: str) -> tuple[Task, Project]:
        task = self.store.get_task(task_id)
        if task is None:
            raise NotFoundError(f"Task not found: {task_id}")
        project = self.store.get_project(task.project_id)
        if project is None:
            raise NotFoundError(f"Project not found: {task.project_id}")
        return task, project

    @staticmethod
    def _head(task: Task, project: Project) -> tuple[str | None, str | None]:
        """The task's head commit, or why there is none: ``(sha, problem)``.

        The branch's head while the branch exists. A merged task's branch may
        be gone; the head its completion evidence recorded is used then.
        """

        if not task.branch_name:
            return None, "This task has no branch yet, so there are no changes to show."
        try:
            if not git.branch_exists(project.repo_path, project.default_branch):
                return None, f"The default branch {project.default_branch} does not exist."
            if git.branch_exists(project.repo_path, task.branch_name):
                return git.head_sha(project.repo_path, f"refs/heads/{task.branch_name}"), None
            recorded = task.completion_evidence.head_sha if task.completion_evidence else ""
            if recorded and git.head_sha(project.repo_path, f"{recorded}^{{commit}}"):
                return recorded, None
        except (OSError, git.GitError):
            return None, "The project repository could not be read."
        return None, f"Branch {task.branch_name} no longer exists in the repository."

    def _compared(self, task: Task, project: Project) -> tuple[str, str, str | None] | str:
        """What to compare for this task: ``(base, head, landed)``, or why not.

        Before the merge it is the branch against the default branch. After
        it, that comparison is empty, so it is the merge commit against the
        default branch as it was just before: what the task landed.
        """

        head, problem = self._head(task, project)
        if head is None:
            return str(problem)
        try:
            landed = git.landed_as(project.repo_path, head, project.default_branch)
        except (OSError, git.GitError):
            return "The project repository could not be read."
        if landed:
            return f"{landed}^1", landed, landed
        return project.default_branch, head, None

    def _changes(self, task: Task, project: Project) -> tuple[list[git.FileChange], str | None]:
        compared = self._compared(task, project)
        if isinstance(compared, str):
            return [], compared
        base, head, _ = compared
        try:
            return git.branch_changes(project.repo_path, base_branch=base, branch_name=head), None
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
        merged_as = None
        compared = self._compared(task, project)
        if reason is None and not isinstance(compared, str):
            base_ref, head_ref, merged_as = compared
            base = CommitRef(
                branch=project.default_branch,
                sha=(
                    git.head_sha(project.repo_path, base_ref)
                    if merged_as
                    else git.merge_base(project.repo_path, base_ref, head_ref)
                ),
            )
            head = CommitRef(branch=task.branch_name, sha=git.head_sha(project.repo_path, head_ref))
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
            merged_as=merged_as,
            empty_reason=reason if not items else None,
        )

    def get_file_diff(self, task_id: str, path: str) -> FileDiff:
        task, project = self._task_and_project(task_id)
        changes, reason = self._changes(task, project)
        # Only a path git itself listed as changed is ever handed back to git.
        match = next((c for c in changes if c.path == path), None)
        if match is None:
            raise InvalidRequestError(
                f"{path!r} is not one of the files this task changes."
            )
        base_ref, head_ref, _ = self._compared(task, project)  # a match means there is a comparison
        text = git.file_diff(project.repo_path, base_branch=base_ref, branch_name=head_ref, change=match)
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

    def get_document(self, task_id: str, path: str) -> TaskDocument:
        """A document the task names, read at the commit it was named at.

        Only a path the task names is handed to git.
        """

        task, project = self._task_and_project(task_id)
        ref = next((ref for ref in task.rests_on if ref.path == path), None)
        if ref is None:
            raise InvalidRequestError(f"{path!r} is not a document this task rests on.")
        text = git.read_file_at(project.repo_path, ref.commit, ref.path)
        if text is None:
            raise NotFoundError(f"{ref.path} is not in the repository at {ref.commit[:10]}.")
        return TaskDocument(
            task_id=task.id,
            path=ref.path,
            heading=ref.heading,
            commit=ref.commit,
            text=text[:DIFF_CAP_CHARS],
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

        ahead = behind = None
        merged_as = None
        state = "no_branch"
        live_head, _ = self._head(task, project)
        compared = self._compared(task, project)
        if live_head and not isinstance(compared, str):
            merged_as = compared[2]
            if merged_as:
                # Merged: how far the default branch has moved since says nothing about the task.
                state = "merged"
            else:
                ahead = git.commits_ahead(project.repo_path, live_head, project.default_branch)
                behind = git.commits_behind(project.repo_path, live_head, project.default_branch)
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
                merged_as=merged_as,
            ),
            size=SizeFact(
                files=len(changes),
                added=sum(c.added for c in changes),
                deleted=sum(c.deleted for c in changes),
            ),
        )
        checklist = (
            list(evidence.criteria())
            if evidence is not None and evidence.criteria_checklist
            else [
                {"criterion": line.strip(), "status": "unverified"}
                for line in (task.acceptance_criteria or "").splitlines()
                if line.strip()
            ]
        )
        claims = ChecksClaims(
            reviews=self._review_claims(events, runs, live_head),
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
            counts=test_counts(latest.get("report")),
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
            raise NotFoundError(f"Task not found: {task_id}")
        runs, total = self.store.list_task_runs_page(
            task_id,
            limit=limit,
            offset=offset,
            skip_roles=sorted(NOT_STEP_ROLES),
            engine_role=ENGINE_RECORD_ROLE,
            commit_events=STEP_COMMIT_EVENTS,
            report_event=STEP_REPORT_EVENT,
        )
        return TaskRuns(
            runs=[
                RunItem(
                    **_run_fields(run),
                    attempt=attempt,
                    step_commit=step_commit,
                    tests=test_counts(report),
                )
                for run, attempt, step_commit, report in runs
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    def list_sprint_activity(
        self,
        sprint_id: str,
        *,
        limit: int,
        offset: int,
        problems: bool = False,
        by: str | None = None,
    ) -> SprintActivity:
        """What happened to a sprint's tasks, newest first (``domain.activity``).

        With ``problems``, only what sent a task back or stopped it; with
        ``by``, only what was done by that role, ``user`` or ``foreman``.
        """

        if self.store.get_sprint(sprint_id) is None:
            raise NotFoundError(f"Sprint not found: {sprint_id}")
        rows, total, present = self.store.list_sprint_activity_page(
            sprint_id,
            limit=limit,
            offset=offset,
            skip_roles=sorted(RECORD_ROLES),
            skip_outcomes=sorted(RECORD_OUTCOMES),
            gate_role=GATE_ROLE,
            hand_events=HAND_EVENTS,
            problem_outcomes=sorted(PROBLEM_OUTCOMES) if problems else None,
            problem_statuses=sorted(PROBLEM_STATUSES),
            who=WHO,
            by=by or None,
        )
        tasks = {task.id: task for task in self.store.list_tasks(sprint_id=sprint_id)}
        items = []
        for row in rows:
            task = tasks.get(row["task_id"])
            items.append(
                SprintActivityItem(
                    **row,
                    task_key=task.task_key if task else None,
                    task_title=task.title if task else row["task_id"],
                )
            )
        return SprintActivity(items=items, total=total, limit=limit, offset=offset, who=present)

    def get_run_output(self, run_id: str, *, raw: bool = False) -> RunOutput:
        """What a run recorded, oldest first.

        Without ``raw`` the agent's raw stream is left out: every line of it
        that means something was also recorded as an event of its own, and
        those are what a person reads. ``raw`` returns only that stream.
        """

        run = self.store.get_run(run_id)
        if run is None:
            raise NotFoundError(f"Run not found: {run_id}")
        events = self.store.list_events(run_id=run.id)

        prompt = run.prompt_text
        entries: list[TranscriptEntry] = []
        raw_entries = 0
        for event in events:
            if event.event_type == "agent.prompt":
                prompt = prompt or str(event.payload.get("text", ""))
                continue
            is_raw = event.event_type == "agent.raw_output"
            raw_entries += is_raw
            if is_raw != raw:
                continue
            entry = _transcript_entry(event)
            if entry is not None:
                entries.append(entry)

        kept: list[TranscriptEntry] = []
        used = 0
        for entry in entries:
            size = len(entry.text) + (
                len(json.dumps(entry.data, default=str)) if entry.data else 0
            )
            if used + size > OUTPUT_CAP_CHARS:
                break
            kept.append(entry)
            used += size
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
            raw_entries=raw_entries,
            raw_included=raw,
            session=self._session_fact(run),
            changes=self._step_changes(run, events),
            reads=self._step_reads(events),
            merge=self._merge_facts(run, events),
            confirmed_commands=_confirmed_commands(run, events),
        )

    # ── what a step did to the repository (recorded when it ended, ADR-0038) ──

    def _attempts(self, run: Run) -> list[tuple[Run, int]]:
        """The task's runs before this one and this one, each with its attempt at its step."""

        counts: dict[tuple[str, bool], int] = {}
        numbered: list[tuple[Run, int]] = []
        for other in self.store.list_runs(task_id=run.task_id):
            key = (other.workflow_step or "", other.role_id == ENGINE_RECORD_ROLE)
            counts[key] = counts.get(key, 0) + 1
            numbered.append((other, counts[key]))
            if other.id == run.id:
                break
        return numbered

    def _session_fact(self, run: Run) -> SessionFact | None:
        if run.role_id.startswith("_builtin:") or not run.session_id:
            return None
        earlier = [
            (other, attempt)
            for other, attempt in self._attempts(run)
            if other.id != run.id
            and other.role_id == run.role_id
            and other.session_id == run.session_id
        ]
        if not earlier:
            return SessionFact()
        other, attempt = earlier[-1]
        return SessionFact(continued_from=other.id, continued_attempt=attempt)

    @staticmethod
    def _step_reads(events: list[Event]) -> StepReads | None:
        recorded = _last_payload(events, STEP_READS_EVENT)
        if recorded is None:
            return None
        try:
            return StepReads(reads=int(recorded["reads"]), edited=bool(recorded["edited"]))
        except (KeyError, TypeError, ValueError):
            return None

    def _step_changes(self, run: Run, events: list[Event]) -> StepChanges | None:
        recorded = _last_payload(events, "engine.step_changes")
        if recorded is None or not recorded.get("from_sha") or not recorded.get("to_sha"):
            return None
        from_sha = str(recorded["from_sha"])
        against = ChangedAgainst(kind="commit", sha=from_sha)
        left = [
            (other, attempt)
            for other, attempt in self._attempts(run)
            if other.id != run.id and other.commit_sha == from_sha
        ]
        if left:
            other, attempt = left[-1]
            against = ChangedAgainst(kind="attempt", sha=from_sha, run_id=other.id, attempt=attempt)
        elif recorded.get("from_default_branch"):
            task = self.store.get_task(run.task_id)
            project = self.store.get_project(task.project_id) if task else None
            against = ChangedAgainst(
                kind="default_branch",
                sha=from_sha,
                branch=project.default_branch if project else None,
            )
        try:
            return StepChanges(
                from_sha=from_sha,
                to_sha=str(recorded["to_sha"]),
                files=recorded.get("files") or [],
                files_total=int(recorded.get("files_total", len(recorded.get("files") or []))),
                added=int(recorded.get("added") or 0),
                removed=int(recorded.get("removed") or 0),
                against=against,
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _merge_facts(run: Run, events: list[Event]) -> MergeFacts | None:
        recorded = _last_payload(events, "engine.merge")
        if recorded is None:
            return None
        fields = {
            key: recorded[key]
            for key in ("target_before", "commits", "commits_total", "changes")
            if recorded.get(key) is not None
        }
        if not fields:
            return None
        try:
            return MergeFacts(**fields)
        except (TypeError, ValueError):
            return None


def _last_payload(events: list[Event], event_type: str) -> dict[str, Any] | None:
    """The facts of the last event of a kind, or None."""

    found = [event.payload for event in events if event.event_type == event_type and event.payload]
    return found[-1] if found else None


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
    else:
        # The page says these in words from the facts; nothing verbatim.
        return TranscriptEntry(
            at=event.timestamp, kind=event.event_type, text="", data=_clipped(payload)
        )
    return TranscriptEntry(at=event.timestamp, kind=event.event_type, stream=stream, text=text)


#: The longest string an event's facts carry to the page.
_FACT_STRING_CAP = 4000


def _clipped(value: Any) -> Any:
    """A JSON value with every long string cut, so one event cannot fill the page."""

    if isinstance(value, str):
        if len(value) <= _FACT_STRING_CAP:
            return value
        return value[:_FACT_STRING_CAP] + f"\n[... {len(value) - _FACT_STRING_CAP} more characters]"
    if isinstance(value, dict):
        return {str(key): _clipped(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clipped(item) for item in value]
    return value


def _confirmed_commands(run: Run, events: list[Event]) -> list[str]:
    """The commands a review's verdict cites that the run made, as the engine checked them."""

    record = run.record
    if not record or record.get("kind") != REVIEW_VERDICT or not isinstance(record.get("fields"), dict):
        return []
    made = [
        str(event.payload.get("command") or "")
        for event in events
        if event.event_type == "agent.command"
    ]
    cited = {
        command
        for entry in record["fields"].get("criteria") or []
        if isinstance(entry, dict)
        for command in (entry.get("ran") if isinstance(entry.get("ran"), list) else [])
        if isinstance(command, str)
    }
    return sorted(command for command in cited if command.strip() and command_was_run(command, made))


def _run_fields(run: Run) -> dict[str, Any]:
    """What a runs list says of one run."""

    return {
        "id": run.id,
        "step": run.workflow_step,
        "role_id": run.role_id,
        "model": run.model,
        "backend": run.agent_backend,
        "status": run.status,
        "outcome": run.outcome,
        "outcome_detail": run.outcome_detail,
        "commit_sha": run.commit_sha,
        "record": run.record,
        "started_at": run.started_at,
        "finished_at": run.completed_at,
        "duration_ms": run.duration_ms,
        "cost_usd": run.cost_usd,
        "tokens": run.token_count,
        "token_usage": run.token_usage.as_dict(),
    }
