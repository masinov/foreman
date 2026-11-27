"""A question an agent asks a person, and the answer that goes back (ADR-0041 section 4).

An agent role that declares the ``ask`` outcome may end its step with a
question instead of a result. The question is a record in the step's final
message, in the same ``foreman-record`` block the other records use, marked by
``"outcome": "ask"``::

    {"outcome": "ask", "question": "...", "options": ["...", "..."],
     "recommendation": {"option": 1, "why": "..."}}

This module owns the record's shape (what the agent is told, and checking what
it returned) and the words an answer goes back in. It knows nothing about runs
or storage.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..definitions.records import RECORD_FENCE, record_blocks
from .outcomes import ASK

#: The kind a question's record carries in ``Run.record``.
QUESTION_KIND = "question"
#: The kind of the record a person's answer leaves on its run.
ANSWER_KIND = "answer"

#: The role and backend of the run that records a person's answer.
ANSWER_ROLE = "_builtin:answer"
ANSWER_BACKEND = "human"

#: What a task waiting for an answer is blocked with. The task's page and
#: ``blocked_kind`` read it; a person's answer clears it.
QUESTION_BLOCKED_REASON = "Waiting for an answer to a question"

#: Events: the question is on the run's record; these say who answered and
#: when, and that the step went on.
ANSWERED_EVENT = "human.question_answered"
ASKED_EVENT = "workflow.question_asked"

#: What an error detail starts with when a question broke the shape.
QUESTION_PROBLEM_PREFIX = "The step's question is not usable"

#: The fewest options a question has.
MIN_OPTIONS = 2


def question_instructions(marker: str = "") -> str:
    """What an agent whose role may ask is told about asking."""

    example = {
        "outcome": ASK,
        "question": "...",
        "options": ["...", "..."],
        "recommendation": {"option": 1, "why": "..."},
    }
    return "\n".join(
        [
            "### Asking a person",
            "If you cannot go on without a person's answer (the task cannot be done as",
            "specified, the specification contradicts itself or the code, a decision only",
            "the owner can take), ask instead of guessing or blocking. Asking is not",
            "failing: your step waits, and goes on with the answer. To ask, end your final",
            f"message with one block whose info string is `{RECORD_FENCE}`, holding only",
            "this JSON, and no" + (f" `{marker}` line and no" if marker else "") + " other record:",
            "- `outcome`: the word `ask`.",
            "- `question` (text, required): the question, so that it can be answered alone.",
            f"- `options` (list of text, at least {MIN_OPTIONS}, required): the answers you can go on with.",
            "- `recommendation` (required): `option`, the number (from 1) of the option you",
            "  recommend, and `why`, the reason.",
            "",
            f"```{RECORD_FENCE}",
            json.dumps(example, indent=2),
            "```",
        ]
    )


def read_question(text: str) -> tuple[dict[str, Any] | None, str | None] | None:
    """The question a final message asks: None when it asks none.

    ``(fields, None)`` is a well-formed question; ``(None, problem)`` one that
    broke the shape, in words. A message asks when its last record block that
    is a JSON object says ``"outcome": "ask"``.
    """

    value: Any = None
    for block in reversed(record_blocks(text)):
        try:
            candidate = json.loads(block)
        except ValueError:
            continue
        if isinstance(candidate, dict):
            value = candidate
            break
    if value is None or str(value.get("outcome", "")).strip().lower() != ASK:
        return None
    problems = check_question(value)
    if problems:
        return None, "; ".join(problems)
    options = [str(option).strip() for option in value["options"]]
    recommendation = value["recommendation"]
    return (
        {
            "question": value["question"].strip(),
            "options": options,
            "recommendation": {
                "option": recommendation["option"],
                "why": recommendation["why"].strip(),
            },
        },
        None,
    )


def check_question(value: Mapping[str, Any]) -> list[str]:
    """Every way a question record breaks the shape, in words; empty when it keeps it."""

    problems: list[str] = []
    question = value.get("question")
    if not isinstance(question, str) or not question.strip():
        problems.append("`question` is required text")
    options = value.get("options")
    option_count = 0
    if not isinstance(options, list) or any(
        not isinstance(option, str) or not option.strip() for option in options
    ):
        problems.append("`options` must be a list of text, none blank")
    else:
        option_count = len(options)
        if option_count < MIN_OPTIONS:
            problems.append(f"`options` needs at least {MIN_OPTIONS} options, got {option_count}")
        elif len({option.strip().lower() for option in options}) != option_count:
            problems.append("`options` lists an option twice")
    recommendation = value.get("recommendation")
    if not isinstance(recommendation, dict):
        problems.append("`recommendation` is required: an object with `option` and `why`")
    else:
        number = recommendation.get("option")
        if isinstance(number, bool) or not isinstance(number, int):
            problems.append("`recommendation.option` must be the number of one of the options")
        elif option_count and not 1 <= number <= option_count:
            problems.append(
                f"`recommendation.option` is {number}, and there are {option_count} options: "
                "it must be one of them"
            )
        why = recommendation.get("why")
        if not isinstance(why, str) or not why.strip():
            problems.append("`recommendation.why` is required text")
        unknown = sorted(set(recommendation) - {"option", "why"})
        if unknown:
            problems.append(f"`recommendation` has undeclared field(s) {', '.join(unknown)}")
    unknown = sorted(set(value) - {"outcome", "question", "options", "recommendation"})
    if unknown:
        problems.append(f"the record has undeclared field(s) {', '.join(unknown)}")
    return problems


def question_of(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The fields of a run's question record, or None when the run asked none."""

    if not isinstance(record, Mapping) or record.get("kind") != QUESTION_KIND:
        return None
    fields = record.get("fields")
    return dict(fields) if isinstance(fields, Mapping) else None


class AnswerError(ValueError):
    """An answer that names no option of the question, or says nothing."""


def resolve_answer(
    question: Mapping[str, Any], *, option: int | None, text: str | None
) -> dict[str, Any]:
    """The answer as recorded: the option chosen (its number and words) and a person's own words.

    A person answers with an option, with their own words, or both.
    """

    words = (text or "").strip()
    options = list(question.get("options") or [])
    if option is None and not words:
        raise AnswerError("Answer with an option or with your own words.")
    chosen: dict[str, Any] = {}
    if option is not None:
        if isinstance(option, bool) or not isinstance(option, int) or not 1 <= option <= len(options):
            raise AnswerError(
                f"The question has {len(options)} options: answer with a number from 1 to {len(options)}."
            )
        chosen = {"option": option, "option_text": options[option - 1]}
    return {**chosen, "text": words}


def answer_words(answer: Mapping[str, Any]) -> str:
    """An answer in a sentence: ``option 2 ("...")`` and/or the person's own words."""

    parts: list[str] = []
    if answer.get("option"):
        parts.append(f'option {answer["option"]} ("{answer.get("option_text", "")}")')
    if answer.get("text"):
        parts.append(f'in their words: {answer["text"]}' if parts else str(answer["text"]))
    return ", ".join(parts)


def answer_message(question: Mapping[str, Any], answer: Mapping[str, Any]) -> str:
    """What goes back to the agent: its question and the answer.

    A step that resumes its session receives it as the next message (the
    session holds the work); a step that does not receives it as a section of
    its prompt.
    """

    who = str(answer.get("answered_by") or "").strip()
    return "\n".join(
        [
            "### Your question, and the answer",
            f"You asked: {question.get('question', '')}",
            f"{who.capitalize() if who else 'A person'} answered: {answer_words(answer)}",
            "Go on with your step using this answer. Do not ask it again.",
        ]
    )
