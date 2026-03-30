"""Tests for repo scaffold generation helpers."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from foreman.scaffold import scaffold_repository


class ScaffoldGenerationTests(unittest.TestCase):
    """Verify the generated repo scaffold matches the current spec slice."""

    def create_repo_path(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / "repo"

    def test_scaffold_repository_creates_minimal_files_and_renders_agents(self) -> None:
        repo_path = self.create_repo_path()
        result = scaffold_repository(
            repo_path,
            project_name="Sample Project",
            spec_path="docs/spec.md",
            default_branch="main",
            test_command="./venv/bin/python -m unittest discover -s tests",
        )

        self.assertEqual(
            [(artifact.path, artifact.action) for artifact in result.artifacts],
            [
                ("docs/adr/", "created"),
                (".foreman/", "created"),
                (".gitignore", "created"),
                ("AGENTS.md", "created"),
            ],
        )
        self.assertTrue((repo_path / "docs" / "adr").is_dir())
        self.assertTrue((repo_path / ".foreman").is_dir())
        self.assertEqual(
            (repo_path / ".gitignore").read_text(encoding="utf-8"),
            ".foreman/\n.foreman.db\n",
        )

        agents_text = (repo_path / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Project: Sample Project", agents_text)
        self.assertIn("Spec: docs/spec.md", agents_text)
        self.assertIn("Never work directly on `main`", agents_text)
        self.assertIn("./venv/bin/python -m unittest discover -s tests", agents_text)
        self.assertIn("FOREMAN_SIGNAL", agents_text)
        self.assertIn("TASK_COMPLETE", agents_text)
        self.assertIn("Never edit files under `.foreman/`", agents_text)

    def test_scaffold_repository_is_idempotent_and_preserves_existing_agents(self) -> None:
        repo_path = self.create_repo_path()
        repo_path.mkdir(parents=True)
        (repo_path / "AGENTS.md").write_text("# Custom Instructions\n", encoding="utf-8")
        (repo_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

        first = scaffold_repository(
            repo_path,
            project_name="Sample Project",
            spec_path="docs/spec.md",
            default_branch="main",
            test_command="./venv/bin/python -m unittest discover -s tests",
        )
        second = scaffold_repository(
            repo_path,
            project_name="Sample Project",
            spec_path="docs/spec.md",
            default_branch="main",
            test_command="./venv/bin/python -m unittest discover -s tests",
        )

        self.assertEqual((repo_path / "AGENTS.md").read_text(encoding="utf-8"), "# Custom Instructions\n")
        self.assertEqual(
            (repo_path / ".gitignore").read_text(encoding="utf-8"),
            "node_modules/\n.foreman/\n.foreman.db\n",
        )
        self.assertEqual(
            [(artifact.path, artifact.action) for artifact in first.artifacts],
            [
                ("docs/adr/", "created"),
                (".foreman/", "created"),
                (".gitignore", "updated"),
                ("AGENTS.md", "unchanged"),
            ],
        )
        self.assertEqual(
            [(artifact.path, artifact.action) for artifact in second.artifacts],
            [
                ("docs/adr/", "unchanged"),
                (".foreman/", "unchanged"),
                (".gitignore", "unchanged"),
                ("AGENTS.md", "unchanged"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
