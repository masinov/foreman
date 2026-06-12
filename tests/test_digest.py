"""Unit coverage for the supervision attention digest."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from foreman.digest import build_attention_digest
from foreman.models import CompletionEvidence, Project, Run, Sprint, Task
from foreman.store import ForemanStore


class AttentionDigestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ForemanStore(Path(self.tmp.name) / "foreman.db")
        self.store.initialize()
        self.addCleanup(self.store.close)

    def _seed(self, autonomy: str = "supervised") -> Project:
        project = Project(
            id="p1", name="Demo", repo_path=self.tmp.name,
            workflow_id="development", autonomy_level=autonomy,
        )
        self.store.save_project(project)
        self.store.save_sprint(
            Sprint(id="sp", project_id="p1", title="S", status="active")
        )
        task = Task(
            id="t1", sprint_id="sp", project_id="p1", title="Build feature",
            status="blocked", blocked_reason="dependency X is missing",
            workflow_current_step="develop", step_visit_counts={"develop": 2},
        )
        task.completion_evidence = CompletionEvidence(
            task_id="t1", task_title="Build feature", acceptance_criteria="c",
            verdict="insufficient", proof_status="failed", score=30.0,
            judged_by="heuristic", failure_reasons=("Tests failed.",),
        )
        self.store.save_task(task)
        self.store.save_run(
            Run(
                id="r1", task_id="t1", project_id="p1", role_id="developer",
                workflow_step="develop", agent_backend="claude",
                status="completed", outcome="blocked", outcome_detail="boom",
            )
        )
        return project

    def test_digest_contains_trigger_task_and_evidence(self) -> None:
        project = self._seed()
        digest = build_attention_digest(
            self.store, project, trigger="task_blocked", task_id="t1"
        )
        self.assertIn("ATTENTION NEEDED", digest)
        self.assertIn("Trigger: task_blocked", digest)
        self.assertIn("dependency X is missing", digest)
        self.assertIn("verdict=insufficient", digest)
        self.assertIn("Tests failed.", digest)
        self.assertIn("develop=2", digest)

    def test_directed_project_forbids_mutation(self) -> None:
        project = self._seed(autonomy="directed")
        digest = build_attention_digest(
            self.store, project, trigger="task_blocked", task_id="t1"
        )
        self.assertIn("DIRECTED mode", digest)
        self.assertIn("may NOT run state-mutating", digest)

    def test_supervised_project_lists_cli_verbs(self) -> None:
        project = self._seed(autonomy="supervised")
        digest = build_attention_digest(
            self.store, project, trigger="task_blocked", task_id="t1"
        )
        self.assertIn("foreman task override", digest)
        self.assertNotIn("DIRECTED mode", digest)

    def test_missing_task_is_tolerated(self) -> None:
        project = self._seed()
        digest = build_attention_digest(
            self.store, project, trigger="sprint_resolved", task_id="ghost"
        )
        self.assertIn("not found", digest)


if __name__ == "__main__":
    unittest.main()
