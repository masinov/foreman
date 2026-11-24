"""The facts recorded about a task before it may merge (ADR-0018).

``EvidenceBuilder`` reads the store and git and returns a
``CompletionEvidence``: which commit is the branch head, whether the tests
passed and on which commit, what each reviewer decided and on which commit,
and whether an approving code review of the branch head covers the
acceptance criteria. It decides nothing about the workflow; the merge guard
in ``foreman.engine.builtins.completion`` does.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import subprocess

from ..repo.git import GitError, head_sha
from ..domain.models import CompletionEvidence, Event, Project, Run, Task
from ..definitions.roles import RoleDefinition
from ..store import ForemanStore


#: A criterion an approving code review of the branch head covers.
CRITERION_COVERED = "covered"
#: A criterion no approving review covers yet.
CRITERION_UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class _GitPosition:
    base: str = ""
    head: str = ""
    merge_base: str = ""
    commit_count: int = 0


@dataclass(frozen=True, slots=True)
class _TestFacts:
    command: str
    passed: bool
    detail: str
    exit_code: int | None
    tested_sha: str
    duration_seconds: float | None
    status: str


@dataclass(frozen=True, slots=True)
class _ReviewFacts:
    outcome: str
    sha: str
    security_outcome: str
    security_sha: str


def _git_position(project: Project, task: Task) -> _GitPosition:
    """The default branch's head, the task branch's head, their merge base and distance."""

    base = head = merge_base = ""
    commit_count = 0
    try:
        base = head_sha(project.repo_path, f"refs/heads/{project.default_branch}") or ""
        if task.branch_name:
            head = head_sha(project.repo_path, f"refs/heads/{task.branch_name}") or ""
            merge_base_result = subprocess.run(
                ["git", "merge-base", project.default_branch, task.branch_name],
                cwd=project.repo_path,
                capture_output=True,
                text=True,
            )
            merge_base = merge_base_result.stdout.strip()
            commit_count_result = subprocess.run(
                ["git", "rev-list", "--count", f"{project.default_branch}..{task.branch_name}"],
                cwd=project.repo_path,
                capture_output=True,
                text=True,
            )
            if commit_count_result.returncode == 0:
                commit_count = int(commit_count_result.stdout.strip())
    except (FileNotFoundError, GitError, OSError, ValueError):
        pass
    return _GitPosition(base, head, merge_base, commit_count)


def _branch_changes(project: Project, task: Task) -> tuple[tuple[str, ...], int, str]:
    """The files the branch changes, its context lines and its diff stat."""

    if task.branch_name:
        diff_text = branch_numstat(project.repo_path, project.default_branch, task.branch_name)
        if diff_text:
            return parse_numstat(diff_text)
    return (), 0, ""


def _test_facts(events: list[Event], head: str) -> _TestFacts:
    """What the test step ran, whether it passed, and whether that was of the head."""

    command = detail = tested_sha = ""
    passed = False
    exit_code: int | None = None
    duration_seconds: float | None = None
    test_events = [e for e in events if e.event_type in ("engine.test_run", "engine.test_output")]
    for event in sorted(test_events, key=lambda e: e.timestamp):
        payload = event.payload
        if event.event_type == "engine.test_run":
            command = payload.get("command", "")
            exit_code = payload.get("exit_code")
            passed = exit_code == 0
            tested_sha = str(payload.get("head_sha") or "")
            duration = payload.get("duration_seconds")
            duration_seconds = float(duration) if isinstance(duration, (int, float)) else None
        elif event.event_type == "engine.test_output":
            if payload.get("exit_code") == 0:
                passed = True
            detail = payload.get("output", "")

    # A test run on a commit that is no longer the branch head says nothing
    # about the head. Runs recorded before the commit was captured carry no
    # SHA and are taken at face value.
    if not command:
        status = "not_run"
    elif tested_sha and head and tested_sha != head:
        status = "stale"
    else:
        status = "passed" if passed else "failed"
    return _TestFacts(command, passed, detail, exit_code, tested_sha, duration_seconds, status)


def _criteria_checklist(criteria_text: str, *, covered: bool, reviewed_sha: str) -> list[dict[str, str]]:
    """One row per acceptance criterion: covered by the approving review, or not yet."""

    return [
        {
            "criterion": criterion,
            "status": CRITERION_COVERED if covered else CRITERION_UNVERIFIED,
            "evidence": f"Code review approved {reviewed_sha[:8]}." if covered and reviewed_sha else "",
        }
        for criterion in (c.strip() for c in criteria_text.split("\n"))
        if criterion
    ]


class EvidenceBuilder:
    """Builds completion evidence for the tasks of one store."""

    def __init__(self, store: ForemanStore, roles: Mapping[str, RoleDefinition]) -> None:
        self.store = store
        self.roles = roles

    def build(
        self,
        task: Task,
        project: Project,
    ) -> CompletionEvidence | None:
        """Build structured completion evidence for one task.

        Records facts and nothing derived from them by weighting: which
        commit is the branch head, whether the test step passed and on which
        commit, and what each reviewer decided and on which commit.
        ``proof_status`` is ``passed`` only when the tests passed on the head
        commit and an approving code review of the head commit covers the
        acceptance criteria (ADR-0018). Nothing else checks the criteria: the
        criteria judge was removed on 2026-11-19 (ADR-0010 amendment).
        """
        runs = self.store.list_runs(task_id=task.id)
        events = self.store.list_events(task_id=task.id)
        git = _git_position(project, task)
        changed_files, diff_context_lines, branch_diff_stat = _branch_changes(project, task)
        tests = _test_facts(events, git.head)
        review = self._review_facts(runs, events)

        failure_reasons: list[str] = []
        outstanding: list[str] = []
        if tests.status == "failed":
            failure_reasons.append(f"Tests failed (exit code {tests.exit_code}).")
        elif tests.status == "stale":
            failure_reasons.append(
                f"Tests ran on {tests.tested_sha[:8]}; the branch is now at {git.head[:8]}."
            )
        elif tests.status == "not_run":
            outstanding.append("Tests have not run.")

        review_approved = review.outcome == "approve"
        review_is_stale = bool(
            review_approved and review.sha and git.head and review.sha != git.head
        )
        if review_is_stale:
            failure_reasons.append(
                f"Code review approved {review.sha[:8]}; the branch is now at "
                f"{git.head[:8]}."
            )

        # An approving code review of the branch head covers the acceptance
        # criteria; until there is one they are not counted as met.
        criteria_text = task.acceptance_criteria or ""
        covered = review_approved and not review_is_stale
        criteria_checklist = _criteria_checklist(criteria_text, covered=covered, reviewed_sha=review.sha)
        if criteria_checklist and not review_approved:
            outstanding.append("Acceptance criteria are covered once code review approves.")
        # Implementation tasks require acceptance criteria
        if task.task_type in {"feature", "fix", "refactor"} and not criteria_checklist:
            failure_reasons.append("No acceptance criteria defined.")

        if failure_reasons:
            proof_status = "failed"
        elif outstanding:
            proof_status = "pending"
        else:
            proof_status = "passed"

        return CompletionEvidence(
            task_id=task.id,
            task_title=task.title,
            acceptance_criteria=criteria_text,
            criteria_count=len(criteria_checklist),
            criteria_addressed=len(criteria_checklist) if covered else 0,
            criteria_partially_addressed=0,
            changed_files=changed_files,
            diff_context_lines=diff_context_lines,
            branch_diff_stat=branch_diff_stat,
            agent_outputs=summarize_agent_outputs(runs),
            builtin_test_result=tests.command,
            builtin_test_passed=tests.passed,
            builtin_test_detail=tests.detail,
            base_sha=git.base,
            head_sha=git.head,
            merge_base_sha=git.merge_base,
            commit_count=git.commit_count,
            test_command=tests.command,
            test_exit_code=tests.exit_code,
            tests_status=tests.status,
            tested_sha=tests.tested_sha,
            test_duration_seconds=tests.duration_seconds,
            review_outcome=review.outcome,
            reviewed_sha=review.sha,
            security_review_outcome=review.security_outcome,
            security_reviewed_sha=review.security_sha,
            criteria_checklist=tuple(criteria_checklist),
            proof_status=proof_status,
            failure_reasons=tuple(failure_reasons),
            outstanding=tuple(outstanding),
        )

    def _review_facts(self, runs: list[Run], events: list[Event]) -> _ReviewFacts:
        """The latest code and security decisions, and the commits they were of.

        Roles declare whether their decision is a code review or a security
        review, so any reviewer (triage, frontier, a custom QA role) counts
        by contract.
        """

        reviewed_sha_by_run = {
            event.run_id: str(event.payload.get("head_sha") or "")
            for event in events
            if event.event_type == "engine.review_recorded"
        }
        review_kind_by_role = {
            role_id: role.completion.review_kind
            for role_id, role in self.roles.items()
            if role.completion.output.extract_decision
        }
        reviewer_runs = [
            r for r in runs
            if r.status == "completed" and r.role_id in review_kind_by_role
        ]
        outcome = sha = security_outcome = security_sha = ""
        for run in sorted(reviewer_runs, key=lambda r: r.completed_at or "", reverse=True):
            kind = review_kind_by_role[run.role_id]
            if kind == "code" and not outcome:
                outcome = run.outcome or ""
                sha = reviewed_sha_by_run.get(run.id, "")
            if kind == "security" and not security_outcome:
                security_outcome = run.outcome or ""
                security_sha = reviewed_sha_by_run.get(run.id, "")
        return _ReviewFacts(outcome, sha, security_outcome, security_sha)

    def branch_head(self, project: Project, task: Task) -> str:
        """Return the task branch's head commit, or "" when it cannot be read."""

        if not task.branch_name:
            return ""
        try:
            return head_sha(project.repo_path, f"refs/heads/{task.branch_name}") or ""
        except (GitError, OSError):
            return ""

def branch_numstat(repo_path: str, target_branch: str, branch_name: str) -> str:
    """Return ``git diff --numstat -z`` output for one branch, or an empty
    string on failure."""
    for rev_args in (
        [f"{target_branch}...{branch_name}"],
        [target_branch, branch_name],
    ):
        try:
            result = subprocess.run(
                ["git", "diff", "--numstat", "-z", *rev_args],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="surrogateescape",
                check=False,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:  # pragma: no cover
            pass
    return ""


def parse_numstat(diff_output: str) -> tuple[tuple[str, ...], int, str]:
    """Parse ``git diff --numstat -z`` output into structured fields.

    Returns ``(changed_files, changed_file_count, summary_line)``. The
    integer is the number of changed files. The summary has the form
    ``"N file(s), +A, -D"``. Binary files (``-`` counts) are listed with 0
    added and 0 deleted. A rename is listed under its new path. Paths are
    used exactly as git reports them.
    """
    tokens = diff_output.split("\0")
    changed_files: list[str] = []
    total_additions = 0
    total_deletions = 0
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if not token:
            continue
        parts = token.split("\t", 2)
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if path == "":
            # Rename/copy: the old and new paths follow as separate records.
            path = tokens[i + 1] if i + 1 < len(tokens) else ""
            i += 2
            if not path:
                continue
        changed_files.append(path)
        if added.isdigit():
            total_additions += int(added)
        if deleted.isdigit():
            total_deletions += int(deleted)

    summary = f"{len(changed_files)} file(s), +{total_additions}, -{total_deletions}"
    return (tuple(changed_files), len(changed_files), summary)


def summarize_agent_outputs(runs: list[Run]) -> tuple[str, ...]:
    """Extract meaningful output snippets from completed agent runs."""
    outputs: list[str] = []
    for run in runs:
        if run.status not in {"completed", "failed", "killed", "timeout"}:
            continue
        detail = run.outcome_detail or ""
        # Capture first meaningful chunk of output (up to 500 chars)
        snippet = detail[:500].strip() if detail.strip() else ""
        if snippet:
            role_and_step = f"[{run.role_id} / {run.workflow_step}]"
            outputs.append(f"{role_and_step}: {snippet}")
    return tuple(outputs)


def truncate_diff(diff_text: str, max_chars: int) -> str:
    """Head+tail truncate a diff, keeping the first 70% and last 30%."""

    if max_chars <= 0 or len(diff_text) <= max_chars:
        return diff_text
    head_len = int(max_chars * 0.7)
    tail_len = max_chars - head_len
    removed = len(diff_text) - max_chars
    return (
        diff_text[:head_len]
        + f"\n[...truncated {removed} chars...]\n"
        + diff_text[len(diff_text) - tail_len:]
    )


def branch_diff_content(
    repo_path: str,
    target_branch: str,
    branch_name: str,
    *,
    max_chars: int = 24000,
) -> str:
    """Return unified ``git diff`` content for one branch, head+tail capped
    to ``max_chars``, or empty string on failure."""
    for diff_args in (
        ["git", "diff", f"{target_branch}...{branch_name}"],
        ["git", "diff", target_branch, branch_name],
    ):
        try:
            result = subprocess.run(
                diff_args,
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:  # pragma: no cover - defensive
            continue
        if result.returncode == 0 and result.stdout:
            return truncate_diff(result.stdout, max_chars)
    return ""
