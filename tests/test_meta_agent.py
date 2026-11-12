"""Tests for the store-backed meta-agent service (no live subprocess)."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import argparse

from foreman import meta_agent
from foreman.cli import build_parser
from foreman.models import Project, Sprint, Task, Event
from foreman.store import ForemanStore


def _drain(agen) -> list[dict]:
    async def run() -> list[str]:
        chunks: list[str] = []
        async for chunk in agen:
            chunks.append(chunk)
        return chunks

    raw = asyncio.run(run())
    return [json.loads(line) for line in raw if line.strip()]


class StateHeaderTests(unittest.TestCase):
    """build_state_header pins a compact, fixed format with truncation rules."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ForemanStore(Path(self.tmp.name) / "foreman.db")
        self.store.initialize()
        self.addCleanup(self.store.close)
        self.project = Project(
            id="proj-1",
            name="Demo",
            repo_path=self.tmp.name,
            workflow_id="development",
        )
        self.store.save_project(self.project)

    def test_header_has_authority_disclaimer_and_project_line(self) -> None:
        header = meta_agent.build_state_header(self.store, self.project)
        self.assertIn("regenerated each turn", header)
        self.assertIn("trust it over your memory", header)
        self.assertIn("Project: Demo (proj-1)", header)
        self.assertIn("Workflow: development", header)

    def test_active_sprint_task_table_truncates_blocked_reason(self) -> None:
        self.store.save_sprint(
            Sprint(id="sp-1", project_id="proj-1", title="S1", status="active")
        )
        long_reason = "x" * 200
        self.store.save_task(
            Task(
                id="task-1",
                sprint_id="sp-1",
                project_id="proj-1",
                title="Build feature",
                status="blocked",
                blocked_reason=long_reason,
            )
        )
        header = meta_agent.build_state_header(self.store, self.project)
        self.assertIn("Active sprint task table", header)
        self.assertIn(
            "id | status | type | title | assigned_role | blocked_reason", header
        )
        self.assertNotIn("model_override", header)
        self.assertIn("task-1 | blocked | feature | Build feature", header)
        # blocked_reason is truncated to <= 80 chars (plus ellipsis), never full.
        self.assertNotIn(long_reason, header)
        self.assertIn("…", header)

    def test_noteworthy_events_filtered_and_capped_at_five(self) -> None:
        run_id = "run-x"
        # Create a real run so the FK on events is satisfied.
        self.store.save_sprint(
            Sprint(id="sp-2", project_id="proj-1", title="S2", status="active")
        )
        self.store.save_task(
            Task(id="task-2", sprint_id="sp-2", project_id="proj-1", title="T")
        )
        from foreman.models import Run

        self.store.save_run(
            Run(
                id=run_id,
                task_id="task-2",
                project_id="proj-1",
                role_id="developer",
                workflow_step="develop",
                agent_backend="claude",
            )
        )
        for i in range(8):
            self.store.save_event(
                Event(
                    id=f"ev-blocked-{i}",
                    run_id=run_id,
                    task_id="task-2",
                    project_id="proj-1",
                    event_type="engine.task_blocked",
                    timestamp=f"2026-06-12T00:00:0{i}Z",
                )
            )
        # A non-noteworthy event should be excluded.
        self.store.save_event(
            Event(
                id="ev-noise",
                run_id=run_id,
                task_id="task-2",
                project_id="proj-1",
                event_type="agent.text",
                timestamp="2026-06-12T01:00:00Z",
            )
        )
        header = meta_agent.build_state_header(self.store, self.project)
        self.assertEqual(header.count("engine.task_blocked"), 5)
        self.assertNotIn("agent.text", header)

    def test_backlog_block_names_filed_and_accepted_capped(self) -> None:
        backlog = self.store.ensure_backlog("proj-1", created_at="2026-06-12T00:00:00Z")
        for i in range(7):
            self.store.save_task(
                Task(
                    id=f"filed-{i}",
                    sprint_id=backlog.id,
                    project_id="proj-1",
                    title=f"Filed work {i}",
                    status="triage",
                )
            )
        self.store.save_task(
            Task(
                id="acc-1",
                sprint_id=backlog.id,
                project_id="proj-1",
                title="Accepted work",
                status="todo",
            )
        )
        self.store.save_task(
            Task(
                id="dec-1",
                sprint_id=backlog.id,
                project_id="proj-1",
                title="Declined work",
                status="declined",
            )
        )
        header = meta_agent.build_state_header(self.store, self.project)
        self.assertIn("### Backlog", header)
        self.assertIn("filed=7, accepted=1, declined=1", header)
        self.assertIn("Filed (showing 5 of 7):", header)
        self.assertIn("Accepted (showing 1 of 1):", header)
        self.assertIn("- acc-1 | feature | Accepted work", header)
        self.assertEqual(header.count("- filed-"), 5)
        self.assertNotIn("dec-1", header)
        # The backlog is not a sprint row in the sprint list.
        sprint_block = header.split("### Backlog")[0]
        self.assertNotIn(backlog.id, sprint_block)

    def test_backlog_block_empty_when_no_backlog(self) -> None:
        header = meta_agent.build_state_header(self.store, self.project)
        self.assertIn("filed=0, accepted=0, declined=0", header)
        self.assertNotIn("Filed (showing", header)


def _subparser_choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


class OperatingContractDriftTests(unittest.TestCase):
    """Every `foreman ...` line in the contract must name a real CLI command."""

    def test_every_contract_command_is_accepted_by_cli_parser(self) -> None:
        project = Project(
            id="proj-1",
            name="Demo",
            repo_path="/tmp/demo",
            workflow_id="development",
        )
        contract = meta_agent.build_operating_contract(project)
        command_lines = [
            line.strip()
            for line in contract.splitlines()
            if line.strip().startswith("foreman ")
        ]
        self.assertGreater(len(command_lines), 20)

        top_level = _subparser_choices(build_parser())
        for line in command_lines:
            tokens = line.split()
            self.assertGreaterEqual(len(tokens), 2, line)
            command = tokens[1]
            self.assertIn(command, top_level, f"unknown command in contract: {line}")
            sub_choices = _subparser_choices(top_level[command])
            if sub_choices:
                self.assertGreaterEqual(len(tokens), 3, f"missing subcommand: {line}")
                subcommand = tokens[2]
                self.assertIn(
                    subcommand,
                    sub_choices,
                    f"unknown subcommand in contract: {line}",
                )

    def test_contract_lists_every_backlog_command(self) -> None:
        project = Project(
            id="proj-1", name="Demo", repo_path="/tmp/demo", workflow_id="development"
        )
        contract = meta_agent.build_operating_contract(project)
        backlog = _subparser_choices(build_parser())["backlog"]
        for sub in _subparser_choices(backlog):
            self.assertIn(f"foreman backlog {sub} ", contract + " ")

    def test_contract_uses_corrected_history_and_override_syntax(self) -> None:
        project = Project(
            id="proj-1",
            name="Demo",
            repo_path="/tmp/demo",
            workflow_id="development",
        )
        contract = meta_agent.build_operating_contract(project)
        self.assertNotIn("foreman history proj-1", contract)
        self.assertIn("foreman history <task-id>", contract)
        self.assertNotIn("--model", contract)
        self.assertIn("foreman task override <task-id> --step <step>=<model>", contract)


class ProcessMessagePersistenceTests(unittest.TestCase):
    """process_message persists both turns and survives a stream interruption."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "foreman.db"
        store = ForemanStore(self.db_path)
        store.initialize()
        store.save_project(
            Project(
                id="proj-1",
                name="Demo",
                repo_path=self.tmp.name,
                workflow_id="development",
            )
        )
        store.close()
        # Make shutil.which always find the fake executable.
        self._orig_which = meta_agent.shutil.which
        meta_agent.shutil.which = lambda _exe: "/usr/bin/claude"
        self.addCleanup(lambda: setattr(meta_agent.shutil, "which", self._orig_which))
        self._orig_run = meta_agent._run_claude
        self.addCleanup(lambda: setattr(meta_agent, "_run_claude", self._orig_run))

    def _open(self) -> ForemanStore:
        store = ForemanStore(self.db_path)
        store.initialize()
        return store

    def _fake_run(self, events, *, captured=None):
        async def _run_claude(session_id, prompt, *, repo_path, executable, model):
            if captured is not None:
                captured["session_id"] = session_id
                captured["prompt"] = prompt
                captured["model"] = model
            for event in events:
                yield event

        return _run_claude

    def test_successful_turn_persists_user_and_assistant(self) -> None:
        captured: dict = {}
        meta_agent._run_claude = self._fake_run(
            [
                {"type": "text_delta", "text": "Hello "},
                {"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}},
                {"type": "text_delta", "text": "world"},
                {"type": "session", "session_id": "sess-1"},
            ],
            captured=captured,
        )
        with self._open() as store:
            project = store.get_project("proj-1")
            events = _drain(
                meta_agent.process_message(
                    "proj-1", "hi there", store=store, project=project
                )
            )
        # The first turn injects the operating contract and a state header.
        self.assertIn("OPERATING CONTRACT", captured["prompt"])
        self.assertIn("FOREMAN STATE", captured["prompt"])
        self.assertIsNone(captured["session_id"])
        # Done event carries the new session id.
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["session_id"], "sess-1")

        with self._open() as store:
            turns, has_more = store.list_meta_turns("proj-1")
            self.assertEqual([t["role"] for t in turns], ["user", "assistant"])
            self.assertEqual(turns[0]["text"], "hi there")
            self.assertEqual(turns[1]["text"], "Hello world")
            self.assertEqual(turns[1]["tool_uses"], [{"name": "Bash", "input": {"cmd": "ls"}}])
            self.assertEqual(store.get_meta_session("proj-1"), "sess-1")

    def test_second_turn_resumes_session_without_contract(self) -> None:
        with self._open() as store:
            store.save_meta_session("proj-1", "sess-existing")
        captured: dict = {}
        meta_agent._run_claude = self._fake_run(
            [{"type": "text_delta", "text": "ok"}, {"type": "session", "session_id": "sess-existing"}],
            captured=captured,
        )
        with self._open() as store:
            project = store.get_project("proj-1")
            _drain(
                meta_agent.process_message(
                    "proj-1", "again", store=store, project=project
                )
            )
        self.assertEqual(captured["session_id"], "sess-existing")
        self.assertNotIn("OPERATING CONTRACT", captured["prompt"])
        self.assertIn("FOREMAN STATE", captured["prompt"])  # header still present

    def test_interrupted_stream_still_persists_assistant_turn(self) -> None:
        meta_agent._run_claude = self._fake_run(
            [
                {"type": "text_delta", "text": "partial"},
                {"type": "error", "message": "boom"},
            ]
        )
        with self._open() as store:
            project = store.get_project("proj-1")
            events = _drain(
                meta_agent.process_message(
                    "proj-1", "do it", store=store, project=project
                )
            )
        self.assertEqual(events[-1]["type"], "error")
        with self._open() as store:
            turns, _ = store.list_meta_turns("proj-1")
            self.assertEqual([t["role"] for t in turns], ["user", "assistant"])
            self.assertEqual(turns[1]["text"], "partial")
            self.assertIn({"interrupted": True}, turns[1]["tool_uses"])

    def test_model_setting_passed_to_backend(self) -> None:
        with self._open() as store:
            project = store.get_project("proj-1")
            project.settings = {"meta_agent_model": "opus-frontier"}
            store.save_project(project)
        captured: dict = {}
        meta_agent._run_claude = self._fake_run(
            [{"type": "session", "session_id": "s"}], captured=captured
        )
        with self._open() as store:
            project = store.get_project("proj-1")
            _drain(
                meta_agent.process_message(
                    "proj-1", "go", store=store, project=project
                )
            )
        self.assertEqual(captured["model"], "opus-frontier")


if __name__ == "__main__":
    unittest.main()
