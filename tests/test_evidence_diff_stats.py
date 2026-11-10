"""Completion-evidence diff stats come from ``git diff --numstat -z``."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from foreman.orchestrator import ForemanOrchestrator


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


class EvidenceDiffStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "T")
        _git(self.repo, "config", "commit.gpgsign", "false")
        (self.repo / "gone.txt").write_text("a\nb\nc\nd\n")
        (self.repo / "old name.txt").write_text("".join(f"line {n}\n" for n in range(20)))
        (self.repo / "bin.dat").write_bytes(b"\x00\x01\x02")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "base")
        _git(self.repo, "branch", "-M", "main")
        _git(self.repo, "checkout", "-q", "-b", "feature")

    def _stats(self) -> tuple[tuple[str, ...], int, str]:
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "work")
        orch = ForemanOrchestrator.__new__(ForemanOrchestrator)
        text = orch._safe_branch_diff(str(self.repo), "main", "feature")
        return orch._parse_diff_stats(text)

    def test_all_cases_through_evidence_code_path(self) -> None:
        spaced = self.repo / "dir with space" / "my file.txt"
        spaced.parent.mkdir()
        spaced.write_text("one\ntwo\n")
        deep = self.repo.joinpath(*(["very_long_directory_name"] * 5)) / "leaf.txt"
        deep.parent.mkdir(parents=True)
        deep.write_text("x\n")
        (self.repo / "bin.dat").write_bytes(b"\x00\x09\x08\x07")
        (self.repo / "old name.txt").rename(self.repo / "new name.txt")
        (self.repo / "gone.txt").write_text("a\n")  # 3 deletions, 0 additions

        files, count, summary = self._stats()

        deep_rel = deep.relative_to(self.repo).as_posix()
        self.assertGreater(len(deep_rel), 100)
        self.assertIn("dir with space/my file.txt", files)
        self.assertIn(deep_rel, files)
        self.assertIn("bin.dat", files)
        self.assertIn("new name.txt", files)
        self.assertNotIn("old name.txt", files)
        self.assertIn("gone.txt", files)
        self.assertEqual(count, len(files))

        numstat = _git(self.repo, "diff", "--numstat", "main...feature")
        added = deleted = 0
        for line in numstat.splitlines():
            a, d, _ = line.split("\t", 2)
            added += int(a) if a.isdigit() else 0
            deleted += int(d) if d.isdigit() else 0
        self.assertGreaterEqual(deleted, 3)
        self.assertEqual(summary, f"{len(files)} file(s), +{added}, -{deleted}")

    def test_deletion_only_file_counts_deleted(self) -> None:
        (self.repo / "gone.txt").write_text("a\n")
        files, _, summary = self._stats()
        self.assertEqual(files, ("gone.txt",))
        self.assertEqual(summary, "1 file(s), +0, -3")

    def test_empty_output(self) -> None:
        orch = ForemanOrchestrator.__new__(ForemanOrchestrator)
        self.assertEqual(orch._parse_diff_stats(""), ((), 0, "0 file(s), +0, -0"))


if __name__ == "__main__":
    unittest.main()
