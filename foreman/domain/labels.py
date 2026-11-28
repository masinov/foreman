"""Task labels and a project's path groups (ADR-0041 section 1).

A project names its labels (``labels``: a name and a one-line meaning) and its
path groups (``path_groups``: a name and path patterns). A route may depend on
the facts these give: ``label:<name>``, ``changed:<group>`` and
``changed_only:<group>``. This module holds what both settings are made of and
the one function that answers which groups a set of changed paths falls in.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache

#: A name is lowercase words (letters and digits) joined by ``-`` or ``_``.
_NAME = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")


class LabelError(ValueError):
    """Raised when a label, a path group or a pattern is not valid."""


def check_name(value: object, *, what: str) -> str:
    """Return ``value`` when it is a valid label or group name."""

    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise LabelError(
            f"{what} {value!r} is not a name: use lowercase words joined by "
            "'-' or '_', such as 'ui' or 'needs-docs'."
        )
    return value


def check_pattern(value: object) -> str:
    """Return ``value`` when it is a path pattern relative to the repository."""

    if not isinstance(value, str) or not value.strip():
        raise LabelError(f"A path pattern must be text, got {value!r}.")
    pattern = value.strip()
    if pattern.startswith("/") or pattern.startswith("~"):
        raise LabelError(f"Path pattern {pattern!r} must be relative to the repository.")
    if pattern.startswith("!"):
        raise LabelError(f"Path pattern {pattern!r}: a negated pattern is not supported.")
    if "\\" in pattern or "\n" in pattern:
        raise LabelError(f"Path pattern {pattern!r} must use '/' and be on one line.")
    if re.match(r"[A-Za-z]:", pattern):
        raise LabelError(f"Path pattern {pattern!r} must be relative to the repository.")
    parts = pattern.rstrip("/").split("/")
    if any(part.strip() == ".." for part in parts):
        raise LabelError(f"Path pattern {pattern!r} must not contain '..'.")
    if any(part.strip() in {"", "."} for part in parts):
        # ``./docs``, ``docs//a`` and ``docs/./a`` would never match a path.
        raise LabelError(
            f"Path pattern {pattern!r}: write it without './', '//' or '/./', "
            "such as 'docs/**'."
        )
    if "[:" in pattern:
        raise LabelError(
            f"Path pattern {pattern!r}: character classes such as [[:alpha:]] are "
            "not supported; list the characters, such as [a-z]."
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            _compile(pattern)
    except (re.error, Warning) as exc:
        raise LabelError(f"Path pattern {pattern!r} is not a valid pattern: {exc}.") from exc
    return pattern


def parse_labels(value: object) -> dict[str, str]:
    """Validate the ``labels`` setting: ``{name: one-line meaning}``."""

    if value is None or value == {}:
        return {}
    if not isinstance(value, Mapping):
        raise LabelError(
            "labels must be an object of label names and their meanings, "
            'such as {"ui": "changes what a person sees"}.'
        )
    labels: dict[str, str] = {}
    for name, meaning in value.items():
        check_name(name, what="Label")
        if not isinstance(meaning, str) or not meaning.strip() or "\n" in meaning.strip():
            raise LabelError(f"Label {name!r} needs a meaning of one line of text.")
        labels[name] = meaning.strip()
    return labels


def parse_path_groups(value: object) -> dict[str, tuple[str, ...]]:
    """Validate the ``path_groups`` setting: ``{name: [pattern, ...]}``."""

    if value is None or value == {}:
        return {}
    if not isinstance(value, Mapping):
        raise LabelError(
            "path_groups must be an object of group names and their path patterns, "
            'such as {"frontend": ["frontend/**"]}.'
        )
    groups: dict[str, tuple[str, ...]] = {}
    for name, patterns in value.items():
        check_name(name, what="Path group")
        if isinstance(patterns, str):
            patterns = [patterns]
        if not isinstance(patterns, (list, tuple)) or not patterns:
            raise LabelError(f"Path group {name!r} needs a list of path patterns.")
        cleaned: list[str] = []
        for pattern in patterns:
            text = check_pattern(pattern)
            if text not in cleaned:
                cleaned.append(text)
        groups[name] = tuple(cleaned)
    return groups


def unknown_labels(labels: Iterable[str], known: Mapping[str, str]) -> list[str]:
    """The labels of ``labels`` that ``known`` (the project's) does not name."""

    return [label for label in labels if label not in known]


def clean_labels(value: object) -> list[str]:
    """A list of label names from a list, or from text with commas; no repeats.

    Only the shape is checked here; whether a project names them is
    ``unknown_labels``.
    """

    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = [part for part in value.split(",")]
    if not isinstance(value, (list, tuple)):
        raise LabelError(f"labels must be a list of label names, got {value!r}.")
    labels: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            raise LabelError(f"A label must be text, got {entry!r}.")
        name = entry.strip()
        if name and name not in labels:
            labels.append(name)
    return labels


# --- Path patterns ----------------------------------------------------------


@lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern[str]:
    """A gitignore-style pattern as a regular expression over a path.

    As gitignore: a pattern with no ``/`` but a trailing one (``*.md``,
    ``docs/``) matches a name at any depth; one with a ``/`` at its start or
    in its middle (``frontend/**``, ``docs/guide``) is anchored at the
    repository's root. A trailing ``/`` names a directory only, so ``docs/``
    matches what is below a ``docs`` directory and not a file named ``docs``.
    A pattern that matches a directory matches everything below it. ``*``
    and ``?`` stay within one path part, ``**`` crosses them.
    """

    directory_only = pattern.endswith("/")
    body = pattern.rstrip("/")
    anchored = "/" in body
    parts = body.split("/")
    out: list[str] = []
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if part == "**":
            # ``**`` as the last part: everything below; elsewhere: any
            # number of directories (including none).
            out.append(".*" if last else "(?:[^/]+/)*")
            continue
        out.append(_part_regex(part) + ("" if last else "/"))
    regex = "".join(out)
    if regex.endswith(".*") and parts[-1] == "**":
        # ``dir/**`` matches what is below ``dir``, not ``dir`` itself; the
        # trailing "/" the loop added before ``**`` is already in the regex.
        tail = ""
    else:
        # A paths list holds files: a directory-only pattern matches below it.
        tail = "/.*" if directory_only else "(?:/.*)?"
    head = "" if anchored else "(?:.*/)?"
    return re.compile(f"{head}{regex}{tail}")


def _part_regex(part: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(part):
        ch = part[i]
        if ch == "*":
            while i + 1 < len(part) and part[i + 1] == "*":
                i += 1
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        elif ch == "[":
            end = part.find("]", i + 2)
            if end == -1:
                out.append(re.escape(ch))
            else:
                body = part[i + 1 : end]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = end
        else:
            out.append(re.escape(ch))
        i += 1
    return "".join(out)


def matches_pattern(path: str, pattern: str) -> bool:
    """Whether ``path`` (relative to the repository) falls under ``pattern``."""

    return _compile(pattern).fullmatch(_normal(path)) is not None


def _normal(path: str) -> str:
    text = path.strip()
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def groups_of_paths(
    paths: Iterable[str], groups: Mapping[str, Sequence[str]]
) -> dict[str, frozenset[str]]:
    """For each changed path, the names of the path groups it falls in.

    A path in no group maps to an empty set; it is not left out, because
    ``changed_only`` must see it.
    """

    found: dict[str, frozenset[str]] = {}
    for path in paths:
        normal = _normal(path)
        if not normal:
            continue
        found[normal] = frozenset(
            name
            for name, patterns in groups.items()
            if any(matches_pattern(normal, pattern) for pattern in patterns)
        )
    return found


def changed_in(path_groups: Mapping[str, frozenset[str]], group: str) -> bool:
    """The fact ``changed:<group>``: any changed path is in the group."""

    return any(group in names for names in path_groups.values())


def changed_only_in(path_groups: Mapping[str, frozenset[str]], groups: Iterable[str]) -> bool:
    """The fact ``changed_only:<group>``: every changed path is in the groups.

    A change that touched nothing is not "only" anything: it is false. A path
    in no group makes it false.
    """

    wanted = frozenset(groups)
    return bool(path_groups) and all(names & wanted for names in path_groups.values())
