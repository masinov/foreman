"""Reads before a step's first change (ADR-0041 section 6)."""

from __future__ import annotations

import unittest

from foreman.domain.step_reads import STEP_READS_EVENT, classify_command, reads_before_first_change
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.engine.results import AgentEventRecord, AgentExecutionResult
from foreman.store import ForemanStore

from engine_support import OrchestratorTestCase, ScriptedAgentExecutor


def command(text: str) -> tuple[str, dict]:
    return "agent.command", {"command": text, "cwd": "/w"}


def tool(name: str, event_type: str = "agent.tool_use", **extra) -> tuple[str, dict]:
    return event_type, {"tool": name, **extra}


class ClassifyCommandTests(unittest.TestCase):
    def test_reading_commands(self) -> None:
        for line in [
            "cat foreman/domain/models.py",
            "sed -n '120,200p' foreman/engine/agent_step.py",
            "rg -n 'TokenUsage' foreman | head -20",
            "grep -rn \"def run\" foreman/ 2>/dev/null",
            "ls -la docs/adr",
            "find . -name '*.py' -path './tests/*'",
            "head -50 README.md",
            "tail -n 30 .foreman/log.txt",
            "wc -l foreman/cli/*.py",
            "git log --oneline -5",
            "git show HEAD~1 --stat",
            "git diff main...HEAD",
            "git status --short 2>&1",
            "git grep -n outcome_numbers",
            "git -C /repo log -3",
            "cd /repo && cat a.txt | grep foo",
            "bash -lc 'rg -n foo foreman'",
        ]:
            with self.subTest(line=line):
                self.assertEqual(classify_command(line), "read")

    def test_changing_commands(self) -> None:
        for line in [
            "echo 'x' > notes.txt",
            "cat a.txt >> b.txt",
            "git diff > /tmp/change.patch",
            "sed -i 's/old/new/' foreman/a.py",
            "sed -i.bak -e 's/a/b/' f",
            "perl -pi -e 's/a/b/' foreman/a.py",
            "cat <<'EOF' > docs/note.md\nhello\nEOF",
            "git commit -m 'feat: x'",
            "git add -A && git commit -m x",
            "cat a | tee out.txt",
            "apply_patch <<'PATCH'\n*** Begin Patch\nPATCH",
            "cat a.txt && sed -i s/a/b/ a.txt",
        ]:
            with self.subTest(line=line):
                self.assertEqual(classify_command(line), "change")

    def test_other_commands_are_neither(self) -> None:
        for line in ["./venv/bin/python -m pytest tests -q", "npm test", "git add -A", "sed s/a/b/ f", "mkdir -p x", "git push"]:
            with self.subTest(line=line):
                self.assertIsNone(classify_command(line))


class ReadsBeforeFirstChangeTests(unittest.TestCase):
    def test_claude_code_tool_events(self) -> None:
        events = [
            ("agent.message", {"text": "Looking."}),
            tool("Read", "agent.file_change", path="a.py"),
            tool("Grep", pattern="x"),
            tool("Glob", pattern="*.py"),
            tool("TodoWrite"),
            tool("Edit", "agent.file_change", path="a.py"),
            tool("Read", "agent.file_change", path="b.py"),
        ]
        result = reads_before_first_change(events)
        self.assertEqual((result.reads, result.edited), (3, True))

    def test_multiedit_and_write_are_changes(self) -> None:
        self.assertEqual(reads_before_first_change([tool("Read", "agent.file_change"), tool("MultiEdit")]).reads, 1)
        self.assertTrue(reads_before_first_change([tool("Write", "agent.file_change")]).edited)

    def test_shell_only_events(self) -> None:
        events = [
            command("rg -n foo foreman"),
            command("sed -n '1,80p' foreman/a.py"),
            command("./venv/bin/python -m pytest tests/test_a.py"),
            command("cat tests/test_a.py"),
            command("cat <<'EOF' > foreman/b.py\nx = 1\nEOF"),
            command("cat foreman/b.py"),
        ]
        result = reads_before_first_change(events)
        self.assertEqual((result.reads, result.edited), (3, True))

    def test_codex_events(self) -> None:
        events = [
            command("bash -lc 'ls docs'"),
            tool("fileChange", "agent.file_change", path="a.py"),
        ]
        self.assertEqual(reads_before_first_change(events).payload(), {"reads": 1, "edited": True})
        self.assertTrue(reads_before_first_change([command("apply_patch <<'P'\nP")]).edited)

    def test_a_commit_is_a_change(self) -> None:
        result = reads_before_first_change([command("git status"), command("git commit -m x")])
        self.assertEqual((result.reads, result.edited), (1, True))

    def test_a_run_that_changed_nothing_reports_its_reads_with_no_edit(self) -> None:
        result = reads_before_first_change([tool("Read", "agent.file_change"), command("git diff main"), tool("Grep")])
        self.assertEqual(result.payload(), {"reads": 3, "edited": False})
        self.assertEqual(reads_before_first_change([]).payload(), {"reads": 0, "edited": False})


class StepReadsEngineTests(OrchestratorTestCase):
    def test_each_agent_run_records_its_reads_when_it_ends(self) -> None:
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)

        def developer(*, task, prompt, carried_output):
            self.write_text(self.work_dir(task, repo_path) / "ready.txt", "ready\n")
            self.commit_all(self.work_dir(task, repo_path), "feat: ready")
            return AgentExecutionResult(
                outcome="done",
                detail="Done.",
                status="completed",
                events=(
                    AgentEventRecord("agent.command", {"command": "rg -n foo ."}),
                    AgentEventRecord("agent.file_change", {"tool": "Read", "path": "a.py"}),
                    AgentEventRecord("agent.file_change", {"tool": "Edit", "path": "ready.txt"}),
                    AgentEventRecord("agent.file_change", {"tool": "Read", "path": "b.py"}),
                ),
            )

        def reviewer(**_):
            return AgentExecutionResult(
                outcome="approve",
                detail="APPROVE",
                events=(AgentEventRecord("agent.command", {"command": "git diff main"}),),
            )

        with ForemanStore(db_path) as store:
            store.initialize()
            project, _, task = self.seed_project(store, repo_path=repo_path)
            executor = ScriptedAgentExecutor({("developer", 1): developer, ("code_reviewer", 1): reviewer})
            ForemanOrchestrator(
                store, roles=self.roles, workflows=self.workflows, agent_executor=executor
            ).run_project(project.id)
            recorded: dict[str, list[dict]] = {}
            for run in store.list_runs(task_id=task.id):
                for event in store.list_events(run_id=run.id):
                    if event.event_type == STEP_READS_EVENT:
                        recorded.setdefault(run.workflow_step, []).append(event.payload)
        self.assertEqual(recorded["develop"][0], {"reads": 2, "edited": True})
        self.assertEqual(recorded["review"][0], {"reads": 1, "edited": False})
        # The engine's own steps are not agent runs.
        self.assertNotIn("test", recorded)


if __name__ == "__main__":
    unittest.main()
