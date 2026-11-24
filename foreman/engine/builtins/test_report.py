"""How many tests ran and how they ended, from the test command's JUnit XML.

Foreman names an empty directory in ``FOREMAN_TEST_REPORT_DIR`` for each
test run. A test command that writes JUnit XML reports there tells Foreman
how many tests ran. pytest, vitest, jest, Playwright and
unittest-xml-reporting all write that format, so no tool is special. A
command that writes none still runs as before, and the count is unknown.

Foreman counts the ``<testcase>`` elements rather than trusting the totals
on ``<testsuite>``, which tools fill in differently. Every report is read in
full, however many there are and however large (ADR-0035 amendment,
2026-11-24): each is read a piece at a time and only the running totals are
kept, so its size costs time the test command already spent writing it, not
memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.parsers import expat

#: The variable that names the directory the test command writes reports into.
REPORT_DIR_ENV = "FOREMAN_TEST_REPORT_DIR"

#: At most this many failed tests are named; the count says how many failed.
MAX_FAILED_NAMED = 50

#: How much of a report is handed to the parser at a time.
_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class TestReport:
    """The totals of every report one test run wrote."""

    __test__ = False  # not a test class, whatever a test runner thinks of the name

    tests: int
    failed: int
    skipped: int
    files: int
    #: The failed tests, as ``(suite, name)``, at most ``MAX_FAILED_NAMED``.
    failed_tests: tuple[tuple[str, str], ...] = ()

    @property
    def passed(self) -> int:
        return self.tests - self.failed - self.skipped

    def as_payload(self) -> dict[str, int]:
        return {
            "tests": self.tests,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "files": self.files,
            "failed_tests": [{"suite": suite, "name": name} for suite, name in self.failed_tests],
        }

    def words(self) -> str:
        """``1599 tests, 1 skipped`` or ``3 of 186 tests failed``."""

        noun = "test" if self.tests == 1 else "tests"
        if self.failed:
            said = f"{self.failed} of {self.tests} {noun} failed"
        else:
            said = f"{self.tests} {noun}"
        return f"{said}, {self.skipped} skipped" if self.skipped else said


class _Refused(Exception):
    """A report Foreman will not read, and why."""


@dataclass
class _Tally:
    """Running totals while the reports are read; the failed tests named are capped."""

    tests: int = 0
    failed: int = 0
    skipped: int = 0
    failed_tests: list[tuple[str, str]] = field(default_factory=list)

    def failure(self, suite: str, name: str) -> None:
        self.failed += 1
        if len(self.failed_tests) < MAX_FAILED_NAMED:
            self.failed_tests.append((suite, name))


def _count(path: Path, tally: _Tally) -> None:
    """Add one report's test cases to ``tally``; ``ValueError`` when it cannot be read.

    A case counts as failed when one of its own elements is ``<failure>`` or
    ``<error>``, else as skipped when one is ``<skipped>``. The file's counts
    are added only once all of it has been read, so a report that breaks
    half-way adds nothing.

    A JUnit report declares no document type. One that does may define
    entities that expand without bound, and this Python's XML parser may be too
    old to stop that, so reading stops where the declaration starts, before any
    entity is defined or used.
    """

    mine = _Tally()
    depth = 0
    case: dict[str, object] | None = None

    def start(name: str, attributes: dict[str, str]) -> None:
        nonlocal depth, case
        depth += 1
        if name == "testcase" and case is None:
            case = {
                "depth": depth,
                "suite": attributes.get("classname") or "",
                "name": attributes.get("name") or "",
                "failed": False,
                "skipped": False,
            }
        elif case is not None and depth == case["depth"] + 1:
            if name in ("failure", "error"):
                case["failed"] = True
            elif name == "skipped":
                case["skipped"] = True

    def end(name: str) -> None:
        nonlocal depth, case
        if case is not None and depth == case["depth"]:
            mine.tests += 1
            if case["failed"]:
                mine.failure(str(case["suite"]), str(case["name"]))
            elif case["skipped"]:
                mine.skipped += 1
            case = None
        depth -= 1

    def refuse(*_: object) -> None:
        raise _Refused("it declares a document type, which a JUnit report does not")

    parser = expat.ParserCreate()
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(_CHUNK_BYTES):
                parser.Parse(chunk, False)
            parser.Parse(b"", True)
    except _Refused as exc:
        raise ValueError(str(exc)) from None
    except expat.ExpatError as exc:
        raise ValueError(f"it is not well-formed XML ({exc})") from None

    tally.tests += mine.tests
    tally.skipped += mine.skipped
    for suite, name in mine.failed_tests:
        tally.failure(suite, name)
    # Failures past the named ones still count.
    tally.failed += mine.failed - len(mine.failed_tests)


def read_reports(directory: Path) -> tuple[TestReport | None, list[str]]:
    """The totals of the reports in ``directory``, and why any could not be read.

    Every report is read in full. None when no report could be read: the
    command wrote none, or every one it wrote was unreadable. Links are not
    followed.
    """

    if not directory.is_dir():
        return None, []
    paths = sorted(
        path for path in directory.rglob("*.xml") if path.is_file() and not path.is_symlink()
    )
    problems: list[str] = []
    tally = _Tally()
    files = 0
    for path in paths:
        name = path.relative_to(directory).as_posix()
        try:
            _count(path, tally)
        except (OSError, ValueError) as exc:
            problems.append(f"{name} was not read: {exc}.")
            continue
        files += 1
    if not files:
        return None, problems
    return TestReport(
        tests=tally.tests,
        failed=tally.failed,
        skipped=tally.skipped,
        files=files,
        failed_tests=tuple(tally.failed_tests),
    ), problems
