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
            listed = evidence.failure_reasons or evidence.outstanding
            reasons = "; ".join(listed) if listed else "proof_status is " + evidence.proof_status
            block_reason = (
                f"Completion proof not passed. Blocking merge until proof_status is 'passed'. "
                f"Current: {evidence.proof_status}. Reasons: {reasons}"
            )
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
