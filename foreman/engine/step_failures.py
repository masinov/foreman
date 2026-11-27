"""Which ends of a step are a failure of its own work, and how they are worded.

A step moves up its role's models only after failures of its own work
(ADR-0041): its run ended without a result, the review sent the work back,
or the tests failed after it. What is not the step's fault never counts: an
engine restart, a Stop, a branch brought up to date after a conflict, a wait
for usage limits, an infrastructure error.
"""

from __future__ import annotations

from collections.abc import Iterable

NO_RESULT = "no_result"
REVIEW = "review"
TESTS = "tests"

#: How each kind of failure is said in a sentence, with a count after it.
_PHRASES = {
    NO_RESULT: "its run ended without a result",
    REVIEW: "the review sent it back",
    TESTS: "the tests failed",
}

#: ``Run.failure_type`` values that are not the step's own work: the account's
#: usage limit, the environment (preflight, the sandbox, git, the network),
#: a limit the project set.
_NOT_THE_STEPS = {"quota", "preflight", "sandbox", "infrastructure", "gate", "policy"}


def own_failure_type(failure_type: str | None) -> bool:
    """Whether a run that ended without a result failed in the step's own work."""

    return failure_type not in _NOT_THE_STEPS


def times(count: int) -> str:
    """A count as it is said: once, twice, 3 times."""

    return {1: "once", 2: "twice"}.get(count, f"{count} times")


def failure_sentence(kinds: Iterable[str]) -> str:
    """What the failures were, for a step that failed ``len(kinds)`` times on one model.

    "The review sent it back twice" when they were all the same kind;
    "its own work failed 3 times" when they were not.
    """

    kinds = list(kinds)
    if not kinds:
        return "its own work failed"
    if len(set(kinds)) == 1:
        return f"{_PHRASES[kinds[0]]} {times(len(kinds))}"
    return f"its own work failed {times(len(kinds))}"


def step_name(step: str) -> str:
    """A step id as it is said: "code_review" is "Code review"."""

    words = step.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def move_up_line(step: str, to_model: str, kinds: Iterable[str]) -> str:
    """The Activity line for a move up: "Develop moves up to claude-opus-5-5 · the review sent it back twice"."""

    return f"{step_name(step)} moves up to {to_model} · {failure_sentence(kinds)}"


def models_exhausted_reason(step: str, model: str, count: int) -> str:
    """Why a task blocks when its step has failed on the last of its models."""

    return f"{step_name(step)} failed {times(count)} on {model}, the last of its models."


def step_cap_reason(step: str, cap: int) -> str:
    """Why a task blocks when it is about to enter a capped step once more."""

    return f"{step_name(step)} ran {times(cap)}, its cap: a person decides."
