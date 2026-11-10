from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from foreman.builtins import BuiltinExecutor
from foreman.models import Project


def _run(directory: Path, command: str, **settings: object):
    project = Project(
        id="p",
        name="P",
        repo_path=str(directory),
        workflow_id="development",
        settings={"test_command": command, **settings},
    )
    result = BuiltinExecutor()._run_tests(project=project, working_dir=directory)
    run_event = next(e for e in result.events if e.event_type == "engine.test_run")
    return result, run_event.payload


class RunTestsReportTests(unittest.TestCase):
    def test_success_reports_summary_line_and_tail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, payload = _run(Path(temp_dir), "echo hello")
        self.assertEqual(result.outcome, "success")
        first, blank, rest = result.detail.split("\n", 2)
        self.assertRegex(first, r"^Tests passed in \d+\.\ds \(exit 0\)\.$")
        self.assertEqual(blank, "")
        self.assertEqual(rest, "hello")
        self.assertIsInstance(payload["duration_seconds"], float)
        self.assertGreaterEqual(payload["duration_seconds"], 0.0)

    def test_failure_reports_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, payload = _run(Path(temp_dir), "echo boom; exit 3")
        self.assertEqual(result.outcome, "failure")
        lines = result.detail.split("\n")
        self.assertRegex(lines[0], r"^Tests failed in \d+\.\ds \(exit 3\)\.$")
        self.assertEqual(lines[1:], ["", "boom"])
        self.assertEqual(payload["exit_code"], 3)

    def test_silent_success_has_only_summary_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, _ = _run(Path(temp_dir), "true")
        self.assertRegex(result.detail, r"^Tests passed in \d+\.\ds \(exit 0\)\.$")

    def test_timeout_keeps_existing_sentence_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, payload = _run(
                Path(temp_dir), "echo started; sleep 30", test_timeout_seconds=1
            )
        self.assertEqual(result.outcome, "failure")
        self.assertTrue(
            result.detail.startswith("Test command timed out after 1s and was killed.")
        )
        self.assertTrue(payload["timed_out"])
        self.assertGreaterEqual(payload["duration_seconds"], 1.0)

    def test_head_sha_matches_repository_head(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            git = ["git", "-c", "user.name=T", "-c", "user.email=t@example.com"]
            subprocess.run([*git, "init", "-q"], cwd=directory, check=True)
            subprocess.run(
                [*git, "commit", "-q", "--allow-empty", "-m", "init"], cwd=directory, check=True
            )
            expected = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=directory,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            _, payload = _run(directory, "true")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{40,64}", expected))
        self.assertEqual(payload["head_sha"], expected)

    def test_head_sha_is_null_outside_a_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _, payload = _run(Path(temp_dir), "true")
        self.assertIsNone(payload["head_sha"])

    def test_missing_command_keeps_early_return(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, payload = _run(Path(temp_dir), "")
        self.assertEqual(result.detail, "Project test_command is not configured.")
        self.assertNotIn("duration_seconds", payload)


if __name__ == "__main__":
    unittest.main()
