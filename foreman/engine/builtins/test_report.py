"""How many tests ran and how they ended, from the test command's JUnit XML.

Foreman names an empty directory in ``FOREMAN_TEST_REPORT_DIR`` for each
test run. A test command that writes JUnit XML reports there tells Foreman
how many tests ran. pytest, vitest, jest, Playwright and
unittest-xml-reporting all write that format, so no tool is special. A
command that writes none still runs as before, and the count is unknown.

Foreman counts the ``<testcase>`` elements rather than trusting the totals
on ``<testsuite>``, which tools fill in differently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ElementTree

#: The variable that names the directory the test command writes reports into.
REPORT_DIR_ENV = "FOREMAN_TEST_REPORT_DIR"

#: A report larger than this is not read.
MAX_REPORT_BYTES = 32 * 1024 * 1024

#: At most this many report files are read from one run.
MAX_REPORT_FILES = 200

# A JUnit report declares no document type. One that does may define
# entities that expand without bound, and this Python's XML parser may be
# too old to stop that, so such a file is not parsed at all.
_DECLARATIONS = (b"<!doctype", b"<!entity")


@dataclass(frozen=True, slots=True)
class TestReport:
    """The totals of every report one test run wrote."""

    __test__ = False  # not a test class, whatever a test runner thinks of the name

    tests: int
    failed: int
    skipped: int
    files: int

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
        }

    def words(self) -> str:
        """``1599 tests, 1 skipped`` or ``3 of 186 tests failed``."""

        noun = "test" if self.tests == 1 else "tests"
        if self.failed:
            said = f"{self.failed} of {self.tests} {noun} failed"
        else:
            said = f"{self.tests} {noun}"
        return f"{said}, {self.skipped} skipped" if self.skipped else said


def _count(path: Path) -> tuple[int, int, int]:
    """``(tests, failed, skipped)`` in one report; ``ValueError`` when it cannot be read."""

    size = path.stat().st_size
    if size > MAX_REPORT_BYTES:
        raise ValueError(f"it is {size} bytes, over the {MAX_REPORT_BYTES} Foreman reads")
    data = path.read_bytes()
    lowered = data.lower()
    if any(mark in lowered for mark in _DECLARATIONS):
        raise ValueError("it declares a document type, which a JUnit report does not")
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValueError(f"it is not well-formed XML ({exc})") from None
    tests = failed = skipped = 0
    for case in root.iter("testcase"):
        tests += 1
        if case.find("failure") is not None or case.find("error") is not None:
            failed += 1
        elif case.find("skipped") is not None:
            skipped += 1
    return tests, failed, skipped


def read_reports(directory: Path) -> tuple[TestReport | None, list[str]]:
    """The totals of the reports in ``directory``, and why any could not be read.

    None when no report could be read: the command wrote none, or every one
    it wrote was unreadable. Links are not followed.
    """

    if not directory.is_dir():
        return None, []
    paths = sorted(
        path for path in directory.rglob("*.xml") if path.is_file() and not path.is_symlink()
    )
    problems: list[str] = []
    if len(paths) > MAX_REPORT_FILES:
        problems.append(f"{len(paths)} reports; Foreman read the first {MAX_REPORT_FILES}.")
        paths = paths[:MAX_REPORT_FILES]
    tests = failed = skipped = files = 0
    for path in paths:
        name = path.relative_to(directory).as_posix()
        try:
            counted = _count(path)
        except (OSError, ValueError) as exc:
            problems.append(f"{name} was not read: {exc}.")
            continue
        tests += counted[0]
        failed += counted[1]
        skipped += counted[2]
        files += 1
    if not files:
        return None, problems
    return TestReport(tests=tests, failed=failed, skipped=skipped, files=files), problems
