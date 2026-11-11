"""Reading what an agent's final message says it did.

A role's completion contract is either a marker the agent must end with or a
decision (APPROVE, DENY, STEER, ESCALATE) it must return exactly once. These
functions find and validate that in text; they know nothing about runs.
"""

from __future__ import annotations

import re

from ..outcomes import DONE, ERROR
from ..roles import RoleDefinition
from .results import AgentExecutionResult


FINAL_MESSAGE_PHASES = frozenset({"result", "final_answer"})


_DECISION_PREFIX_RE = re.compile(
    r"^(?:(?:final\s+)?(?:decision|verdict|result)\s*[:\-\u2013\u2014]\s*)",
    re.IGNORECASE,
)


_DECISION_LINE_RE = re.compile(r"^(APPROVE|DENY|STEER|ESCALATE)(?![A-Z])\s*(.*)$")


_DECISION_OPTION_TEMPLATES = {
    "approve": "APPROVE",
    "deny": "DENY: <reason>",
    "steer": "STEER: <specific corrective action>",
    "escalate": "ESCALATE: <why the senior reviewer is needed>",
}


def decision_option_lines(outcomes: tuple[str, ...]) -> list[str]:
    lines = [_DECISION_OPTION_TEMPLATES[o] for o in outcomes if o in _DECISION_OPTION_TEMPLATES]
    return lines or list(_DECISION_OPTION_TEMPLATES.values())[:3]


def _parse_decision_line(raw_line: str) -> tuple[str, str] | None:
    """Return ``(verdict, reason)`` when a line carries a reviewer verdict.

    Accepts the bare word, ``VERDICT: reason``, markdown emphasis, list
    markers, and a ``Decision:`` / ``Verdict:`` prefix. Lines whose reason is
    a ``<placeholder>`` are option restatements, not verdicts, and are ignored.
    """

    line = _normalize_decision_line(raw_line)
    line = _DECISION_PREFIX_RE.sub("", line)
    line = line.strip("*_` ").strip()
    match = _DECISION_LINE_RE.match(line)
    if match is None:
        return None
    verdict = match.group(1).lower()
    reason = match.group(2).strip()
    reason = reason.lstrip(":-\u2013\u2014 ").strip().strip("*_`").strip()
    if reason.startswith("<") and reason.endswith(">"):
        return None
    return (verdict, reason)


def extract_decision_output(
    text: str,
    *,
    allowed: tuple[str, ...] | None = None,
) -> tuple[str, str]:
    """Extract exactly one reviewer verdict from the final message.

    More than one distinct verdict is an error rather than a guess, and a
    verdict the role does not declare is an error naming the allowed set;
    both trigger the one-shot output-contract retry.
    """

    if not text:
        return (ERROR, "Reviewer returned no decision.")

    found: list[tuple[str, str]] = []
    for raw_line in text.splitlines():
        parsed = _parse_decision_line(raw_line)
        if parsed is not None:
            found.append(parsed)
    if not found:
        return (ERROR, text)

    verdicts = {verdict for verdict, _ in found}
    if len(verdicts) > 1:
        return (
            ERROR,
            "Ambiguous decision: found "
            + ", ".join(sorted(v.upper() for v in verdicts))
            + ". Return exactly one verdict.",
        )
    verdict, reason = found[-1]
    if allowed and verdict not in allowed:
        return (
            ERROR,
            f"Decision {verdict.upper()} is not valid for this role; expected one of "
            + ", ".join(o.upper() for o in allowed)
            + ".",
        )
    return (verdict, reason or verdict.upper())


def _normalize_decision_line(line: str) -> str:
    normalized = line.strip()
    normalized = normalized.strip("`")
    normalized = normalized.strip()
    if normalized.startswith(("* ", "- ")):
        normalized = normalized[2:].strip()
    normalized = normalized.strip("*").strip()
    return normalized


def contains_completion_marker(text: str, marker: str) -> bool:
    return any(_normalize_decision_line(line) == marker for line in text.splitlines())


def strip_completion_marker(text: str, marker: str) -> str:
    lines = [line for line in text.splitlines() if _normalize_decision_line(line) != marker]
    return "\n".join(lines).strip()


def extract_json_block(text: str) -> str | None:
    match = re.search(r"```json\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match is None:
        return None
    return match.group(1).strip() or None


def extract_completion_output(
    role: RoleDefinition,
    text: str,
    *,
    transcript: str | None = None,
) -> tuple[str, str]:
    """Apply the role's completion contract to the agent's final message.

    ``text`` is the final assistant message: the marker or verdict must
    appear there, not anywhere in the transcript, so a plan that mentions
    the marker or a reviewer that restates the options never counts.
    ``transcript`` is only a fallback for the returned detail when the
    final message is empty once the marker is stripped.
    """

    cleaned_text = text.strip()
    output_config = role.completion.output
    marker = role.completion.marker.strip()

    if output_config.extract_decision:
        return extract_decision_output(cleaned_text, allowed=role.completion.outcomes)

    if marker:
        if not contains_completion_marker(cleaned_text, marker):
            return (ERROR, f"Missing completion marker `{marker}`.")
        cleaned_text = strip_completion_marker(cleaned_text, marker)
        if not cleaned_text and transcript:
            cleaned_text = strip_completion_marker(transcript.strip(), marker)

    if output_config.extract_json:
        json_block = extract_json_block(cleaned_text)
        return (DONE, json_block or cleaned_text or "Completed without JSON output.")

    if output_config.extract_summary or output_config.extract_branch:
        return (DONE, cleaned_text or "Completed.")

    return (DONE, cleaned_text or "Completed.")


def contract_retry_reason(
    role: RoleDefinition,
    result: AgentExecutionResult,
) -> str | None:
    """Return a retry reason when one malformed agent response merits one corrective retry."""

    if result.status != "completed" or result.outcome != "error":
        return None

    if role.completion.output.extract_decision:
        return "decision_format"

    marker = role.completion.marker.strip()
    if marker and result.detail == f"Missing completion marker `{marker}`.":
        return "missing_completion_marker"

    return None


def with_retry_instruction(
    prompt: str,
    role: RoleDefinition,
    reason: str,
) -> str:
    """Append a minimal corrective instruction for one malformed-output retry."""

    if reason == "decision_format":
        options = "\n".join(decision_option_lines(role.completion.outcomes))
        correction = (
            "Your previous response did not follow the required final output format.\n"
            "Do not do more review work.\n"
            "Return exactly one line and nothing else:\n"
            f"{options}"
        )
    elif reason == "missing_completion_marker":
        correction = (
            "Your previous response did not include the required completion marker.\n"
            "Do not do more work.\n"
            f"Return your completion summary again and end with `{role.completion.marker}` "
            "on its own line."
        )
    else:
        return prompt
    return f"{prompt}\n\n### Output Correction\n{correction}"
