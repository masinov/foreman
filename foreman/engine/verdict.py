"""Whether a reviewer's verdict record agrees with its outcome (ADR-0041 section 2).

A reviewer returns a decision (approve, deny, steer, escalate) and, in a
record of kind ``review_verdict``, what it found: a status for each
acceptance criterion and findings with severities. Only a serious finding,
S1 (broken, unsafe or data-losing) or S2 (an acceptance criterion not met),
sends work back; S3 and S4 findings are kept with the review.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: The kind of record a reviewer role declares.
REVIEW_VERDICT = "review_verdict"
#: The severities that block an approval and justify a deny or a steer.
BLOCKING_SEVERITIES = ("S1", "S2")
#: A criterion's status: checked, or settled by the reviewer's own judgement.
VERIFIED = "verified"
JUDGEMENT = "judgement"
#: What a detail starts with when the verdict does not agree with its outcome.
VERDICT_PROBLEM_PREFIX = "The review's verdict does not agree with its outcome"


def blocking_findings(fields: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The S1 and S2 findings of a verdict record."""

    findings = fields.get("findings")
    return [
        finding
        for finding in (findings if isinstance(findings, list) else [])
        if isinstance(finding, Mapping) and finding.get("severity") in BLOCKING_SEVERITIES
    ]


def check_verdict(
    outcome: str, fields: Mapping[str, Any], *, task_has_criteria: bool = False
) -> str | None:
    """Why the verdict and the outcome disagree, or None when they agree.

    - deny or steer needs at least one S1 or S2 finding;
    - approve needs none, and every criterion verified or the reviewer's
      judgement; when the task has acceptance criteria, an approval that
      lists none has checked none;
    - any other outcome (escalate) hands the decision on and is not checked.
    """

    blocking = blocking_findings(fields)
    if outcome in ("deny", "steer") and not blocking:
        return (
            f"{VERDICT_PROBLEM_PREFIX}: the reviewer returned {outcome.upper()} with no "
            "S1 or S2 finding. Only a broken, unsafe or data-losing change (S1) or an "
            "acceptance criterion not met (S2) sends work back."
        )
    if outcome == "approve":
        if blocking:
            names = ", ".join(str(finding.get("severity")) for finding in blocking)
            return (
                f"{VERDICT_PROBLEM_PREFIX}: the reviewer returned APPROVE with "
                f"{len(blocking)} blocking finding(s) ({names})."
            )
        criteria = fields.get("criteria")
        if task_has_criteria and not (isinstance(criteria, list) and criteria):
            return (
                f"{VERDICT_PROBLEM_PREFIX}: the reviewer returned APPROVE without listing "
                "the task's acceptance criteria. List each one, in order, with its status "
                "and what you checked."
            )
        unchecked = [
            str(entry.get("criterion", "")).strip() or f"#{number}"
            for number, entry in enumerate(criteria if isinstance(criteria, list) else [], start=1)
            if isinstance(entry, Mapping) and entry.get("status") not in (VERIFIED, JUDGEMENT)
        ]
        if unchecked:
            return (
                f"{VERDICT_PROBLEM_PREFIX}: the reviewer returned APPROVE with "
                f"criteria not verified: {'; '.join(unchecked)}."
            )
    return None


def findings_text(fields: Mapping[str, Any]) -> str:
    """The S1 and S2 findings as lines for the developer the review sends back."""

    lines = [
        f"- {finding.get('severity')}: {str(finding.get('finding') or '').strip()}"
        for finding in blocking_findings(fields)
    ]
    return "Findings that sent it back:\n" + "\n".join(lines) if lines else ""
