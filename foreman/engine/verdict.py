"""Whether a reviewer's verdict record agrees with its outcome (ADR-0041 section 2).

A reviewer returns a decision (approve, deny, steer, escalate) and, in a
record of kind ``review_verdict``, what it found: a status for each
acceptance criterion and findings with severities. Only a serious finding,
S1 (broken, unsafe or data-losing) or S2 (an acceptance criterion not met),
sends work back; S3 and S4 findings are kept with the review.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
import re
from typing import Any

from ..domain.step_reads import _segments, _strip_heredocs, _unwrap

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


def listed_count(fields: Mapping[str, Any]) -> int:
    """How many criteria entries a verdict record lists."""

    criteria = fields.get("criteria")
    return len(criteria) if isinstance(criteria, list) else 0


#: A line that starts a criterion of its own: a bullet or a number.
_ITEM_START = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def criteria_items(text: str | None) -> list[str]:
    """A task's acceptance criteria, one item each.

    A line that starts with a bullet or a number starts an item, and the lines
    under it continue it (a bullet that wraps is one criterion). Without
    bullets, each non-blank line is an item.
    """

    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not any(_ITEM_START.match(line) for line in lines):
        return [line.strip() for line in lines]
    items: list[str] = []
    for line in lines:
        if _ITEM_START.match(line) or not items:
            items.append(_ITEM_START.sub("", line).strip())
        else:
            items[-1] = f"{items[-1]} {line.strip()}"
    return items


def count_criteria(text: str | None) -> int:
    """How many acceptance criteria a task has."""

    return len(criteria_items(text))


def _normal_text(text: str) -> str:
    return " ".join(re.sub(r"[`*_\"'.,;:()\[\]]", " ", text.lower()).split())


def _same_criterion(listed: str, task: str) -> bool:
    a, b = _normal_text(listed), _normal_text(task)
    if not a or not b:
        return False
    return a == b or a in b or b in a or SequenceMatcher(None, a, b).ratio() >= 0.6


def missing_criteria(fields: Mapping[str, Any], task_items: Sequence[str]) -> list[str]:
    """The task's criteria no entry of the verdict stands for, each entry standing for one."""

    criteria = fields.get("criteria")
    listed = [
        str(entry.get("criterion") or "")
        for entry in (criteria if isinstance(criteria, list) else [])
        if isinstance(entry, Mapping)
    ]
    used: set[int] = set()
    missing: list[str] = []
    for item in task_items:
        match = next(
            (index for index, text in enumerate(listed) if index not in used and _same_criterion(text, item)),
            None,
        )
        if match is None:
            missing.append(item)
        else:
            used.add(match)
    return missing


def _texts(entry: Mapping[str, Any], key: str) -> list[str]:
    value = entry.get(key)
    return [item for item in (value if isinstance(value, list) else []) if isinstance(item, str) and item.strip()]


#: A redirection: ``2>&1``, ``> out.txt``, ``< /dev/null``. It changes where
#: output goes, not what ran.
_REDIRECTION = re.compile(r"(?<![\w-])\d*(?:>>?|<)\s*(?:&\d+|[^\s;&|]+)")


def command_parts(command: str) -> list[tuple[str, ...]]:
    """The simple commands of a command line, as words, the way a check compares them.

    A shell wrapper (``bash -lc '...'``, as Codex runs commands) is taken off,
    redirections are dropped, a line is split at ``&&``, ``||``, ``;`` and
    ``|``, and a ``cd`` is left out (it names where, not what). Quoting is
    undone, so ``"a b"`` and ``'a b'`` are the same word.
    """

    # A heredoc's body is text given to a command, not commands: a note that
    # names a command "(in parentheses)" does not run it (sprint 69 review).
    inner, _ = _strip_heredocs(_unwrap(command.strip()))
    inner = _REDIRECTION.sub(" ", inner)
    return [
        tuple(words)
        for words in _segments(inner)
        if words and words[0] != "cd"
    ]


def command_was_run(command: str, run: Sequence[str]) -> bool:
    """Whether a cited command is among the commands the review ran.

    Each simple command of the cited line must have run as a whole simple
    command, its program and arguments word for word (option flags such as
    ``-q`` may differ): running one test file is not running the suite, and
    ``echo pytest x`` is not ``pytest x``. Where it ran (a ``cd`` before it),
    what it was piped into and where its output went do not matter.
    """

    wanted = command_parts(command)
    if not wanted:
        return False
    done = {part for line in run for part in command_parts(line)}
    done_bare = {_without_flags(part) for part in done}
    return all(part in done or _without_flags(part) in done_bare for part in wanted)


def _without_flags(words: tuple[str, ...]) -> tuple[str, ...]:
    """A simple command without its option flags: ``pytest -q x`` is ``pytest x``.

    The program and its arguments still have to match word for word.
    """

    return tuple(word for word in words if not word.startswith("-"))


def session_commands(store: Any, task_id: str, step: str, session_id: str | None) -> list[str]:
    """The commands recorded by the earlier runs of one session of one step.

    Only the runs of this review: the same task, step and session, since the
    task's last run of another agent step (a review after the work changed is
    a new review, even in the same session).
    """

    if not session_id:
        return []
    runs = [run for run in store.list_runs(task_id=task_id) if not run.role_id.startswith("_builtin:")]
    since = 0
    for index, run in enumerate(runs):
        if run.workflow_step != step:
            since = index + 1
    commands: list[str] = []
    for run in runs[since:]:
        if run.workflow_step == step and run.session_id == session_id:
            commands.extend(
                str(event.payload.get("command") or "")
                for event in store.list_events(run_id=run.id)
                if event.event_type == "agent.command"
            )
    return commands


def unconfirmed_commands(
    fields: Mapping[str, Any], commands: Sequence[str]
) -> list[tuple[int, str]]:
    """The commands the criteria cite under ``ran`` that the review did not run."""

    criteria = fields.get("criteria")
    return [
        (number, command)
        for number, entry in enumerate(criteria if isinstance(criteria, list) else [], start=1)
        if isinstance(entry, Mapping)
        for command in _texts(entry, "ran")
        if not command_was_run(command, commands)
    ]


def _without_basis(entry: Mapping[str, Any], approve_needs: str) -> bool:
    """Whether a criterion lacks what ``approve_needs`` asks.

    Verified: a command it ran (``ran``), or one it ran or a file it read
    (``checked``). Judgement: its reason, in ``evidence``.
    """

    if approve_needs == "stated":
        return False
    if entry.get("status") == JUDGEMENT:
        return not str(entry.get("evidence") or "").strip()
    if entry.get("status") != VERIFIED:
        return False
    if _texts(entry, "ran"):
        return False
    return approve_needs == "ran" or not _texts(entry, "read")


def check_verdict(
    outcome: str,
    fields: Mapping[str, Any],
    *,
    task_criteria: int | Sequence[str] = 0,
    approve_needs: str = "checked",
    commands: Sequence[str] | None = None,
) -> str | None:
    """Why the verdict and the outcome disagree, or None when they agree.

    - deny or steer needs at least one S1 or S2 finding;
    - approve needs none, and every criterion verified or the reviewer's
      judgement; the verdict lists as many criteria as the task has, so
      none is skipped;
    - approve also needs, for each criterion marked verified, what the role's
      ``approve_needs`` asks: ``checked`` a command it ran or a file it read,
      ``ran`` a command it ran, ``stated`` nothing; a criterion resting only on
      the developer's report is not verified. A criterion marked judgement
      says why in its evidence;
    - every command a criterion cites under ``ran`` is among ``commands``, the
      commands the review ran (None when they are not known: not checked);
    - any other outcome (escalate) hands the decision on and is not checked.
    """

    blocking = blocking_findings(fields)
    if outcome in ("deny", "steer") and not blocking:
        return (
            f"{VERDICT_PROBLEM_PREFIX}: the reviewer returned {outcome.upper()} with no "
            "S1 or S2 finding. Only a broken, unsafe or data-losing change (S1) or an "
            "acceptance criterion not met (S2) sends work back."
        )
    items = list(task_criteria) if not isinstance(task_criteria, int) else []
    count = task_criteria if isinstance(task_criteria, int) else len(items)
    if outcome in ("approve", "deny", "steer") and 0 < listed_count(fields) < count:
        return (
            f"{VERDICT_PROBLEM_PREFIX}: the verdict lists {listed_count(fields)} of the "
            f"task's {count} acceptance criteria. List each one of them, in order, with its "
            "status and what you checked."
        )
    if outcome == "approve" and items and listed_count(fields):
        missing = missing_criteria(fields, items)
        if missing:
            return (
                f"{VERDICT_PROBLEM_PREFIX}: the verdict does not list these acceptance "
                f"criteria of the task: {'; '.join(missing)}. List each one of the task's "
                "criteria once, as the task states it, with its status and what you checked."
            )
    if outcome in ("approve", "deny", "steer") and commands is not None:
        missing = unconfirmed_commands(fields, commands)
        if missing:
            cited = "; ".join(
                f"criterion {number} cites `{command}`, which the review did not run"
                for number, command in missing
            )
            return (
                f"{VERDICT_PROBLEM_PREFIX}: {cited}. List under `ran` only the commands "
                "you ran, exactly as you ran them."
            )
    if outcome == "approve":
        if blocking:
            names = ", ".join(str(finding.get("severity")) for finding in blocking)
            return (
                f"{VERDICT_PROBLEM_PREFIX}: the reviewer returned APPROVE with "
                f"{len(blocking)} blocking finding(s) ({names})."
            )
        criteria = fields.get("criteria")
        listed = len(criteria) if isinstance(criteria, list) else 0
        if count and listed == 0:
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
        bare = [
            str(entry.get("criterion", "")).strip() or f"#{number}"
            for number, entry in enumerate(criteria if isinstance(criteria, list) else [], start=1)
            if isinstance(entry, Mapping) and _without_basis(entry, approve_needs)
        ]
        if bare:
            needs = (
                "a command it ran"
                if approve_needs == "ran"
                else "a command it ran or a file it read"
            )
            # What to do says only what this role accepts: offering "read the
            # code" to a role that needs a command it ran sent a reviewer
            # round again with the same refused verdict (FOR-108, 2026-11-28).
            if approve_needs == "ran":
                how = (
                    "Reading a file is not enough for this role: run a command that "
                    "shows it (a test, or a grep of the document for what the "
                    "criterion names) and list it under `ran`, or mark the criterion "
                    "judgement and say why in its evidence."
                )
            else:
                how = (
                    "The developer's report is not a check: run something, read the "
                    "code, or mark the criterion judgement and say why in its evidence."
                )
            return (
                f"{VERDICT_PROBLEM_PREFIX}: the reviewer returned APPROVE with criteria "
                f"without what this role's approvals need ({needs}, or judgement with "
                f"its reason): {'; '.join(bare)}. {how}"
            )
    return None


def findings_text(fields: Mapping[str, Any]) -> str:
    """The S1 and S2 findings as lines for the developer the review sends back."""

    lines = [
        f"- {finding.get('severity')}: {str(finding.get('finding') or '').strip()}"
        for finding in blocking_findings(fields)
    ]
    return "Findings that sent it back:\n" + "\n".join(lines) if lines else ""
