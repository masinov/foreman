"""Tests for versioned event constructors."""

from __future__ import annotations

import unittest

from foreman.events import (
    SCHEMA_VERSION,
    agent_completed,
    agent_error,
    agent_killed,
    agent_started,
    engine_branch_violation,
    engine_completion_evidence,
    engine_completion_guard,
    engine_crash_recovery,
    engine_supervisor_merge,
    engine_task_created,
    engine_test_run,
    engine_test_started,
    gate_cost_exceeded,
    gate_time_exceeded,
    workflow_no_transition,
    workflow_step_completed,
    workflow_transition,
)


class SchemaVersionTests(unittest.TestCase):
    def test_schema_version_present(self) -> None:
        evt = agent_started(role_id="developer", backend="claude_code")
        self.assertEqual(evt.payload["schema_version"], SCHEMA_VERSION)


class AgentEventTests(unittest.TestCase):
    def test_agent_started(self) -> None:
        evt = agent_started(role_id="developer", backend="claude_code", model="sonnet-4-6", session_id="sess-1")
        self.assertEqual(evt.event_type, "agent.started")
        self.assertEqual(evt.payload["role_id"], "developer")
        self.assertEqual(evt.payload["backend"], "claude_code")
        self.assertEqual(evt.payload["model"], "sonnet-4-6")
        self.assertEqual(evt.payload["session_id"], "sess-1")

    def test_agent_completed(self) -> None:
        evt = agent_completed(result="All done.", cost_usd=0.05, token_count=100)
        self.assertEqual(evt.event_type, "agent.completed")
        self.assertEqual(evt.payload["result"], "All done.")
        self.assertEqual(evt.payload["cost_usd"], 0.05)

    def test_agent_error(self) -> None:
        evt = agent_error("Connection timed out.")
        self.assertEqual(evt.event_type, "agent.error")
        self.assertEqual(evt.payload["error"], "Connection timed out.")

    def test_agent_killed(self) -> None:
        evt = agent_killed(reason="Gate timeout", gate_type="time")
        self.assertEqual(evt.event_type, "agent.killed")
        self.assertEqual(evt.payload["reason"], "Gate timeout")
        self.assertEqual(evt.payload["gate_type"], "time")


class WorkflowEventTests(unittest.TestCase):
    def test_workflow_step_completed(self) -> None:
        evt = workflow_step_completed(step="developer", outcome="done")
        self.assertEqual(evt.event_type, "workflow.step_completed")
        self.assertEqual(evt.payload["step"], "developer")
        self.assertEqual(evt.payload["outcome"], "done")

    def test_workflow_transition(self) -> None:
        evt = workflow_transition(from_step="developer", to_step="reviewer", trigger="completion:done")
        self.assertEqual(evt.event_type, "workflow.transition")
        self.assertEqual(evt.payload["from_step"], "developer")
        self.assertEqual(evt.payload["to_step"], "reviewer")

    def test_workflow_no_transition(self) -> None:
        evt = workflow_no_transition(step="developer", outcome="blocked")
        self.assertEqual(evt.event_type, "workflow.no_transition")
        self.assertEqual(evt.payload["step"], "developer")


class EngineEventTests(unittest.TestCase):
    def test_engine_test_started(self) -> None:
        evt = engine_test_started(command="pytest")
        self.assertEqual(evt.event_type, "engine.test_started")
        self.assertEqual(evt.payload["command"], "pytest")

    def test_engine_test_run(self) -> None:
        evt = engine_test_run(command="pytest", exit_code=0, passed=True, output_tail="PASSED")
        self.assertEqual(evt.event_type, "engine.test_run")
        self.assertEqual(evt.payload["exit_code"], 0)
        self.assertTrue(evt.payload["passed"])

    def test_engine_completion_guard(self) -> None:
        evt = engine_completion_guard(
            verdict="failed",
            score=30.0,
            score_breakdown="criteria: 1/3",
            changed_files=["src/main.py"],
            reasons=["Score too low"],
        )
        self.assertEqual(evt.event_type, "engine.completion_guard")
        self.assertEqual(evt.payload["verdict"], "failed")

    def test_engine_completion_evidence(self) -> None:
        evt = engine_completion_evidence(
            task_id="task-1",
            criteria_count=3,
            criteria_addressed=1,
            score=33.0,
            verdict="partial",
            proof_status="failed",
            changed_files=["src/main.py"],
            builtin_test_passed=True,
            failure_reasons=["Score too low"],
        )
        self.assertEqual(evt.event_type, "engine.completion_evidence")
        self.assertEqual(evt.payload["proof_status"], "failed")
        self.assertIn("failure_reasons", evt.payload)

    def test_engine_supervisor_merge(self) -> None:
        evt = engine_supervisor_merge(
            branch="feat/my-task",
            target="main",
            task_id="task-1",
            evidence_score=85.0,
            evidence_verdict="pass",
        )
        self.assertEqual(evt.event_type, "engine.supervisor_merge")
        self.assertEqual(evt.payload["branch"], "feat/my-task")

    def test_engine_crash_recovery(self) -> None:
        evt = engine_crash_recovery(
            run_id="run-1",
            task_id="task-1",
            previous_status="running",
            holder_id="holder-1",
            lease_token="tok-abc",
        )
        self.assertEqual(evt.event_type, "engine.crash_recovery")
        self.assertEqual(evt.payload["lease_token"], "tok-abc")

    def test_engine_branch_violation(self) -> None:
        evt = engine_branch_violation(branch="main", detail="Default branch was mutated.")
        self.assertEqual(evt.event_type, "engine.branch_violation")
        self.assertEqual(evt.payload["branch"], "main")

    def test_engine_task_created(self) -> None:
        evt = engine_task_created(
            task_id="task-2",
            title="Follow-up task",
            task_type="feature",
            created_by="agent:developer",
        )
        self.assertEqual(evt.event_type, "engine.task_created")
        self.assertEqual(evt.payload["task_type"], "feature")


class GateEventTests(unittest.TestCase):
    def test_gate_cost_exceeded(self) -> None:
        evt = gate_cost_exceeded(task_id="task-1", total_cost_usd=150.0, cost_limit_usd=100.0)
        self.assertEqual(evt.event_type, "gate.cost_exceeded")
        self.assertEqual(evt.payload["total_cost_usd"], 150.0)

    def test_gate_time_exceeded(self) -> None:
        evt = gate_time_exceeded(task_id="task-1", total_duration_ms=3600000, time_limit_ms=1800000)
        self.assertEqual(evt.event_type, "gate.time_exceeded")
        self.assertEqual(evt.payload["time_limit_ms"], 1800000)
