"""Reading what an agent's final message says it did.

A role's completion contract is either a marker the agent must end with or a
decision (APPROVE, DENY, STEER, ESCALATE) it must return exactly once. These
functions find and validate that in text; they know nothing about runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..domain.outcomes import APPROVE, DONE, ERROR
from ..definitions.records import RECORD_PROBLEM_PREFIX, read_record, split_record_block
from ..definitions.roles import RoleDefinition
from .results import AgentExecutionResult
from .verdict import REVIEW_VERDICT, VERDICT_PROBLEM_PREFIX, check_verdict, findings_text


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


@dataclass(frozen=True, slots=True)
class CompletionReading:
    """What a role's final message says: the outcome, its detail and the record."""

    outcome: str
    detail: str
    #: ``{"kind": ..., "fields": {...}}`` when the role declares a record and
    #: the message held a well-formed one; None otherwise.
    record: dict[str, Any] | None = None


def read_completion(
    role: RoleDefinition,
    text: str,
    *,
    transcript: str | None = None,
    task_has_criteria: bool = False,
) -> CompletionReading:
    """Apply the role's completion contract to the agent's final message.

    ``text`` is the final assistant message: the marker or verdict must
    appear there, not anywhere in the transcript, so a plan that mentions
    the marker or a reviewer that restates the options never counts.
    ``transcript`` is only a fallback for the returned detail when the
    final message is empty once the marker is stripped.

    A role that declares a record (ADR-0042) must also return it, in the
    final message: a missing or malformed one is an error outcome whose
    detail says what is wrong, and the step has no record.
    """

    cleaned_text = text.strip()
    output_config = role.completion.output
    marker = role.completion.marker.strip()

    declaration = role.completion.record

    if output_config.extract_decision:
        # The decision is read outside the record block, so a line of JSON
        # can never count as a verdict.
        words = split_record_block(cleaned_text)[1] if declaration else cleaned_text
        outcome, detail = extract_decision_output(words, allowed=role.completion.outcomes)
        if declaration is None or outcome == ERROR:
            return CompletionReading(outcome, detail)
        fields, problem = read_record(declaration, text)
        if fields is None:
            return CompletionReading(ERROR, f"{RECORD_PROBLEM_PREFIX}: {problem}")
        record = {"kind": declaration.kind, "fields": fields}
        # A verdict that disagrees with its outcome is an error, with the reason;
        # the record stays, so the page shows what the reviewer returned.
        if declaration.kind != REVIEW_VERDICT:
            return CompletionReading(outcome, detail, record)
        disagreement = check_verdict(outcome, fields, task_has_criteria=task_has_criteria)
        if disagreement:
            return CompletionReading(ERROR, disagreement, record)
        # A review that sends work back carries its S1 and S2 findings in the
        # detail, which is what the developer is handed (carry_output).
        sent_back = findings_text(fields) if outcome in ("deny", "steer") else ""
        return CompletionReading(outcome, f"{detail}\n\n{sent_back}" if sent_back else detail, record)

    if marker:
        if not contains_completion_marker(cleaned_text, marker):
            return CompletionReading(ERROR, f"Missing completion marker `{marker}`.")
        cleaned_text = strip_completion_marker(cleaned_text, marker)
        if not cleaned_text and transcript:
            cleaned_text = strip_completion_marker(transcript.strip(), marker)

    if declaration is not None:
        fields, problem = read_record(declaration, text)
        if fields is None:
            return CompletionReading(ERROR, f"{RECORD_PROBLEM_PREFIX}: {problem}")
        # The words around the block stay the step's summary; the block is the record.
        summary = split_record_block(cleaned_text)[1] or str(fields.get("summary") or "").strip()
        return CompletionReading(
            DONE,
            summary or "Completed.",
            {"kind": declaration.kind, "fields": fields},
        )

    if output_config.extract_json:
        json_block = extract_json_block(cleaned_text)
        return CompletionReading(DONE, json_block or cleaned_text or "Completed without JSON output.")

    return CompletionReading(DONE, cleaned_text or "Completed.")


def extract_completion_output(
    role: RoleDefinition,
    text: str,
    *,
    transcript: str | None = None,
) -> tuple[str, str]:
    """The outcome and detail of :func:`read_completion`."""

    reading = read_completion(role, text, transcript=transcript)
    return (reading.outcome, reading.detail)


def contract_retry_reason(
    role: RoleDefinition,
    result: AgentExecutionResult,
) -> str | None:
    """Return a retry reason when one malformed agent response merits one corrective retry."""

    if result.status != "completed" or result.outcome != "error":
        return None

    if role.completion.record is not None:
        if result.detail.startswith(VERDICT_PROBLEM_PREFIX):
            return "verdict_agreement"
        if result.detail.startswith(RECORD_PROBLEM_PREFIX):
            return "record_format"

    if role.completion.output.extract_decision:
        return "decision_format"

    marker = role.completion.marker.strip()
    if marker and result.detail == f"Missing completion marker `{marker}`.":
        return "missing_completion_marker"

    return None


#: The line ``truncate_diff`` leaves where it cut a diff.
_CUT_DIFF = re.compile(r"\[\.\.\.truncated \d+ chars\.\.\.\]")
#: Tools whose use shows a file or the tree was looked at.
_READING_TOOLS = frozenset({"Read", "Grep", "Glob"})

#: What a task is stopped with when a reviewer approves unread twice.
UNREAD_APPROVAL_DETAIL = (
    "The reviewer approved a change it had not read: the diff it was given was "
    "cut, and it opened no file, also after being asked to. A user should "
    "review this change, or unblock the task to have it reviewed again."
)


def approved_without_reading(
    role: RoleDefinition,
    prompt: str,
    result: AgentExecutionResult,
) -> bool:
    """Whether a role that must read approved a cut diff without opening a file.

    Seen on 2026-11-12: a 1,310-line change approved in seven seconds. A
    diff that reached the role whole needs no file opened; one that was cut
    cannot be approved on what the prompt showed.
    """

    if not role.completion.output.approve_needs_reading:
        return False
    if result.status != "completed" or result.outcome != APPROVE:
        return False
    if not _CUT_DIFF.search(prompt):
        return False
    return not any(_shows_reading(event) for event in result.events)


def _shows_reading(event: object) -> bool:
    event_type = getattr(event, "event_type", "")
    if event_type == "agent.command":
        # A shell command may read; a role allowed a shell is taken at its word.
        return True
    if event_type in {"agent.file_change", "agent.tool_use"}:
        return getattr(event, "payload", {}).get("tool") in _READING_TOOLS
    return False


def with_retry_instruction(
    prompt: str,
    role: RoleDefinition,
    reason: str,
    *,
    resumes_session: bool = False,
) -> str:
    """The prompt of one corrective retry.

    A retry that resumes the agent's session sends the correction alone: the
    session already holds the first prompt and the work done on it, and
    sending that prompt again had the agent start the task over. A retry
    with no session to resume sends the first prompt with the correction
    after it.
    """

    options = "\n".join(decision_option_lines(role.completion.outcomes))
    declaration = role.completion.record
    marker = role.completion.marker.strip()
    if reason == "decision_format":
        if declaration is None:
            correction = (
                "Your previous response did not follow the required final output format.\n"
                "Do not do more review work.\n"
                "Return exactly one line and nothing else:\n"
                f"{options}"
            )
        else:
            correction = (
                "Your previous response did not follow the required final output format.\n"
                "Do not do more review work.\n"
                + declaration.instructions(marker)
                + "\nThen, as the last line of your message, exactly one of:\n"
                + options
            )
    elif reason == "approved_unread":
        correction = (
            "You approved, but the diff you were given was cut and you opened no file.\n"
            "Read the changed files listed above in full, then decide again.\n"
            "If you cannot open files, do not approve a change you have seen only part of.\n"
            + (
                "End with your verdict record and, as the last line, exactly one of:\n"
                if declaration
                else "End with exactly one line:\n"
            )
            + options
        )
    elif reason == "missing_completion_marker":
        correction = (
            "Your previous response did not include the required completion marker.\n"
            "Do not do more work.\n"
            + (
                f"If the work is finished, return your completion summary again and end with "
                f"`{role.completion.marker}` on its own line.\n"
                if declaration is None
                else "If the work is finished, return your summary and your record again:\n"
                + declaration.instructions(marker)
                + f"\nThen end with `{role.completion.marker}` on its own line.\n"
            )
            + "If it is not finished, do not write the marker: say what is unfinished or "
            "what blocks it."
        )
    elif reason == "record_format":
        correction = (
            "Your previous response did not return its record in the required form.\n"
            "Do not do more work.\n"
            + (declaration.instructions(marker) if declaration else "")
            + (
                "\nThen, as the last line of your message, exactly one of:\n" + options
                if role.completion.output.extract_decision
                else ""
            )
        )
    elif reason == "verdict_agreement":
        correction = (
            "Your verdict did not agree with your decision.\n"
            "Do not do more review work.\n"
            "- DENY or STEER needs at least one S1 or S2 finding.\n"
            "- APPROVE needs no S1 or S2 finding, and every acceptance criterion of the "
            "task listed, each verified or marked judgement.\n"
            "Return your verdict record and decision again so they agree: change the "
            "findings or the decision, whichever you got wrong.\n"
            + (declaration.instructions(marker) if declaration else "")
            + "\nThen, as the last line of your message, exactly one of:\n"
            + options
        )
    else:
        return prompt
    if resumes_session:
        return f"### Output Correction\n{correction}"
    return f"{prompt}\n\n### Output Correction\n{correction}"
