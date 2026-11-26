"""ADR numbers given at merge, and the ADR index generated (ADR-0040 section 3.2).

A branch writes a decision as ``<adr dir>/new-<slug>.md`` and refers to it by
that path. When the task merges, :func:`settle` runs in the tree the merge is
being made in: each ``new-<slug>.md`` takes the next free number (it is
renamed to ``ADR-NNNN-<slug>.md``, its title line gets the number and the
references to it are rewritten) and the index, ``README.md``, is regenerated
from each ADR's title and status. The hand-written part of the index, above
the generated list, is kept. Two ADRs with one number are refused: git never
reports that clash, since the files have different names.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import posixpath
import re

from .git import run_git

INDEX_FILE = "README.md"

#: The generated list starts at this line. Everything above it is the
#: folder's hand-written introduction.
MARKER = "<!-- foreman:adr-index - generated from each ADR's title and status; edit the ADRs, not this list -->"

_NEW = re.compile(r"^new-(?P<slug>[^/\s]+)\.md$")
_NUMBERED = re.compile(r"^ADR-(?P<number>\d{4,})-(?P<slug>[^/\s]+)\.md$")
_TITLE = re.compile(r"^#[ \t]+(?:ADR-(?:\d+|X+)[ \t]*[:–—-][ \t]*|ADR[ \t]*:[ \t]*)?(?P<title>.+?)[ \t]*$")
_STATUS = re.compile(r"^[ \t]*[-*]?[ \t]*\*{0,2}Status:?\*{0,2}:?[ \t]*(?P<status>.+?)[ \t]*$", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Adr:
    """One numbered decision: its number, file name, title and status."""

    number: int
    name: str
    title: str
    status: str


@dataclass(frozen=True, slots=True)
class Settlement:
    """What :func:`settle` did, or why it refused."""

    #: ``(old path, new path)`` for each decision that was numbered.
    numbered: tuple[tuple[str, str], ...] = ()
    #: The files that share a number, by number; set when the merge is refused.
    duplicates: tuple[tuple[int, tuple[str, ...]], ...] = ()
    #: Why a new decision could not be numbered (it is not UTF-8 text); set
    #: when the merge is refused for it.
    problem: str | None = None

    def refusal(self) -> str | None:
        if self.problem:
            return self.problem
        if not self.duplicates:
            return None
        clashes = "; ".join(
            f"ADR-{number:04d}: {', '.join(names)}" for number, names in self.duplicates
        )
        return (
            f"The merge would leave two ADRs with the same number ({clashes}). "
            "Give one of them another number, or rename it to new-<slug>.md in the same folder "
            "so that the merge numbers it, then merge again."
        )


def title_and_status(text: str) -> tuple[str, str]:
    """An ADR's title (without its number) and its status, from its first lines.

    The status is the word or words after ``Status:`` up to a parenthesis or a
    semicolon: ``accepted (the owner approved it)`` is ``accepted``.
    """

    title = ""
    for line in text.splitlines():
        found = _TITLE.match(line)
        if found:
            title = found.group("title")
            break
    status = ""
    found = _STATUS.search(text)
    heading = re.search(r"^##[ \t]+Status[ \t]*\n+[ \t]*(?P<status>\S[^\n]*)", text, re.MULTILINE)
    raw = found.group("status") if found else heading.group("status").lower() if heading else ""
    if raw:
        status = re.split(r"\s+\(|;", raw, maxsplit=1)[0].strip().rstrip(".,")
    return title, status


def set_title_number(text: str, number: int) -> str:
    """The text with its title line reading ``# ADR-NNNN: <title>``."""

    lines = text.split("\n")
    for index, line in enumerate(lines):
        found = _TITLE.match(line)
        if found:
            lines[index] = f"# ADR-{number:04d}: {found.group('title')}"
            break
    return "\n".join(lines)


def read_adrs(folder: Path) -> list[Adr]:
    """Every numbered ADR in the folder, in number order."""

    adrs = []
    for path in folder.iterdir() if folder.is_dir() else ():
        found = _NUMBERED.match(path.name)
        if found and path.is_file():
            title, status = title_and_status(path.read_text(encoding="utf-8", errors="replace"))
            adrs.append(Adr(int(found.group("number")), path.name, title or found.group("slug"), status))
    return sorted(adrs, key=lambda adr: (adr.number, adr.name))


def duplicate_numbers(adrs: list[Adr]) -> tuple[tuple[int, tuple[str, ...]], ...]:
    by_number: dict[int, list[str]] = {}
    for adr in adrs:
        by_number.setdefault(adr.number, []).append(adr.name)
    return tuple((n, tuple(names)) for n, names in sorted(by_number.items()) if len(names) > 1)


def render_index(existing: str, adrs: list[Adr]) -> str:
    """The index with its generated list replaced; the hand-written part is kept."""

    if MARKER in existing:
        head = existing.split(MARKER, 1)[0]
    else:
        # The first generation: what stood above the old hand-made list stays.
        head = re.split(r"^## Index\b", existing, maxsplit=1, flags=re.MULTILINE)[0]
    head = head.rstrip()
    rows = [
        f"| ADR-{adr.number:04d} | {adr.title.replace('|', '/')} | {adr.status.replace('|', '/')} |"
        for adr in adrs
    ]
    table = "\n".join(["| ADR | Title | Status |", "|---|---|---|", *rows])
    prefix = f"{head}\n\n" if head else "# ADRs\n\n"
    return f"{prefix}{MARKER}\n\n## Index\n\n{table}\n"


def _new_files(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir() if _NEW.match(path.name) and path.is_file())


def _rewrite_references(
    root: Path, adr_dir: str, old: str, new: str, files: frozenset[str]
) -> list[str]:
    """Point the branch's own files that name ``old`` at ``new``; returns the files.

    Only ``files`` (what the branch changed) are rewritten, and only a mention
    of the decision itself: its name alone, or a path that leads to it in
    ``adr_dir`` (from the repository's root or from the file's own folder).
    A file of the same name in another folder is left alone.
    """

    folder = posixpath.normpath(adr_dir.strip("/"))
    pattern = re.compile(r"(?<![\w.-])(?P<path>[\w./-]*/)?" + re.escape(old) + r"(?![\w-])")
    changed = []
    for name in sorted(files):
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        here = posixpath.dirname(name)

        def point(match: re.Match[str]) -> str:
            prefix = match.group("path")
            if prefix:
                leads = {
                    posixpath.normpath(prefix.lstrip("/")),
                    posixpath.normpath(posixpath.join(here, prefix)),
                }
                if not any(lead == folder or lead.endswith(f"/{folder}") for lead in leads):
                    return match.group(0)
            return f"{prefix or ''}{new}"

        rewritten = pattern.sub(point, text)
        if rewritten != text:
            path.write_text(rewritten, encoding="utf-8")
            changed.append(name)
    return changed


def settle(root: Path, adr_dir: str, changed: list[str] | None = None) -> Settlement | None:
    """Number the new ADRs and regenerate the index, in the tree ``root``.

    ``changed`` is what the branch brings (the merge's staged paths): only
    those files have their references rewritten. Nothing is staged or written
    when two ADRs share a number or a new one is not UTF-8 text (the returned
    settlement says why). ``None``: the project has no such folder, and is
    left alone. Everything changed is staged, for the caller to commit.
    """

    folder = root / adr_dir
    if not adr_dir or not folder.is_dir():
        return None
    adrs = read_adrs(folder)
    duplicates = duplicate_numbers(adrs)
    if duplicates:
        return Settlement(duplicates=duplicates)

    new_names = _new_files(folder)
    for name in new_names:
        try:
            (folder / name).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return Settlement(
                problem=(
                    f"{adr_dir}/{name} is not UTF-8 text, so it cannot be numbered. "
                    "Save it as UTF-8 on the branch, then merge again."
                )
            )

    numbered: list[tuple[str, str]] = []
    # The branch's files, followed through their renames as the loop goes.
    files = {path for path in (changed or []) if path}
    number = max((adr.number for adr in adrs), default=0)
    for name in new_names:
        number += 1
        slug = _NEW.match(name).group("slug")  # type: ignore[union-attr]
        old, new = f"{adr_dir}/{name}", f"{adr_dir}/ADR-{number:04d}-{slug}.md"
        run_git(root, "mv", old, new)
        files.discard(old)
        files.add(new)
        path = root / new
        # In its own text, ADR-XXXX is the decision itself.
        # Read now: numbering an earlier one may have rewritten a reference in it.
        text = set_title_number(path.read_text(encoding="utf-8"), number).replace("ADR-XXXX", f"ADR-{number:04d}")
        path.write_text(text, encoding="utf-8")
        _rewrite_references(root, adr_dir, name, f"ADR-{number:04d}-{slug}.md", frozenset(files))
        numbered.append((old, new))

    index = folder / INDEX_FILE
    current = index.read_text(encoding="utf-8") if index.is_file() else ""
    index.write_text(render_index(current, read_adrs(folder)), encoding="utf-8")
    present = sorted(path for path in files | {f"{adr_dir}/{INDEX_FILE}"} if (root / path).exists())
    run_git(root, "add", "--", *present)
    return Settlement(numbered=tuple(numbered))


def touches_adrs(staged: list[str], adr_dir: str) -> bool:
    """Whether a merge brings a change to the folder's decisions (not just the index)."""

    prefix = f"{adr_dir.strip('/')}/"
    return any(
        path.startswith(prefix) and path != f"{prefix}{INDEX_FILE}" for path in staged
    )
