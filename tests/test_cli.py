"""Smoke tests for the bootstrap Foreman CLI."""

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_BIN = REPO_ROOT / "venv" / "bin"
PIP = VENV_BIN / "pip"
FOREMAN = VENV_BIN / "foreman"


class ForemanCLISmokeTests(unittest.TestCase):
    """Verify that the initial CLI shell is wired and runnable."""

    @classmethod
    def setUpClass(cls) -> None:
        install_result = subprocess.run(
            [
                str(PIP),
                "install",
                "-e",
                ".",
                "--no-build-isolation",
                "--no-deps",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if install_result.returncode != 0:
            raise AssertionError(
                "Editable install failed:\n"
                f"stdout:\n{install_result.stdout}\n"
                f"stderr:\n{install_result.stderr}"
            )
        if not FOREMAN.is_file():
            raise AssertionError(f"Console entrypoint was not created at {FOREMAN}")

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(FOREMAN), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_help_lists_bootstrap_commands(self) -> None:
        result = self.run_cli("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: foreman", result.stdout)
        self.assertIn("projects", result.stdout)
        self.assertIn("status", result.stdout)
        self.assertIn("init", result.stdout)

    def test_projects_command_reports_empty_bootstrap_state(self) -> None:
        result = self.run_cli("projects")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Projects", result.stdout)
        self.assertIn("No projects are tracked yet.", result.stdout)
        self.assertIn("SQLite-backed runtime state lands in the next sprint slice.", result.stdout)

    def test_status_command_reports_empty_bootstrap_state(self) -> None:
        result = self.run_cli("status")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Status", result.stdout)
        self.assertIn("No active projects or sprints.", result.stdout)
        self.assertIn("Next slice: implement the SQLite model and store baseline.", result.stdout)


if __name__ == "__main__":
    unittest.main()
