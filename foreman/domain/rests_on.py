"""The documents a task rests on: a path, optionally a heading, and the
commit of the default branch at the moment each was named.

Foreman captures the commit; nobody types it. The text form, for a CLI flag
or a form field, is ``path`` or ``path#heading``, one per entry. A space
before the ``#`` makes the separator unambiguous, so a path that has a ``#``
in it is written ``path #heading``, or ``path #`` with no heading.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import ForemanError


class RestsOnError(ForemanError):
    """A named document is not acceptable. The message says why."""


#: The heading separator when written unambiguously: a space, then ``#``.
_SEPARATOR = re.compile(r"\s#")
#: Line breaks and other control characters: a path and a heading are one line.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(slots=True, frozen=True)
class DocumentRef:
    """One document a task rests on."""

    path: str
    heading: str = ""
    #: The default branch's commit when the document was named; empty only
    #: for an entry parsed but not yet resolved.
    commit: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.path, self.heading)

    def label(self) -> str:
        """The entry as people read it, and as the text form takes it back (``text``)."""

        return self.text() if "#" in self.path else (f"{self.path}#{self.heading}" if self.heading else self.path)

    def text(self) -> str:
        """The text form that ``parse_entry`` reads back as this same entry."""

        if "#" in self.path or _SEPARATOR.search(self.heading):
            return f"{self.path} #{self.heading}"
        return f"{self.path}#{self.heading}" if self.heading else self.path

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "heading": self.heading, "commit": self.commit}


def clean_path(raw: str) -> str:
    """A repository-relative POSIX path, or ``RestsOnError`` saying why not."""

    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        raise RestsOnError("A document needs a path.")
    if _CONTROL.search(text):
        raise RestsOnError(f"{text!r}: a path is one line, with no line break or control character.")
    if text.startswith("/"):
        raise RestsOnError(f"{text}: name the path from the repository root, not an absolute path.")
    normal = posixpath.normpath(text)
    if normal == ".." or normal.startswith("../") or normal == ".":
        raise RestsOnError(f"{text}: the path must stay inside the repository.")
    return normal


def clean_heading(raw: str) -> str:
    """A heading, trimmed, or ``RestsOnError`` when it is more than one line."""

    text = str(raw or "").strip()
    if _CONTROL.search(text):
        raise RestsOnError(f"{text!r}: a heading is one line, with no line break or control character.")
    return text


def split_text(value: str) -> tuple[str, str]:
    """The path and the heading of the text form.

    A space then ``#`` separates them when the text has one (so a path may
    hold a ``#``); otherwise the first ``#`` does.
    """

    found = _SEPARATOR.search(value)
    if found:
        return value[: found.start()], value[found.end() :]
    path, _, heading = value.partition("#")
    return path, heading


def parse_entry(value: Any) -> DocumentRef:
    """One entry: ``"path"``, ``"path#heading"``, ``"path #heading"``, a mapping or a ``DocumentRef``."""

    if isinstance(value, DocumentRef):
        return DocumentRef(clean_path(value.path), clean_heading(value.heading), value.commit)
    if isinstance(value, Mapping):
        return DocumentRef(
            clean_path(str(value.get("path") or "")),
            clean_heading(str(value.get("heading") or "")),
            str(value.get("commit") or "").strip(),
        )
    if isinstance(value, str):
        path, heading = split_text(value)
        return DocumentRef(clean_path(path), clean_heading(heading))
    raise RestsOnError("Each document is a path, `path#heading`, or an object with `path` and `heading`.")


def parse_documents(value: Any) -> list[DocumentRef]:
    """The entries of a list, or of a text with one entry per line; no duplicates."""

    if value is None:
        return []
    if isinstance(value, str):
        items: Sequence[Any] = [line for line in value.splitlines() if line.strip()]
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        raise RestsOnError("The documents a task rests on are a list.")
    found: list[DocumentRef] = []
    for item in items:
        entry = parse_entry(item)
        if all(entry.key != other.key for other in found):
            found.append(entry)
    return found


def documents_from_json(items: Any) -> list[DocumentRef]:
    """The stored list, read back; an entry that does not parse is dropped."""

    refs: list[DocumentRef] = []
    for item in items if isinstance(items, list) else []:
        try:
            refs.append(parse_entry(item))
        except RestsOnError:
            continue
    return refs


def pointers_text(
    refs: Sequence[DocumentRef],
    changed: Mapping[tuple[str, str], Mapping[str, str]] | None = None,
) -> str:
    """The task layer's section for a step (ADR-0041 section 6): pointers, not text.

    Empty when the task names no document. ``changed`` holds, by (path,
    heading), the latest merge that changed a document since it was named:
    the step is told so, and that the task is not changed to match.
    """

    if not refs:
        return ""
    lines = [
        "## Documents this task rests on",
        "",
        "Pointers, not the text: read what you need. Each was named at the commit shown "
        "(`git show <commit>:<path>` reads it as it was then); the file may have changed since.",
        "",
    ]
    for ref in refs:
        heading = f", {ref.heading}" if ref.heading else ""
        at = f" (named at {ref.commit[:10]})" if ref.commit else ""
        lines.append(f"- {ref.path}{heading}{at}")
    moved = [(ref, (changed or {}).get(ref.key)) for ref in refs]
    moved = [(ref, change) for ref, change in moved if change]
    if moved:
        lines += [
            "",
            "### Changed since this task was planned",
            "",
            "These documents were changed by a merge after the task named them. Nothing in the task "
            "was updated to match. Read what changed (`git diff <named commit> <merge commit> -- <path>`) "
            "before relying on the task's description or criteria, and say in your report where the "
            "change matters.",
            "",
        ]
        for ref, change in moved:
            who = change.get("merged_task_key") or "another task"
            lines.append(
                f"- {ref.label()}: changed in {who}'s merge ({str(change.get('merge_sha', ''))[:10]}), "
                f"named at {ref.commit[:10]}"
            )
    return "\n".join(lines)
