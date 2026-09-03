"""Regression coverage for the sprint-53 output contract and signals slice.

The agent's final message is the contract: the completion marker or the
reviewer verdict must appear there. Signals are parsed once, only outside
code fences, only from roles allowed to emit them, and reviewer outcomes are
declared in the role file instead of hardcoded engine role ids.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from foreman.models import Project, Run, Sprint, Task
from foreman.orchestrator import ForemanOrchestrator, _extract_decision_output
from foreman.roles import RoleLoadError, default_roles_dir, load_role, load_roles
from foreman.runner import AgentRunConfig, ClaudeCodeRunner
from foreman.runner.base import AgentEvent
from foreman.runner.signals import extract_signal_events
from foreman.store import ForemanStore
from foreman.workflows import WorkflowLoadError, default_workflows_dir, load_workflow, load_workflows


class DecisionGrammarTests(unittest.TestCase):
    def test_accepts_decision_and_verdict_prefixes(self) -> None:
        self.assertEqual(_extract_decision_output("Looks fine.\n\n**Decision:** APPROVE"), ("approve", "APPROVE"))
        self.assertEqual(
            _extract_decision_output("Verdict — DENY: the migration test is missing"),
            ("deny", "the migration test is missing"),
        )
        self.assertEqual(
            _extract_decision_output("Final decision: STEER - split the change"),
            ("steer", "split the change"),
        )

    def test_multiple_distinct_verdicts_are_an_error_not_a_guess(self) -> None:
        outcome, detail = _extract_decision_output(
            "DENY: no tests\n\nThe options were:\n- APPROVE\n- DENY: <reason>"
        )
        self.assertEqual(outcome, "error")
        self.assertIn("Ambiguous decision", detail)
        self.assertIn("APPROVE", detail)
        self.assertIn("DENY", detail)

    def test_placeholder_option_lines_are_ignored(self) -> None:
        outcome, detail = _extract_decision_output(
            "DENY: no tests\n\nReturn one of:\n- DENY: <reason>\n- STEER: <specific corrective action>"
        )
        self.assertEqual((outcome, detail), ("deny", "no tests"))

    def test_verdict_outside_the_role_contract_is_an_error(self) -> None:
        outcome, detail = _extract_decision_output("STEER: rework it", allowed=("approve", "deny"))
        self.assertEqual(outcome, "error")
        self.assertIn("not valid for this role", detail)
        self.assertIn("APPROVE, DENY", detail)

    def test_prose_mentioning_a_verdict_word_is_not_a_verdict(self) -> None:
        self.assertEqual(_extract_decision_output("I cannot APPROVE this yet.")[0], "error")
        self.assertEqual(_extract_decision_output("APPROVED by me")[0], "error")


class SignalParsingTests(unittest.TestCase):
    def test_signals_inside_code_fences_and_quotes_are_ignored(self) -> None:
        text = textwrap.dedent(
            """
            Here is how a signal looks:
            ```
            FOREMAN_SIGNAL: {"type": "task_created", "title": "x", "description": "d", "criteria": "c"}
            ```
            > FOREMAN_SIGNAL: {"type": "blocker", "message": "quoted"}
            FOREMAN_SIGNAL: {"type": "progress", "message": "real"}
            """
        )
        cleaned, events = extract_signal_events(text)
        self.assertEqual([event.event_type for event in events], ["signal.progress"])
        self.assertIn("```", cleaned)
        self.assertIn("> FOREMAN_SIGNAL", cleaned)
        self.assertNotIn('"message": "real"', cleaned)

    def test_pretty_printed_json_spanning_lines_is_one_signal(self) -> None:
        text = textwrap.dedent(
            """
            Follow-up found.
            FOREMAN_SIGNAL: {
              "type": "task_created",
              "title": "Add index",
              "description": "events(task_id) is unindexed",
              "criteria": "query uses the index"
            }
            Done.
            """
        )
        cleaned, events = extract_signal_events(text)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "signal.task_created")
        self.assertEqual(events[0].payload["title"], "Add index")
        self.assertEqual(cleaned, "Follow-up found.\nDone.")

    def test_single_line_invalid_json_does_not_swallow_following_prose(self) -> None:
        cleaned, events = extract_signal_events("FOREMAN_SIGNAL: {not valid json}\nThis prose stays.")
        self.assertEqual(events[0].event_type, "signal.invalid")
        self.assertEqual(cleaned, "This prose stays.")


class ClaudeRunnerSignalDedupeTests(unittest.TestCase):
    def test_result_text_does_not_re_emit_signals_seen_in_assistant_blocks(self) -> None:
        signal_line = 'FOREMAN_SIGNAL: {"type": "task_created", "title": "Follow up", "description": "d", "criteria": "c"}'
        final_text = f"Implemented.\n{signal_line}\nTASK_COMPLETE"
        lines = [
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": final_text}]}}) + "\n",
            json.dumps({"type": "result", "is_error": False, "session_id": "s", "result": final_text}) + "\n",
        ]

        class _Out:
            def __init__(self) -> None:
                self._lines = list(lines)

            def readline(self) -> str:
                return self._lines.pop(0) if self._lines else ""

        class _Proc:
            def __init__(self) -> None:
                self.stdin = type("In", (), {"write": lambda s, t: None, "close": lambda s: None})()
                self.stdout = _Out()
                self.stderr = type("Err", (), {"read": lambda s: ""})()
                self.returncode = 0

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                return 0

            def kill(self):
                return None

        runner = ClaudeCodeRunner(popen_factory=lambda *a, **k: _Proc(), which=lambda n: "/usr/bin/claude", tick_seconds=0.05)
        config = AgentRunConfig(
            backend="claude_code", model=None, prompt="p", working_dir=Path("/tmp"),
            session_id=None, permission_mode="bypassPermissions",
        )
        events = list(runner.run(config))
        signals = [event for event in events if event.event_type == "signal.task_created"]
        self.assertEqual(len(signals), 1)
        self.assertEqual([e.payload["phase"] for e in events if e.event_type == "agent.message"], ["assistant", "result"])


class RoleContractTests(unittest.TestCase):
    def test_shipped_roles_declare_outcomes_and_signals(self) -> None:
        roles = load_roles(default_roles_dir())
        self.assertEqual(roles["triage_reviewer"].completion.outcomes, ("approve", "deny", "escalate"))
        self.assertEqual(roles["security_reviewer"].completion.outcomes, ("approve", "deny"))
        self.assertEqual(roles["code_reviewer"].signals, ("progress", "blocker"))
        self.assertEqual(roles["developer"].signals, ("task_started", "task_created", "progress", "blocker"))
        self.assertEqual(roles["developer"].completion.outcomes, ("done", "blocked", "error"))

    def test_unknown_outcome_or_signal_in_role_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.toml"
            path.write_text(
                _role_toml("bad", outcomes=["approve", "maybe"], extract_decision=True), encoding="utf-8"
            )
            with self.assertRaises(RoleLoadError):
                load_role(path)
            path.write_text(_role_toml("bad", signals=["progress", "telepathy"]), encoding="utf-8")
            with self.assertRaises(RoleLoadError):
                load_role(path)

    def test_workflow_validation_uses_declared_role_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            roles_dir = Path(tmp) / "roles"
            roles_dir.mkdir()
            (roles_dir / "qa_reviewer.toml").write_text(
                _role_toml("qa_reviewer", outcomes=["approve", "deny"], extract_decision=True),
                encoding="utf-8",
            )
            (roles_dir / "developer.toml").write_text(_role_toml("developer", marker="TASK_COMPLETE"), encoding="utf-8")
            roles = load_roles(roles_dir)
            workflow_path = Path(tmp) / "qa.toml"
            workflow_path.write_text(_workflow_toml(reviewer="qa_reviewer", extra_trigger="completion:steer"), encoding="utf-8")
            with self.assertRaises(WorkflowLoadError) as raised:
                load_workflow(
                    workflow_path,
                    available_role_ids=set(roles),
                    role_outcomes={rid: role.completion.outcomes for rid, role in roles.items()},
                )
            self.assertIn("steer", str(raised.exception))

    def test_shipped_workflows_validate_against_shipped_roles(self) -> None:
        roles = load_roles(default_roles_dir())
        workflows = load_workflows(
            default_workflows_dir(),
            available_role_ids=set(roles),
            role_outcomes={rid: role.completion.outcomes for rid, role in roles.items()},
        )
        self.assertIn("development_tiered", workflows)


def _role_toml(
    role_id: str,
    *,
    outcomes: list[str] | None = None,
    signals: list[str] | None = None,
    extract_decision: bool = False,
    marker: str = "",
) -> str:
    outcomes_line = f"outcomes = {json.dumps(outcomes)}\n" if outcomes is not None else ""
    signals_block = f"\n[signals]\nallowed = {json.dumps(signals)}\n" if signals is not None else ""
    return textwrap.dedent(
        f"""
        [role]
        id = "{role_id}"
        name = "{role_id}"
        description = "test role"

        [agent]
        backend = "claude_code"
        model = ""
        session_persistence = false
        permission_mode = "bypassPermissions"

        [prompt]
        template = "Task {{task_title}}\\n{{previous_output}}\\n{{completion_marker}}"

        [completion]
        marker = "{marker}"
        timeout_minutes = 5
        max_cost_usd = 10.0
        {outcomes_line}
        [completion.output]
        extract_decision = {str(extract_decision).lower()}
        extract_summary = {str(not extract_decision).lower()}
        """
    ).lstrip() + signals_block


def _workflow_toml(*, reviewer: str, extra_trigger: str | None = None) -> str:
    extra = ""
    if extra_trigger:
        extra = f"""
[[transitions]]
from = "review"
trigger = "{extra_trigger}"
to = "develop"
carry_output = true
"""
    return f"""
[workflow]
id = "qa_flow"
name = "QA flow"
methodology = "development"

[[steps]]
id = "develop"
role = "developer"

[[steps]]
id = "review"
role = "{reviewer}"

[[steps]]
id = "test"
role = "_builtin:run_tests"

[[steps]]
id = "merge"
role = "_builtin:merge"

[[steps]]
id = "done"
role = "_builtin:mark_done"

[[transitions]]
from = "develop"
trigger = "completion:done"
to = "review"

[[transitions]]
from = "review"
trigger = "completion:approve"
to = "test"

[[transitions]]
from = "review"
trigger = "completion:deny"
to = "develop"
carry_output = true
{extra}
[[transitions]]
from = "test"
trigger = "completion:success"
to = "merge"

[[transitions]]
from = "test"
trigger = "completion:failure"
to = "develop"
carry_output = true

[[transitions]]
from = "merge"
trigger = "completion:success"
to = "done"

[[transitions]]
from = "merge"
trigger = "completion:failure"
to = "develop"
carry_output = true

[[transitions]]
from = "merge"
trigger = "completion:conflict"
to = "develop"
carry_output = true

[fallback]
action = "block"
message = "Unhandled workflow outcome."
"""


class _ScriptedRunner:
    def __init__(self, behaviours) -> None:
        self._behaviours = list(behaviours)
        self.prompts: list[str] = []

    def run(self, config: AgentRunConfig):
        self.prompts.append(config.prompt)
        behaviour = self._behaviours.pop(0)
        yield from behaviour(config)


def _messages(*texts_with_phase):
    def behaviour(config: AgentRunConfig):
        yield AgentEvent("agent.started", payload={"command": "fake"})
        for text, phase in texts_with_phase:
            yield AgentEvent("agent.message", payload={"text": text, "phase": phase})
        yield AgentEvent("agent.completed", payload={"session_id": "s", "cost_usd": 0.0, "duration_ms": 1, "token_count": 1})

    return behaviour


class OrchestratorContractTests(unittest.TestCase):
    """The engine applies the contract to the final message and dedupes signals."""

    def _workspace(self) -> tuple[Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        repo = root / "repo"
        repo.mkdir()
        for args in (
            ("init",),
            ("checkout", "-b", "main"),
            ("config", "user.email", "t@example.com"),
            ("config", "user.name", "T"),
        ):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
        (repo / "README.md").write_text("# r\n", encoding="utf-8")
        (repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
        return repo, root / "foreman.db"

    def _seed(self, store: ForemanStore, repo: Path, *, workflow_id: str = "development") -> tuple[Project, Task]:
        project = Project(
            id="p1", name="Contract", repo_path=str(repo), workflow_id=workflow_id, default_branch="main",
            settings={"task_selection_mode": "directed", "test_command": "true", "default_model": "m"},
        )
        store.save_project(project)
        store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        task = Task(id="t1", sprint_id="s1", project_id="p1", title="Implement", status="todo", acceptance_criteria="Implemented.")
        store.save_task(task)
        return project, task

    def test_marker_must_be_in_the_final_message(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project, task = self._seed(store, repo)
            orchestrator = ForemanOrchestrator(store, agent_runners={"claude_code": _ScriptedRunner([])})
            role = orchestrator.roles["developer"]
            run = Run(id="r1", task_id=task.id, project_id=project.id, role_id="developer", workflow_step="develop", agent_backend="claude_code", status="running")
            store.save_run(run)

            echoed_early = _messages(
                ("Plan: I will implement this and end with TASK_COMPLETE.", "assistant"),
                ("Implemented, but I hit a blocker with the migration.", "result"),
            )
            orchestrator.agent_runners["claude_code"] = _ScriptedRunner([echoed_early])
            result = orchestrator._execute_native_runner_step(
                role=role, project=project, task=task, workflow_step="develop", prompt="p", session_id=None
            )
            self.assertEqual(result.outcome, "error")
            self.assertIn("Missing completion marker", result.detail)

            ended_properly = _messages(
                ("Plan: I will implement this.", "assistant"),
                ("Implemented the feature.\nTASK_COMPLETE", "result"),
            )
            orchestrator.agent_runners["claude_code"] = _ScriptedRunner([ended_properly])
            result = orchestrator._execute_native_runner_step(
                role=role, project=project, task=task, workflow_step="develop", prompt="p", session_id=None
            )
            self.assertEqual(result.outcome, "done")
            self.assertEqual(result.detail, "Implemented the feature.")

    def test_duplicate_signals_apply_once_and_reviewers_cannot_create_tasks(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project, task = self._seed(store, repo)
            orchestrator = ForemanOrchestrator(store, agent_runners={"claude_code": _ScriptedRunner([])})
            payload = {"title": "Follow up", "description": "d", "criteria": "c"}

            def duplicated(config: AgentRunConfig):
                yield AgentEvent("agent.started", payload={"command": "fake"})
                yield AgentEvent("signal.task_created", payload=dict(payload))
                yield AgentEvent("signal.task_created", payload=dict(payload))
                yield AgentEvent("agent.message", payload={"text": "TASK_COMPLETE", "phase": "result"})
                yield AgentEvent("agent.completed", payload={"session_id": "s"})

            run = Run(id="r-dev", task_id=task.id, project_id=project.id, role_id="developer", workflow_step="develop", agent_backend="claude_code", status="running")
            store.save_run(run)
            orchestrator.agent_runners["claude_code"] = _ScriptedRunner([duplicated])
            orchestrator._execute_native_runner_step(
                role=orchestrator.roles["developer"], project=project, task=task, workflow_step="develop",
                prompt="p", session_id=None,
                event_recorder=lambda rec: orchestrator._persist_agent_event(run, task, project, "developer", rec),
            )
            created = [t for t in store.list_tasks(sprint_id="s1") if t.title == "Follow up"]
            self.assertEqual(len(created), 1)

            run2 = Run(id="r-rev", task_id=task.id, project_id=project.id, role_id="code_reviewer", workflow_step="review", agent_backend="claude_code", status="running")
            store.save_run(run2)

            def reviewer_signals(config: AgentRunConfig):
                yield AgentEvent("agent.started", payload={"command": "fake"})
                yield AgentEvent("signal.task_created", payload={"title": "Sneaky", "description": "d", "criteria": "c"})
                yield AgentEvent("agent.message", payload={"text": "APPROVE", "phase": "result"})
                yield AgentEvent("agent.completed", payload={"session_id": "s"})

            orchestrator.agent_runners["claude_code"] = _ScriptedRunner([reviewer_signals])
            result = orchestrator._execute_native_runner_step(
                role=orchestrator.roles["code_reviewer"], project=project, task=task, workflow_step="review",
                prompt="p", session_id=None,
                event_recorder=lambda rec: orchestrator._persist_agent_event(run2, task, project, "code_reviewer", rec),
            )
            self.assertEqual(result.outcome, "approve")
            self.assertEqual([t for t in store.list_tasks(sprint_id="s1") if t.title == "Sneaky"], [])
            rejected = [e for e in store.list_events(run_id=run2.id) if e.event_type == "signal.rejected"]
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0].payload["signal"], "task_created")

    def test_custom_reviewer_role_is_normalized_by_its_contract_not_its_id(self) -> None:
        repo, db_path = self._workspace()
        with tempfile.TemporaryDirectory() as tmp:
            roles_dir = Path(tmp) / "roles"
            roles_dir.mkdir()
            (roles_dir / "qa_reviewer.toml").write_text(
                _role_toml("qa_reviewer", outcomes=["approve", "deny"], extract_decision=True), encoding="utf-8"
            )
            (roles_dir / "developer.toml").write_text(_role_toml("developer", marker="TASK_COMPLETE"), encoding="utf-8")
            workflows_dir = Path(tmp) / "workflows"
            workflows_dir.mkdir()
            (workflows_dir / "qa_flow.toml").write_text(_workflow_toml(reviewer="qa_reviewer"), encoding="utf-8")
            roles = load_roles(roles_dir)
            workflows = load_workflows(
                workflows_dir,
                available_role_ids=set(roles),
                role_outcomes={rid: role.completion.outcomes for rid, role in roles.items()},
            )

            def developer_commits(config: AgentRunConfig):
                (repo / "feature.txt").write_text("done\n", encoding="utf-8")
                subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
                subprocess.run(["git", "commit", "-m", "feat: feature"], cwd=repo, check=True, capture_output=True)
                yield AgentEvent("agent.started", payload={"command": "fake"})
                yield AgentEvent("agent.message", payload={"text": "Implemented the feature.\nTASK_COMPLETE", "phase": "result"})
                yield AgentEvent("agent.completed", payload={"session_id": "s"})

            def qa_approves(config: AgentRunConfig):
                yield AgentEvent("agent.started", payload={"command": "fake"})
                yield AgentEvent("agent.message", payload={"text": "Checked.\n\nDecision: APPROVE", "phase": "result"})
                yield AgentEvent("agent.completed", payload={"session_id": "s"})

            with ForemanStore(db_path) as store:
                store.initialize()
                project, task = self._seed(store, repo, workflow_id="qa_flow")
                orchestrator = ForemanOrchestrator(
                    store,
                    roles=roles,
                    workflows=workflows,
                    agent_runners={"claude_code": _ScriptedRunner([developer_commits, qa_approves])},
                )
                result = orchestrator.run_project(project.id)
                diagnostics = [
                    (r.workflow_step, r.role_id, r.outcome, (r.outcome_detail or "")[:160])
                    for r in store.list_runs(task_id=task.id)
                ]
                self.assertEqual(result.stop_reason, "idle", f"{store.get_task(task.id).blocked_reason}\n{diagnostics}")
                self.assertEqual(store.get_task(task.id).status, "done")
                review_runs = [r for r in store.list_runs(task_id=task.id) if r.role_id == "qa_reviewer"]
                self.assertEqual([r.outcome for r in review_runs], ["approve"])

    def test_tiered_review_approval_satisfies_the_merge_guard(self) -> None:
        """Frontier approval counts as the code review by declared review_kind."""

        repo, db_path = self._workspace()

        def developer_commits(config: AgentRunConfig):
            (repo / "feature.py").write_text("def feature():\n    return 'implemented'\n", encoding="utf-8")
            (repo / "tests_feature.py").write_text("from feature import feature\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "feat: implement the feature"], cwd=repo, check=True, capture_output=True)
            yield AgentEvent("agent.started", payload={"command": "fake"})
            yield AgentEvent("agent.message", payload={"text": "Implemented the feature with tests.\nTASK_COMPLETE", "phase": "result"})
            yield AgentEvent("agent.completed", payload={"session_id": "s"})

        def triage_escalates(config: AgentRunConfig):
            yield AgentEvent("agent.started", payload={"command": "fake"})
            yield AgentEvent("agent.message", payload={"text": "ESCALATE: touches core code", "phase": "result"})
            yield AgentEvent("agent.completed", payload={"session_id": "s"})

        def frontier_approves(config: AgentRunConfig):
            yield AgentEvent("agent.started", payload={"command": "fake"})
            yield AgentEvent("agent.message", payload={"text": "Reviewed the diff.\n\nAPPROVE", "phase": "result"})
            yield AgentEvent("agent.completed", payload={"session_id": "s"})

        with ForemanStore(db_path) as store:
            store.initialize()
            project, task = self._seed(store, repo, workflow_id="development_tiered")
            task.acceptance_criteria = "Implemented the feature with tests."
            store.save_task(task)
            orchestrator = ForemanOrchestrator(
                store,
                agent_runners={"claude_code": _ScriptedRunner([developer_commits, triage_escalates, frontier_approves])},
            )
            result = orchestrator.run_project(project.id)
            self.assertEqual(result.stop_reason, "idle", store.get_task(task.id).blocked_reason)
            done = store.get_task(task.id)
            self.assertEqual(done.status, "done")
            self.assertEqual(done.completion_evidence.review_outcome, "approve")
            steps = [r.workflow_step for r in store.list_runs(task_id=task.id) if r.role_id != "_builtin:orchestrator"]
            self.assertEqual(steps, ["develop", "test", "triage", "review", "merge_approval", "merge", "done"])

    def test_retry_correction_lists_the_roles_declared_outcomes(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            orchestrator = ForemanOrchestrator(store, agent_runners={"claude_code": _ScriptedRunner([])})
            triage = orchestrator.roles["triage_reviewer"]
            corrected = orchestrator._append_output_contract_retry_instruction("prompt", triage, "decision_format")
            self.assertIn("ESCALATE: <why the senior reviewer is needed>", corrected)
            self.assertNotIn("STEER", corrected)


if __name__ == "__main__":
    unittest.main()
