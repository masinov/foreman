"""``CHANGELOG.md`` generated from change files (ADR-0040 section 3.1).

A task describes its change in ``changes/<task key>.md``: a title line, then a
few bullets. No change edits ``CHANGELOG.md``; when a sprint finishes, Foreman
folds the change files into one section of it, newest sprint first, and
removes them. What the file held before stays below the generated sections.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

from ..domain.models import Sprint
from ..repo.git import run_git

#: Where change files live, in the repository.
CHANGES_DIR = "changes"
CHANGELOG_FILE = "CHANGELOG.md"

#: Generated sections go straight after this line. Everything the file held
#: before the first generation stays below them, as history.
MARKER = "<!-- foreman:changelog - sprints below, newest first; earlier history follows -->"

_INTRO = "# Changelog\n"


@dataclass(frozen=True, slots=True)
class Change:
    """One change file: the task key (its name), a title and its bullets."""

    key: str
    title: str
    bullets: tuple[str, ...]
    path: str


def _sort_key(key: str) -> list[tuple[int, int | str]]:
    return [(0, int(part)) if part.isdigit() else (1, part.lower()) for part in re.split(r"(\d+)", key) if part]


def parse_change(key: str, text: str, path: str) -> Change:
    """A change file's title (its first non-empty line) and the lines after it."""

    lines = [line.rstrip() for line in text.strip().splitlines()]
    title = re.sub(r"^#+\s*", "", lines[0]).strip() if lines else ""
    bullets: list[str] = []
    for line in lines[1:]:
        if re.match(r"^\s*[-*]\s+", line):
            bullets.append(re.sub(r"^\s*[-*]\s+", "", line).strip())
        elif line.strip() and bullets:
            bullets[-1] += " " + line.strip()  # a wrapped bullet
        elif line.strip():
            bullets.append(line.strip())
    return Change(key=key, title=title or key, bullets=tuple(bullets), path=path)


def read_changes(root: Path) -> list[Change]:
    """The change files under ``changes/``, in task-key order; the README is not one."""

    directory = root / CHANGES_DIR
    if not directory.is_dir():
        return []
    found = [
        parse_change(path.stem, path.read_text(encoding="utf-8"), f"{CHANGES_DIR}/{path.name}")
        for path in directory.glob("*.md")
        if path.is_file() and path.name.lower() != "readme.md"
    ]
    return sorted(found, key=lambda change: _sort_key(change.key))


def render_section(sprint: Sprint, completed: datetime, changes: list[Change]) -> str:
    """One sprint's section: each change under its task key."""

    parts = [f"## {sprint.title} ({completed.astimezone(timezone.utc):%Y-%m-%d})", ""]
    for change in changes:
        parts.append(f"### {change.key}: {change.title}")
        parts.append("")
        parts += [f"- {bullet}" for bullet in change.bullets]
        if change.bullets:
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def fold_section(existing: str, section: str) -> str:
    """``existing`` with ``section`` first among the generated ones.

    The first time, the marker goes before the first section heading of the
    file (after its introduction), so what the file held stays below it.
    """

    existing = existing.replace("\r\n", "\n")
    if not existing.strip():
        return f"{_INTRO}\n{MARKER}\n\n{section}"
    lines = existing.split("\n")
    for index, line in enumerate(lines):
        if line.strip() == MARKER:
            head, tail = lines[: index + 1], lines[index + 1 :]
            break
    else:
        first = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
        head, tail = lines[:first] + [MARKER], lines[first:]
    rest = "\n".join(tail).lstrip("\n")
    body = "\n".join(head).rstrip("\n") + "\n\n" + section
    return body + ("\n" + rest if rest.strip() else "")


def stage_changelog(root: Path, sprint: Sprint, completed: datetime) -> list[str]:
    """Write the sprint's section and ``git rm`` the folded files in ``root``.

    The paths to commit: ``CHANGELOG.md`` and each removed change file. Empty
    when there are no change files; nothing is written then.
    """

    changes = read_changes(root)
    if not changes:
        return []
    target = root / CHANGELOG_FILE
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    target.write_text(fold_section(existing, render_section(sprint, completed, changes)), encoding="utf-8")
    paths = [change.path for change in changes]
    run_git(root, "rm", "--quiet", "--", *paths)
    run_git(root, "add", "--", CHANGELOG_FILE)
    return [CHANGELOG_FILE, *paths]
