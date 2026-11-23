from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from foreman.engine.builtins import test_report
from foreman.engine.builtins.test_report import TestReport, read_reports


def _write(directory: Path, name: str, text: str) -> None:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ReadReportsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.dir = Path(self._temp.name)

    def test_no_report_is_no_count(self) -> None:
        self.assertEqual(read_reports(self.dir), (None, []))
        self.assertEqual(read_reports(self.dir / "absent"), (None, []))

    def test_every_report_is_counted_by_its_test_cases(self) -> None:
        # unittest-xml-reporting writes one file per class, vitest one file in
        # a subfolder; the suite's own totals are ignored, the cases counted.
        _write(self.dir, "TEST-a.xml", '<testsuite tests="99"><testcase name="x"/><testcase name="y">'
               '<failure message="no"/></testcase></testsuite>')
        _write(self.dir, "frontend/junit.xml", '<testsuites><testsuite><testcase name="z"><error/></testcase>'
               '<testcase name="w"><skipped/></testcase><testcase name="v"/></testsuite></testsuites>')
        report, problems = read_reports(self.dir)
        self.assertEqual((report.tests, report.failed, report.skipped, report.files), (5, 2, 1, 2))
        self.assertEqual(report.passed, 2)
        self.assertEqual(report.failed_tests, (("", "y"), ("", "z")))
        self.assertEqual(problems, [])

    def test_an_unreadable_report_is_named_and_the_rest_counted(self) -> None:
        _write(self.dir, "good.xml", '<testsuite><testcase name="x"/></testsuite>')
        _write(self.dir, "broken.xml", "<testsuite><testcase")
        report, problems = read_reports(self.dir)
        self.assertEqual(report, TestReport(tests=1, failed=0, skipped=0, files=1))
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("broken.xml was not read: it is not well-formed XML"))

    def test_a_report_that_declares_entities_is_not_parsed(self) -> None:
        _write(self.dir, "bomb.xml", '<?xml version="1.0"?><!DOCTYPE t [<!ENTITY a "aaaa">]>'
               "<testsuite><testcase name='&a;'/></testsuite>")
        report, problems = read_reports(self.dir)
        self.assertIsNone(report)
        self.assertEqual(problems, ["bomb.xml was not read: it declares a document type, which a JUnit report does not."])

    def test_a_report_over_the_size_limit_is_not_read(self) -> None:
        _write(self.dir, "big.xml", "<testsuite>" + " " * 64 + "</testsuite>")
        original = test_report.MAX_REPORT_BYTES
        test_report.MAX_REPORT_BYTES = 16
        self.addCleanup(setattr, test_report, "MAX_REPORT_BYTES", original)
        report, problems = read_reports(self.dir)
        self.assertIsNone(report)
        self.assertIn("over the 16 Foreman reads", problems[0])

    def test_a_link_is_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as elsewhere:
            target = Path(elsewhere) / "outside.xml"
            target.write_text('<testsuite><testcase name="x"/></testsuite>', encoding="utf-8")
            (self.dir / "link.xml").symlink_to(target)
            self.assertEqual(read_reports(self.dir), (None, []))

    def test_failed_tests_are_named_up_to_a_limit(self) -> None:
        cases = "".join(f'<testcase classname="tests.test_a.ATests" name="test_{i}"><failure/></testcase>' for i in range(60))
        _write(self.dir, "many.xml", f"<testsuite>{cases}</testsuite>")
        report, _ = read_reports(self.dir)
        self.assertEqual(report.failed, 60)
        self.assertEqual(len(report.failed_tests), test_report.MAX_FAILED_NAMED)
        self.assertEqual(report.failed_tests[0], ("tests.test_a.ATests", "test_0"))
        self.assertEqual(report.as_payload()["failed_tests"][0], {"suite": "tests.test_a.ATests", "name": "test_0"})

    def test_words(self) -> None:
        self.assertEqual(TestReport(tests=1, failed=0, skipped=0, files=1).words(), "1 test")
        self.assertEqual(TestReport(tests=1599, failed=0, skipped=1, files=9).words(), "1599 tests, 1 skipped")
        self.assertEqual(TestReport(tests=186, failed=3, skipped=0, files=1).words(), "3 of 186 tests failed")


if __name__ == "__main__":
    unittest.main()
