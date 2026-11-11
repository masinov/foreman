"""The facts recorded about a task before it may merge (ADR-0018).

``EvidenceBuilder`` reads the store and git and returns a
``CompletionEvidence``: which commit is the branch head, whether the tests
passed and on which commit, what each reviewer decided and on which commit,
and what a judge model said about each acceptance criterion. It decides
nothing about the workflow; the merge guard in ``foreman.builtins`` does.
"""

from __future__ import annotations

from collections.abc import Mapping
import subprocess

from ..git import GitError, head_sha
from ..judge import NOT_JUDGED, judge_criteria, truncate_diff
from ..models import CompletionEvidence, Project, Run, Task
from ..roles import RoleDefinition
from ..store import ForemanStore


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
        commit, what each reviewer decided and on which commit, and what a
        judge model said about each acceptance criterion when one is
        configured. ``proof_status`` is ``passed`` only when the tests passed
        on the head commit and the criteria were either all passed by a judge
        or covered by an approving code review of the head commit (ADR-0018).
        """
        runs = self.store.list_runs(task_id=task.id)

        # Git positional reference
        base_sha = ""
        head_sha_val = ""
        merge_base_sha_val = ""
        commit_count = 0
        try:
            base_sha = head_sha(project.repo_path, f"refs/heads/{project.default_branch}") or ""
            if task.branch_name:
                head_sha_val = head_sha(project.repo_path, f"refs/heads/{task.branch_name}") or ""
                merge_base_result = subprocess.run(
                    ["git", "merge-base", project.default_branch, task.branch_name],
                    cwd=project.repo_path,
                    capture_output=True,
                    text=True,
                )
                merge_base_sha_val = merge_base_result.stdout.strip()
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

        # Changed files from git diff
        changed_files: tuple[str, ...] = ()
        diff_context_lines = 0
        branch_diff_stat = ""
        if task.branch_name:
            diff_text = branch_numstat(
                project.repo_path,
                project.default_branch,
                task.branch_name,
            )
            if diff_text:
                changed_files, diff_context_lines, branch_diff_stat = parse_numstat(
                    diff_text,
                )

        # Agent output summaries
        agent_outputs = summarize_agent_outputs(runs)

        # Built-in test results
        test_events = [
            event
            for event in self.store.list_events(task_id=task.id)
            if event.event_type in ("engine.test_run", "engine.test_output")
        ]
        builtin_test_passed = False
        builtin_test_result = ""
        builtin_test_detail = ""
        test_exit_code: int | None = None
        tested_sha = ""
        test_duration_seconds: float | None = None
        for event in sorted(test_events, key=lambda e: e.timestamp):
            payload = event.payload
            if event.event_type == "engine.test_run":
                builtin_test_result = payload.get("command", "")
                test_exit_code = payload.get("exit_code")
                builtin_test_passed = test_exit_code == 0
                tested_sha = str(payload.get("head_sha") or "")
                duration = payload.get("duration_seconds")
                test_duration_seconds = (
                    float(duration) if isinstance(duration, (int, float)) else None
                )
            elif event.event_type == "engine.test_output":
                if payload.get("exit_code") == 0:
                    builtin_test_passed = True
                builtin_test_detail = payload.get("output", "")

        # A test run on a commit that is no longer the branch head says
        # nothing about the head. Runs recorded before the commit was captured
        # carry no SHA and are taken at face value.
        if not builtin_test_result:
            tests_status = "not_run"
        elif tested_sha and head_sha_val and tested_sha != head_sha_val:
            tests_status = "stale"
        else:
            tests_status = "passed" if builtin_test_passed else "failed"

        # Reviewer outcomes from completed decision-role runs. Roles declare
        # whether their decision is a code review or a security review, so any
        # reviewer (triage, frontier, a custom QA role) counts by contract.
        review_outcome = ""
        reviewed_sha = ""
        security_review_outcome = ""
        security_reviewed_sha = ""
        reviewed_sha_by_run = {
            event.run_id: str(event.payload.get("head_sha") or "")
            for event in self.store.list_events(task_id=task.id)
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
        for run in sorted(reviewer_runs, key=lambda r: r.completed_at or "", reverse=True):
            kind = review_kind_by_role[run.role_id]
            if kind == "code" and not review_outcome:
                review_outcome = run.outcome or ""
                reviewed_sha = reviewed_sha_by_run.get(run.id, "")
            if kind == "security" and not security_review_outcome:
                security_review_outcome = run.outcome or ""
                security_reviewed_sha = reviewed_sha_by_run.get(run.id, "")

        # Criteria coverage
        criteria_count = 0
        criteria_addressed = 0
        criteria_partially_addressed = 0
        criteria_text = task.acceptance_criteria or ""
        criteria_list = [c.strip() for c in criteria_text.split("\n") if c.strip()]
        criteria_count = len(criteria_list)
        criteria_checklist: list[dict[str, str]] = []
        judged_by = NOT_JUDGED

        if criteria_list:
            all_output_text = "\n".join(agent_outputs).lower()
            judge_diff = branch_diff_content(
                project.repo_path,
                project.default_branch,
                task.branch_name,
            ) if task.branch_name else ""
            judgment = judge_criteria(
                criteria=criteria_list,
                diff_text=judge_diff,
                agent_summary=all_output_text,
                changed_files=changed_files,
                settings=project.settings,
            )
            judged_by = judgment.judged_by
            criteria_checklist = [dict(item) for item in judgment.checklist]
            criteria_addressed = sum(
                1 for item in criteria_checklist if item.get("status") == "passed"
            )
            criteria_partially_addressed = sum(
                1 for item in criteria_checklist if item.get("status") == "partial"
            )

        judged = judged_by != NOT_JUDGED
        review_approved = review_outcome == "approve"
        failure_reasons: list[str] = []
        outstanding: list[str] = []

        if tests_status == "failed":
            failure_reasons.append(f"Tests failed (exit code {test_exit_code}).")
        elif tests_status == "stale":
            failure_reasons.append(
                f"Tests ran on {tested_sha[:8]}; the branch is now at {head_sha_val[:8]}."
            )
        elif tests_status == "not_run":
            outstanding.append("Tests have not run.")

        review_is_stale = bool(
            review_approved and reviewed_sha and head_sha_val and reviewed_sha != head_sha_val
        )
        if review_is_stale:
            failure_reasons.append(
                f"Code review approved {reviewed_sha[:8]}; the branch is now at "
                f"{head_sha_val[:8]}."
            )

        # An approving code review covers the acceptance criteria. Without one,
        # only a judge model's "passed" on every criterion does; a criterion no
        # judge looked at is not counted as met.
        if criteria_checklist and not review_approved:
            if judged:
                for item in criteria_checklist:
                    if item.get("status") != "passed":
                        failure_reasons.append(
                            f"Criterion not fully addressed: {item.get('criterion', '')!r} "
                            f"({item.get('status')})."
                        )
            else:
                outstanding.append(
                    "Acceptance criteria were not checked by a judge model and code "
                    "review has not approved."
                )
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
            criteria_count=criteria_count,
            criteria_addressed=criteria_addressed,
            criteria_partially_addressed=criteria_partially_addressed,
            changed_files=changed_files,
            diff_context_lines=diff_context_lines,
            branch_diff_stat=branch_diff_stat,
            agent_outputs=agent_outputs,
            builtin_test_result=builtin_test_result,
            builtin_test_passed=builtin_test_passed,
            builtin_test_detail=builtin_test_detail,
            base_sha=base_sha,
            head_sha=head_sha_val,
            merge_base_sha=merge_base_sha_val,
            commit_count=commit_count,
            test_command=builtin_test_result,
            test_exit_code=test_exit_code,
            tests_status=tests_status,
            tested_sha=tested_sha,
            test_duration_seconds=test_duration_seconds,
            review_outcome=review_outcome,
            reviewed_sha=reviewed_sha,
            security_review_outcome=security_review_outcome,
            security_reviewed_sha=security_reviewed_sha,
            criteria_checklist=tuple(criteria_checklist),
            proof_status=proof_status,
            failure_reasons=tuple(failure_reasons),
            outstanding=tuple(outstanding),
            judged_by=judged_by,
        )

    def branch_head(self, project: Project, task: Task) -> str:
        """Return the task branch's head commit, or "" when it cannot be read."""

        if not task.branch_name:
            return ""
        try:
            return head_sha(project.repo_path, f"refs/heads/{task.branch_name}") or ""
        except (GitError, OSError):
            return ""

    def is_stale(
        self,
        evidence: CompletionEvidence,
        task: Task,
        project: Project,
    ) -> bool:
        if not task.branch_name:
            return False
        try:
            current_head = head_sha(project.repo_path, f"refs/heads/{task.branch_name}") or ""
        except Exception:
            return False
        return bool(evidence.head_sha and current_head and evidence.head_sha != current_head)


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
