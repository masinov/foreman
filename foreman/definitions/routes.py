"""The facts a route may name (ADR-0041 section 1, and its amendment).

A transition may carry ``when``: a list of facts that must all hold for the
route to be taken. The facts are fixed by Foreman and matched simply, there
are no expressions:

- ``label:<name>``: the task carries the label,
- ``no_criteria``: the task has no acceptance criteria,
- ``changed:<group>``: a changed path is in the path group,
- ``changed_only:<group>[,<group>]``: every changed path is in one of the groups,
- ``visits:<step>>=<n>``: the step has been visited ``n`` times or more,
- ``frozen_touched``: not yet (write scope and frozen checks, ADR-0040 item 8).

A fact prefixed ``not:`` holds when the fact does not. This module parses a
fact, says it in words, and checks a workflow's routes against what a project
names; deciding whether a fact holds on a task is the engine's
(``foreman.engine.route_facts``).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

from ..domain.labels import LabelError, check_name

LABEL = "label"
NO_CRITERIA = "no_criteria"
CHANGED = "changed"
CHANGED_ONLY = "changed_only"
VISITS = "visits"
FROZEN_TOUCHED = "frozen_touched"

#: Facts that read what a branch changed.
CHANGE_FACTS: frozenset[str] = frozenset({CHANGED, CHANGED_ONLY})

FACT_FORMS = (
    "label:<name>, no_criteria, changed:<group>, changed_only:<group>[,<group>], "
    "visits:<step>>=<n>"
)

_VISITS = re.compile(r"(?P<step>[^\s>]+)>=(?P<count>\d+)")


class FactError(ValueError):
    """Raised when a fact is not one of the list."""


@dataclass(frozen=True, slots=True)
class Fact:
    """One fact of a route, parsed."""

    text: str
    kind: str
    negated: bool = False
    names: tuple[str, ...] = ()
    count: int = 0


def parse_fact(text: object) -> Fact:
    """Parse one fact, or raise ``FactError`` saying what is wrong with it."""

    if not isinstance(text, str) or not text.strip():
        raise FactError(f"A fact is text, got {text!r}.")
    original = text.strip()
    body, negated = original, False
    if body.startswith("not:"):
        body, negated = body[len("not:"):], True
        if body.startswith("not:"):
            raise FactError(f"Fact {original!r}: 'not:' is used once.")
    kind, _, argument = body.partition(":")
    if kind == FROZEN_TOUCHED and not argument:
        raise FactError(
            f"Fact {original!r} is not available yet: it needs write scope and frozen "
            "checks (ADR-0040 build item 8), which Foreman does not have."
        )
    if kind == NO_CRITERIA and not argument:
        return Fact(original, NO_CRITERIA, negated)
    try:
        if kind == LABEL and argument:
            return Fact(original, LABEL, negated, (check_name(argument, what="Label"),))
        if kind == CHANGED and argument:
            return Fact(original, CHANGED, negated, (check_name(argument, what="Path group"),))
        if kind == CHANGED_ONLY and argument:
            groups = tuple(check_name(part.strip(), what="Path group") for part in argument.split(","))
            return Fact(original, CHANGED_ONLY, negated, groups)
    except LabelError as exc:
        raise FactError(f"Fact {original!r}: {exc}") from exc
    if kind == VISITS and argument:
        match = _VISITS.fullmatch(argument)
        if match:
            return Fact(original, VISITS, negated, (match["step"],), int(match["count"]))
        raise FactError(f"Fact {original!r}: write it as visits:<step>>=<n>, such as visits:develop>=3.")
    raise FactError(f"{original!r} is not a fact Foreman knows. The facts are: {FACT_FORMS}.")


def parse_facts(texts: Iterable[object]) -> tuple[Fact, ...]:
    """Parse a route's facts."""

    return tuple(parse_fact(text) for text in texts)


def fact_words(fact: Fact) -> str:
    """A fact as the Activity says it: "no criteria", "docs changed", "not labelled ui"."""

    names = ", ".join(fact.names)
    no = fact.negated
    if fact.kind == NO_CRITERIA:
        return "criteria given" if no else "no criteria"
    if fact.kind == LABEL:
        return f"not labelled {names}" if no else f"labelled {names}"
    if fact.kind == CHANGED:
        return f"{names} not changed" if no else f"{names} changed"
    if fact.kind == CHANGED_ONLY:
        return f"not only {names} changed" if no else f"only {names} changed"
    if fact.kind == VISITS:
        return (
            f"{names} visited fewer than {fact.count} times"
            if no
            else f"{names} visited {fact.count} or more times"
        )
    return fact.text


def words_of(facts: Iterable[str]) -> str:
    """Several facts, said together; ``facts`` are the texts as written."""

    return ", ".join(fact_words(parse_fact(text)) for text in facts)


def route_line(
    *, to_step: str, default: bool, held: Collection[str]
) -> str:
    """The line the Activity shows for a route taken where there were others."""

    if default:
        return f"No route's facts held: the default, to {to_step}"
    return f"Took the route to {to_step}: {words_of(held)}"


def project_route_errors(
    routes: Iterable[tuple[str, tuple[str, ...]]],
    *,
    labels: Mapping[str, str],
    path_groups: Mapping[str, object],
) -> list[str]:
    """What a project does not name that its workflow's routes do.

    ``routes`` are ``(where, facts)`` pairs, ``where`` saying which route in
    words. A fact that does not parse is not reported here: the workflow
    refuses it on its own.
    """

    errors: list[str] = []
    for where, texts in routes:
        for text in texts:
            try:
                fact = parse_fact(text)
            except FactError:
                continue
            if fact.kind == LABEL and fact.names[0] not in labels:
                errors.append(
                    f"{where} tests the label {fact.names[0]!r}, which the project does not name"
                    f" ({_names(labels)})."
                )
            if fact.kind in CHANGE_FACTS:
                for group in fact.names:
                    if group not in path_groups:
                        errors.append(
                            f"{where} tests the path group {group!r}, which the project does not name"
                            f" ({_names(path_groups)})."
                        )
    return list(dict.fromkeys(errors))


def _names(named: Mapping[str, object]) -> str:
    return "it names " + ", ".join(sorted(named)) if named else "it names none"
