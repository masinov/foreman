"""The documents a task rests on: a path, optionally a heading, and the
commit of the default branch at the moment each was named.

Foreman captures the commit; nobody types it. The text form, for a CLI flag
or a form field, is ``path`` or ``path#heading``, one per entry.
"""

from __future__ import annotations

import posixpath
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import ForemanError


class RestsOnError(ForemanError):
    """A named document is not acceptable. The message says why."""


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
        return f"{self.path}#{self.heading}" if self.heading else self.path

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "heading": self.heading, "commit": self.commit}


def clean_path(raw: str) -> str:
    """A repository-relative POSIX path, or ``RestsOnError`` saying why not."""

    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        raise RestsOnError("A document needs a path.")
    if text.startswith("/"):
        raise RestsOnError(f"{text}: name the path from the repository root, not an absolute path.")
    normal = posixpath.normpath(text)
    if normal == ".." or normal.startswith("../") or normal == ".":
        raise RestsOnError(f"{text}: the path must stay inside the repository.")
    return normal


def parse_entry(value: Any) -> DocumentRef:
    """One entry: ``"path"``, ``"path#heading"``, a mapping or a ``DocumentRef``."""

    if isinstance(value, DocumentRef):
        return DocumentRef(clean_path(value.path), value.heading.strip(), value.commit)
    if isinstance(value, Mapping):
        return DocumentRef(
            clean_path(str(value.get("path") or "")),
            str(value.get("heading") or "").strip(),
            str(value.get("commit") or "").strip(),
        )
    if isinstance(value, str):
        path, _, heading = value.partition("#")
        return DocumentRef(clean_path(path), heading.strip())
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


def pointers_text(refs: Sequence[DocumentRef]) -> str:
    """The task layer's section for a step (ADR-0041 section 6): pointers, not text.

    Empty when the task names no document.
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
    return "\n".join(lines)
