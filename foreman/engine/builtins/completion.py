"""The completion guard: whether the evidence lets a task merge (ADR-0018).

A waiver a person gave for one check (``foreman waive-merge``) lets the
merge past it, at the commit it was given for.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ...definitions.layers import project_definitions
from ...domain.models import CompletionEvidence, Project, Task
from ...store import ForemanStore
from ..evidence import EvidenceBuilder
from .base import BuiltinExecutorBase


def _short(sha: str) -> str:
    """A commit id as every page shows it."""

    return sha[:7]


def only_stale(evidence: CompletionEvidence) -> bool:
    """Whether the evidence falls short only because the branch moved since it was checked.

    The tests passed and the review approved, on a commit the branch has
    since left: nothing failed, the new commits are just unchecked. Such a
    task is tested and reviewed again rather than blocked.
    """

    head = evidence.head_sha
    if not head or evidence.review_outcome != "approve":
        return False
    tests_stale = evidence.tests_status == "stale"
    review_stale = bool(evidence.reviewed_sha and evidence.reviewed_sha != head)
    if not (tests_stale or review_stale):
        return False
    if evidence.tests_status not in {"stale", "passed"}:
        return False
    return not any("no acceptance criteria" in r.lower() for r in evidence.failure_reasons)


def proof_refusal_text(evidence: CompletionEvidence) -> str:
    """Say in plain sentences why a merge is refused for lack of proof.

    The first sentence is the heading a person reads; then the facts, each
    said once; the last says what they can do. The structured evidence is
    unchanged for the API and the reviewer's prompt.
    """

    head = evidence.head_sha
    tests_stale = evidence.tests_status == "stale"
    review_stale = bool(
        evidence.review_outcome == "approve"
        and evidence.reviewed_sha
        and head
        and evidence.reviewed_sha != head
    )
    tests_failed = evidence.tests_status == "failed"
    tests_not_run = evidence.tests_status == "not_run"
    review_missing = evidence.review_outcome != "approve"
    no_criteria = any("no acceptance criteria" in r.lower() for r in evidence.failure_reasons)

    details: list[str] = []
    if tests_stale and review_stale and evidence.tested_sha == evidence.reviewed_sha:
        details.append(
            f"Tests and review ran on {_short(evidence.tested_sha)}; the branch is now at {_short(head)}."
        )
    else:
        if tests_stale:
            details.append(f"Tests ran on {_short(evidence.tested_sha)}; the branch is now at {_short(head)}.")
        if review_stale:
            details.append(
                f"Review approved {_short(evidence.reviewed_sha)}; the branch is now at {_short(head)}."
            )
    if tests_failed:
        code = evidence.test_exit_code
        details.append(
            f"The tests failed with exit code {code}." if code is not None else "The tests failed."
        )
    if review_missing and not review_stale:
        details.append("No code review has approved the latest change.")
    if tests_not_run:
        details.append("The tests have not run.")
    if no_criteria:
        details.append("The task has no acceptance criteria.")

    if tests_stale or review_stale:
        what = (
            "tested and reviewed" if tests_stale and review_stale else "tested" if tests_stale else "reviewed"
        )
        heading = f"Not merged: the branch changed after it was {what}."
        step = "Unblock it to test and review it again."
    elif tests_failed:
        heading = "Not merged: the tests failed."
        step = "Send it back to fix the tests."
    elif review_missing:
        heading = "Not merged: no code review approved the latest change."
        step = "Unblock it to have the change reviewed."
    elif tests_not_run:
        heading = "Not merged: the tests have not run."
        step = "Unblock it to run the tests."
    elif no_criteria:
        heading = "Not merged: the task has no acceptance criteria."
        step = "Add acceptance criteria to the task, then unblock it."
    else:
        heading = "Not merged: the checks have not all passed."
        step = "Unblock it to run the checks again."
        details = []
    return " ".join([heading, *details, step])


def _completion_guard_payload(evidence: CompletionEvidence) -> dict[str, Any]:
    """Return the facts a blocked merge is recorded with."""

    return {
        "proof_status": evidence.proof_status,
        "tests_status": evidence.tests_status,
        "review_outcome": evidence.review_outcome,
        "head_sha": evidence.head_sha,
        "changed_files": list(evidence.changed_files),
        "reasons": [*evidence.failure_reasons, *evidence.outstanding],
    }


class CompletionGuard(BuiltinExecutorBase):
    """Deciding from the evidence whether a task may merge."""

    def _build_completion_evidence(
        self,
        *,
        project: Project,
        task: Task,
        store: ForemanStore | None,
        evidence_builder: Callable[[Task, Project], CompletionEvidence | None] | None = None,
    ) -> CompletionEvidence | None:
        """Best-effort completion evidence build for pre-merge guard checks."""

        try:
            if evidence_builder is not None:
                return evidence_builder(task, project)
            if store is None:
                return None
            return EvidenceBuilder(store, project_definitions(store, project.id).roles).build(task, project)
        except Exception:  # pragma: no cover - guard logic must not crash execution
            return None

    def _completion_guard_block_reason(
        self,
        task: Task,
        evidence: CompletionEvidence,
        project: Project,
        store: ForemanStore | None = None,
    ) -> str | None:
        """Return a block reason when merge-time evidence is too weak.

        A MergeWaiver can override blocks due to missing/incomplete acceptance criteria
        or docs-only-on-impl-task, but not blocks due to test failures,
        reviewer denial, or security reviewer denial.
        """

        if task.task_type not in {"feature", "fix", "refactor"}:
            return None

        if not evidence.changed_files:
            block_reason = "Blocking merge because the task branch has no file changes."
            if not self._active_waiver_applies(store, task, evidence, "no_code_delta"):
                return block_reason
        if self._changes_are_docs_or_tests_only(evidence.changed_files):
            block_reason = (
                "Blocking merge because only docs or tests changed for an implementation task."
            )
            if not self._active_waiver_applies(store, task, evidence, "docs_only_impl_task"):
                return block_reason
        # Gate on proof status - require explicit "passed"
        if evidence.proof_status != "passed":
            block_reason = proof_refusal_text(evidence)
            # A waiver can cover missing or unmet criteria, never tests or review.
            waiver_type = self._waiver_type_for_proof_failure(evidence.failure_reasons)
            if waiver_type:
                if not self._active_waiver_applies(store, task, evidence, waiver_type):
                    return block_reason
            else:
                return block_reason
        # Gate on code review approval - require explicit approve
        if evidence.review_outcome != "approve":
            return (
                f"Code review not approved (outcome: {evidence.review_outcome!r}). "
                "Blocking merge until code review approves."
            )
        # Gate on security review for secure workflows - require explicit approve
        if project.workflow_id == "development_secure":
            if evidence.security_review_outcome != "approve":
                return (
                    f"Security review not approved (outcome: {evidence.security_review_outcome!r}). "
                    "Blocking merge until security review approves."
                )
        return None

    def _waiver_type_for_proof_failure(self, failure_reasons: tuple[str, ...]) -> str | None:
        """Determine the waiver type that could apply given failure reasons.

        Returns a waiver type only if ALL failures are waiveable proof deficiencies
        (missing criteria). Never returns a waiver type if any failure
        involves tests, reviewer, or security.
        """
        non_waivable_markers = (
            "tests failed",
            "tests ran on",
            "exit code",
            "review",
            "security",
        )
        reasons_lower = [r.lower() for r in failure_reasons]

        # If there are any non-waivable failures, no waiver can apply
        for reason in reasons_lower:
            if any(marker in reason for marker in non_waivable_markers):
                return None

        # All failures are proof-related — determine waiver type
        if not reasons_lower:
            return None

        if all("no acceptance criteria" in r for r in reasons_lower):
            return "missing_acceptance_criteria"

        return None

    def _active_waiver_applies(
        self,
        store: ForemanStore | None,
        task: Task,
        evidence: CompletionEvidence,
        waiver_type: str,
    ) -> bool:
        """Return True if an active waiver of the given type exists for the task/branch."""
        if not store or not task.branch_name or not evidence.head_sha:
            return False
        waiver = store.get_active_merge_waiver(task.id, task.branch_name, evidence.head_sha)
        return waiver is not None and waiver.waiver_type == waiver_type

    def _changes_are_docs_or_tests_only(self, changed_files: tuple[str, ...]) -> bool:
        """Return True when every changed path is documentation or test-only."""

        normalized = [path.strip().lower() for path in changed_files if path.strip()]
        if not normalized:
            return False
        return all(self._is_docs_or_tests_path(path) for path in normalized)

    def _is_docs_or_tests_path(self, path: str) -> bool:
        """Classify one path as documentation or test-only."""

        candidate = Path(path)
        name = candidate.name.lower()
        parts = [part.lower() for part in candidate.parts]
        if name.endswith(".md") or name in {"readme", "readme.txt"}:
            return True
        if parts and parts[0] == "docs":
            return True
        if "tests" in parts:
            return True
        if name.startswith("test_") or name.endswith("_test.py"):
            return True
        return False
