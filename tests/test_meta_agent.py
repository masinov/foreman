"""Tests for the store-backed meta-agent service (no live Claude Code)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import argparse

from foreman.manager import agent as meta_agent
from foreman.cli import build_parser
from foreman.cli.parser import MANAGER_SESSION_COMMANDS
from foreman.manager.proposals import MANAGER, OPERATION_KINDS, Proposals
from foreman.domain.models import Project, Sprint, Task, Event
from foreman.store import ForemanStore


def _drain(agen) -> list[dict]:
    async def run() -> list[str]:
        chunks: list[str] = []
        async for chunk in agen:
            chunks.append(chunk)
        return chunks

    raw = asyncio.run(run())
    return [json.loads(line) for line in raw if line.strip()]


class LongOutputLineTests(unittest.TestCase):
    """A tool result is one line of the manager's output, however long."""

    def test_a_line_longer_than_asyncios_default_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Stands in for Claude Code: one assistant line holding 300,000
            # characters (a large file read back), then the result line.
            fake = Path(tmp) / "claude"
            fake.write_text(
                f"#!{sys.executable}\n"
                "import json, sys\n"
                "sys.stdin.read()\n"
                "text = 'x' * 300_000\n"
                "print(json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': text}]}}))\n"
                "print(json.dumps({'type': 'result', 'session_id': 's-1'}))\n"
            )
            fake.chmod(0o755)

            async def run() -> list[dict]:
                return [
                    event
                    async for event in meta_agent._run_claude(
                        None, "hello", repo_path=tmp, executable=str(fake), model=None
                    )
                ]

            events = asyncio.run(run())
        self.assertEqual([event["type"] for event in events], ["text_delta", "session"])
        self.assertEqual(len(events[0]["text"]), 300_000)


class ProcessEndsWithTheReadingTests(unittest.TestCase):
    """A manager process never outlives the turn that started it."""

    def test_the_process_is_killed_when_the_reading_stops_early(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "pid"
            # Says one thing, then keeps working as a real session would.
            fake = Path(tmp) / "claude"
            fake.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys, time\n"
                "sys.stdin.read()\n"
                f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
                "print(json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'hi'}]}}), flush=True)\n"
                "time.sleep(60)\n"
            )
            fake.chmod(0o755)

            async def run() -> None:
                stream = meta_agent._run_claude(None, "hello", repo_path=tmp, executable=str(fake), model=None)
                first = await stream.__anext__()
                self.assertEqual(first["type"], "text_delta")
                # The turn stops reading: a failure, or the request cancelled.
                await stream.aclose()

            asyncio.run(run())
            pid = int(pid_file.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


class ReplyInProgressStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = ForemanStore(Path(tmp.name) / "foreman.db")
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.store.save_project(Project(id="p", name="P", repo_path=tmp.name, workflow_id="development"))

    def test_one_message_is_answered_at_a_time(self) -> None:
        started = self.store.start_meta_reply("p", text="first")
        self.assertIsNotNone(started)
        self.assertTrue(self.store.meta_reply_in_progress("p"))
        self.assertIsNone(self.store.start_meta_reply("p", text="second"))
        turns, _ = self.store.list_meta_turns("p")
        self.assertEqual([(t["role"], t["text"]) for t in turns], [("user", "first"), ("assistant", "")])
        self.assertEqual(turns[1]["tool_uses"], [{"in_progress": True}])

        self.store.update_meta_turn(started[1], text="done", tool_uses=[])
        self.assertFalse(self.store.meta_reply_in_progress("p"))
        self.assertIsNotNone(self.store.start_meta_reply("p", text="second"))

    def test_a_reply_a_stopped_dashboard_left_is_marked_cut_short(self) -> None:
        _, reply = self.store.start_meta_reply("p", text="first")
        self.store.update_meta_turn(reply, text="half", tool_uses=[{"name": "Bash"}, {"in_progress": True}])

        self.assertEqual(self.store.close_unfinished_meta_replies(), 1)

        turns, _ = self.store.list_meta_turns("p")
        self.assertEqual(turns[1]["tool_uses"], [{"name": "Bash"}, {"interrupted": True}])
        self.assertFalse(self.store.meta_reply_in_progress("p"))


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
        from foreman.domain.models import Run

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
        self.assertGreater(len(command_lines), 15)

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

    def test_contract_lists_only_commands_a_manager_session_may_run(self) -> None:
        """ADR-0022: the contract offers reads and `proposal create`, nothing that would be refused."""

        project = Project(
            id="proj-1", name="Demo", repo_path="/tmp/demo", workflow_id="development"
        )
        contract = meta_agent.build_operating_contract(project)
        top_level = _subparser_choices(build_parser())
        for line in contract.splitlines():
            tokens = line.strip().split()
            if len(tokens) < 2 or tokens[0] != "foreman":
                continue
            path = tokens[1]
            if _subparser_choices(top_level[path]):
                path = f"{path} {tokens[2]}"
            self.assertIn(path, MANAGER_SESSION_COMMANDS, line)
        self.assertIn("foreman proposal create proj-1 --json .foreman/manager/<name>.json", contract)
        self.assertNotIn("<<", contract)
        self.assertIn("nothing you propose", contract.lower().replace("\n", " "))
        for kind in OPERATION_KINDS:
            self.assertIn(kind, contract)

    def test_contract_uses_corrected_history_syntax(self) -> None:
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
        async def _run_claude(session_id, prompt, *, repo_path, executable, model, env=None):
            if captured is not None:
                captured["session_id"] = session_id
                captured["prompt"] = prompt
                captured["model"] = model
                captured["env"] = env
            for event in events:
                if callable(event):
                    event = event(env)
                    if event is None:
                        continue
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

    def test_page_context_reaches_the_prompt_but_not_the_transcript(self) -> None:
        captured: dict = {}
        meta_agent._run_claude = self._fake_run(
            [{"type": "text_delta", "text": "ok"}], captured=captured
        )
        context = meta_agent.describe_page_context(
            {"page": "FOR-14", "task_id": "task-14", "ignored": "x"}
        )
        with self._open() as store:
            project = store.get_project("proj-1")
            _drain(
                meta_agent.process_message(
                    "proj-1", "what is this?", store=store, project=project,
                    page_context=context,
                )
            )
        self.assertIn("the page: FOR-14; task id: task-14", captured["prompt"])
        self.assertNotIn("ignored", captured["prompt"])
        with self._open() as store:
            turns, _ = store.list_meta_turns("proj-1")
            self.assertEqual(turns[0]["text"], "what is this?")

    def test_describe_page_context_validates(self) -> None:
        self.assertIsNone(meta_agent.describe_page_context(None))
        self.assertIsNone(meta_agent.describe_page_context({"page": "  "}))
        with self.assertRaises(ValueError):
            meta_agent.describe_page_context("Sprints")
        with self.assertRaises(ValueError):
            meta_agent.describe_page_context({"page": 3})

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

    def test_the_reply_is_stored_while_it_is_written(self) -> None:
        seen: list = []

        def look(_env):
            # Someone else reads the conversation while the manager works.
            with self._open() as other:
                turns, _ = other.list_meta_turns("proj-1")
            seen.append((turns[-1]["text"], turns[-1]["tool_uses"]))
            return None

        meta_agent._run_claude = self._fake_run([look, {"type": "text_delta", "text": "Hello"}, look])
        with self._open() as store:
            project = store.get_project("proj-1")
            events = _drain(meta_agent.process_message("proj-1", "hi", store=store, project=project))

        # The stream first names the stored turns it is writing.
        with self._open() as store:
            turns, _ = store.list_meta_turns("proj-1")
        self.assertEqual(
            events[0], {"type": "turn", "message_id": turns[0]["id"], "reply_id": turns[1]["id"]}
        )
        self.assertEqual(seen[0], ("", [{"in_progress": True}]))
        self.assertEqual(seen[1], ("Hello", [{"in_progress": True}]))
        with self._open() as store:
            turns, _ = store.list_meta_turns("proj-1")
            self.assertEqual((turns[-1]["text"], turns[-1]["tool_uses"]), ("Hello", []))

    def test_a_message_while_a_reply_is_in_progress_is_refused(self) -> None:
        with self._open() as store:
            store.start_meta_reply("proj-1", text="first")
            project = store.get_project("proj-1")
            events = _drain(meta_agent.process_message("proj-1", "second", store=store, project=project))
            turns, _ = store.list_meta_turns("proj-1")
        self.assertEqual(events, [{"type": "error", "message": meta_agent.MANAGER_BUSY}])
        self.assertEqual([t["text"] for t in turns], ["first", ""])

    def test_clearing_declines_the_proposals_still_waiting(self) -> None:
        with self._open() as store:
            store.save_sprint(Sprint(id="s", project_id="proj-1", title="S", status="planned"))
            project = store.get_project("proj-1")
            proposal = Proposals(store, via="cli").create(
                project,
                reason="Because.",
                operations=[{"kind": "edit_sprint", "sprint_id": "s", "goal": "G."}],
                proposed_by=MANAGER,
            )
            store.start_meta_reply("proj-1", text="first")

            declined = meta_agent.clear_session(store, "proj-1", via="dashboard", actor="ada")

            self.assertEqual(declined, [proposal.id])
            stored = store.get_proposal(proposal.id)
            self.assertEqual((stored.state, stored.decided_by), ("declined", "ada"))
            self.assertEqual(stored.outcome["sentence"], meta_agent.CLEARED_PROPOSAL)
            self.assertEqual(store.list_meta_turns("proj-1")[0], [])

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


class ManagerProposalStreamTests(ProcessMessagePersistenceTests):
    """ADR-0022: the session is marked, and a proposal made in a turn is announced."""

    def _propose(self, env):
        """What `foreman proposal create` does inside the session, from its environment."""

        with self._open() as store:
            project = store.get_project("proj-1")
            store.save_sprint(
                Sprint(id="s1", project_id="proj-1", title="Sprint 1", status="planned")
            )
            proposal = Proposals(store, via="cli").create(
                project,
                reason="Start the planned sprint.",
                operations=[{"kind": "activate_sprint", "sprint_id": "s1"}],
                proposed_by=MANAGER,
                turn_id=env["FOREMAN_MANAGER_TURN"],
            )
        self.proposal_id = proposal.id
        return {"type": "tool_use", "name": "Bash", "input": {}}

    def test_the_session_is_marked_and_the_proposal_is_announced_and_kept(self) -> None:
        captured: dict = {}
        meta_agent._run_claude = self._fake_run(
            [
                {"type": "text_delta", "text": "I propose starting it."},
                self._propose,
                {"type": "session", "session_id": "sess-1"},
            ],
            captured=captured,
        )
        with self._open() as store:
            project = store.get_project("proj-1")
            events = _drain(
                meta_agent.process_message("proj-1", "start it", store=store, project=project)
            )
            turns, _ = store.list_meta_turns("proj-1")
            proposal = store.get_proposal(self.proposal_id)

        env = captured["env"]
        self.assertEqual(env["FOREMAN_MANAGER_SESSION"], "proj-1")
        self.assertEqual(env["FOREMAN_MANAGER_TURN"], turns[0]["id"])
        self.assertEqual(env["FOREMAN_DB"], str(self.db_path))
        parsed = events
        self.assertIn({"type": "proposal", "proposal_id": self.proposal_id}, parsed)
        self.assertEqual(
            [event["type"] for event in parsed], ["turn", "text_delta", "tool_use", "proposal", "done"]
        )
        self.assertIn({"proposal_id": self.proposal_id}, turns[1]["tool_uses"])
        self.assertEqual(proposal.state, "proposed")
        self.assertEqual(proposal.turn_id, turns[0]["id"])

    def test_a_turn_without_a_proposal_announces_none(self) -> None:
        meta_agent._run_claude = self._fake_run([{"type": "text_delta", "text": "Nothing to change."}])
        with self._open() as store:
            project = store.get_project("proj-1")
            events = _drain(meta_agent.process_message("proj-1", "hi", store=store, project=project))
        self.assertNotIn("proposal", [event["type"] for event in events])

    def test_the_real_runner_passes_the_marks_to_the_process(self) -> None:
        """`_run_claude` hands its env to the Claude Code process it starts."""

        script = Path(self.tmp.name) / "fake-claude"
        script.write_text(
            "#!/bin/sh\ncat >/dev/null\n"
            'printf \'{"type":"assistant","message":{"content":[{"type":"text","text":"%s"}]}}\\n\' '
            '"$FOREMAN_MANAGER_SESSION/$FOREMAN_MANAGER_TURN"\n'
        )
        script.chmod(0o755)

        async def run():
            out = []
            async for event in self._orig_run(
                None,
                "prompt",
                repo_path=self.tmp.name,
                executable=str(script),
                model=None,
                env={"FOREMAN_MANAGER_SESSION": "proj-1", "FOREMAN_MANAGER_TURN": "turn-1"},
            ):
                out.append(event)
            return out

        events = asyncio.run(run())
        self.assertEqual(events, [{"type": "text_delta", "text": "proj-1/turn-1"}])

    def test_the_session_is_started_confined_to_reading_and_proposing(self) -> None:
        """FOR-42: what the Claude Code process is started with, from a fake
        executable that records its arguments and environment."""

        record = Path(self.tmp.name) / "record.json"
        script = Path(self.tmp.name) / "fake-claude"
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "sys.stdin.read()\n"
            f"json.dump({{'argv': sys.argv[1:], 'env': dict(os.environ)}}, open({str(record)!r}, 'w'))\n"
            'print(json.dumps({"type": "result", "session_id": "s-1"}))\n'
        )
        script.chmod(0o755)
        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()

        async def run():
            async for _ in self._orig_run(
                "earlier-session",
                "prompt",
                repo_path=str(repo),
                executable=str(script),
                model="some-model",
                env={"FOREMAN_MANAGER_SESSION": "proj-1", "FOREMAN_MANAGER_TURN": "turn-1"},
            ):
                pass

        secrets = {"FOREMAN_DASHBOARD_TOKEN": "dashboard-secret", "GITHUB_TOKEN": "forge-secret"}
        with patch.dict(os.environ, secrets):
            asyncio.run(run())

        seen = json.loads(record.read_text())
        argv = seen["argv"]

        def value(flag: str) -> str:
            return argv[argv.index(flag) + 1]

        # The permission rules are what confine it; bypassPermissions ignores them.
        self.assertEqual(value("--permission-mode"), "default")
        self.assertNotIn("bypassPermissions", argv)
        self.assertEqual(value("--tools"), "Read,Grep,Glob,Bash,Write")
        self.assertEqual(
            value("--allowed-tools"),
            "Read,Grep,Glob,Bash(foreman:*),Edit(.foreman/manager/**)",
        )
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(value("--model"), "some-model")
        self.assertEqual(value("--resume"), "earlier-session")
        # It is told who it is, and not given the dashboard's secrets.
        self.assertEqual(seen["env"]["FOREMAN_MANAGER_SESSION"], "proj-1")
        for name in secrets:
            self.assertNotIn(name, seen["env"])
        # The one folder it may write to exists.
        self.assertTrue((repo / ".foreman" / "manager").is_dir())

    def test_the_session_is_not_given_the_operators_memory(self) -> None:
        environment = meta_agent.manager_process_env({"FOREMAN_MANAGER_SESSION": "proj-1"})
        self.assertEqual(environment["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")

    def test_this_installations_foreman_is_first_on_the_sessions_path(self) -> None:
        import sys

        environment = meta_agent.manager_process_env({"FOREMAN_MANAGER_SESSION": "proj-1"})
        bin_dir = Path(sys.executable).parent
        if (bin_dir / "foreman").exists():
            self.assertEqual(environment["PATH"].split(os.pathsep)[0], str(bin_dir))

    def test_a_later_turn_is_reminded_how_to_propose(self) -> None:
        captured: list[dict] = []

        async def _run_claude(session_id, prompt, *, repo_path, executable, model, env=None):
            captured.append({"prompt": prompt})
            yield {"type": "session", "session_id": "s-1"}
            yield {"type": "text_delta", "text": "ok"}

        meta_agent._run_claude = _run_claude
        with self._open() as store:
            project = store.get_project("proj-1")
            _drain(meta_agent.process_message("proj-1", "first", store=store, project=project))
            _drain(meta_agent.process_message("proj-1", "second", store=store, project=project))

        first, second = (entry["prompt"] for entry in captured)
        self.assertIn("## OPERATING CONTRACT", first)
        self.assertNotIn("## OPERATING CONTRACT", second)
        self.assertIn("How to propose", second)
        self.assertIn(".foreman/manager/", second)

