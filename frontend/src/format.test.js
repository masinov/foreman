import { describe, it, expect } from "vitest";

import {
  costUnknownNote,
  deriveEngineState,
  engineState,
  evidenceFacts,
  eventMatchesFilter,
  formatBlockedKind,
  formatEngineSummary,
  formatGuidanceState,
  formatEventSummary,
  formatHeartbeatAge,
  formatSelectionMode,
  formatTokenUsage,
  formatWorkflowLabel,
  getEventCategory,
  getTaskTypeClass,
} from "./format";

describe("formatSelectionMode + formatWorkflowLabel", () => {
  it("renders friendly landing-card labels instead of raw ids", () => {
    expect(formatSelectionMode("directed")).toBe("Directed");
    expect(formatSelectionMode("autonomous")).toBe("Autonomous");
    expect(formatSelectionMode(undefined)).toBe("Directed");
    expect(formatWorkflowLabel("development_tiered")).toBe("Tiered workflow");
    expect(formatWorkflowLabel("development")).toBe("Standard workflow");
    expect(formatWorkflowLabel(undefined)).toBe("Standard workflow");
    expect(formatWorkflowLabel("custom_flow")).toBe("Custom Flow");
  });
});

describe("getTaskTypeClass", () => {
  it("maps every backend task type to a styled class (no invalid 'bug')", () => {
    expect(getTaskTypeClass("feature")).toBe("tag-feature");
    expect(getTaskTypeClass("fix")).toBe("tag-fix");
    expect(getTaskTypeClass("refactor")).toBe("tag-refactor");
    expect(getTaskTypeClass("docs")).toBe("tag-docs");
    expect(getTaskTypeClass("spike")).toBe("tag-spike");
    expect(getTaskTypeClass("chore")).toBe("tag-chore");
  });
});

describe("getEventCategory + eventMatchesFilter", () => {
  it("routes roadmap events into populated, filterable buckets", () => {
    expect(getEventCategory("engine.attention_needed")).toBe("review");
    expect(getEventCategory("engine.completion_evidence")).toBe("review");
    expect(getEventCategory("gate.cost_exceeded")).toBe("review");
    expect(getEventCategory("agent.message")).toBe("message");
    expect(getEventCategory("workflow.model_selected")).toBe("workflow");
    expect(getEventCategory("human.message")).toBe("human");
  });

  it("matches the Decisions filter for evidence/attention events", () => {
    const evt = { event_type: "engine.completion_evidence", payload: {} };
    expect(eventMatchesFilter(evt, "review")).toBe(true);
    expect(eventMatchesFilter(evt, "workflow")).toBe(false);
    expect(eventMatchesFilter(evt, "all")).toBe(true);
  });
});

describe("deriveEngineState", () => {
  it("treats agent_running as the authoritative 'running' signal", () => {
    expect(deriveEngineState({ agent_running: true, status: "idle" })).toBe("running");
    expect(deriveEngineState({ agent_running: false, task_counts: { blocked: 2 } })).toBe("blocked");
    expect(deriveEngineState({ agent_running: false, task_counts: { blocked: 0 } })).toBe("idle");
  });

  it("falls back to the legacy status when agent_running is absent", () => {
    expect(deriveEngineState({ status: "running" })).toBe("running");
    expect(deriveEngineState({ status: "blocked" })).toBe("blocked");
    expect(deriveEngineState(null)).toBe("idle");
  });
});

describe("costUnknownNote", () => {
  it("notes runs with unknown cost, and stays empty when all costs are known", () => {
    expect(costUnknownNote({ zero_cost_token_runs: 3 })).toBe("cost unknown for 3 runs");
    expect(costUnknownNote({ zero_cost_token_runs: 1 })).toBe("cost unknown for 1 run");
    expect(costUnknownNote({ zero_cost_token_runs: 0 })).toBe("");
    expect(costUnknownNote(undefined)).toBe("");
  });
});

describe("formatEventSummary", () => {
  it("summarizes the new roadmap event types", () => {
    expect(
      formatEventSummary({ event_type: "engine.attention_needed", payload: { trigger: "evidence_failed" } }),
    ).toBe("Attention needed: evidence_failed");
    expect(
      formatEventSummary({ event_type: "workflow.model_selected", payload: { model: "claude-opus-4-8", source: "ladder", step: "review" } }),
    ).toBe("Model: claude-opus-4-8 (ladder) @ review");
  });
});

describe("resident engine state", () => {
  it("reads residency and pause state from the agent status payload", () => {
    expect(engineState({ resident: true, paused: false })).toBe("resident");
    expect(engineState({ resident: true, paused: true })).toBe("paused");
    expect(engineState({ resident: false, paused: false })).toBe("stopped");
    expect(engineState(null)).toBe("stopped");
  });

  it("summarises the engine with its heartbeat age", () => {
    expect(formatEngineSummary({ resident: true, paused: false, heartbeat_age_seconds: 4 })).toBe(
      "Engine: resident · heartbeat 4s ago",
    );
    expect(formatEngineSummary({ resident: true, paused: true, heartbeat_age_seconds: 125 })).toBe(
      "Engine: paused · heartbeat 2m ago",
    );
    expect(formatEngineSummary({ resident: false })).toBe("Engine: not running");
  });

  it("rounds the heartbeat age to what a header can show", () => {
    expect(formatHeartbeatAge(0)).toBe("0s ago");
    expect(formatHeartbeatAge(59.6)).toBe("60s ago");
    expect(formatHeartbeatAge(3600)).toBe("1h ago");
    expect(formatHeartbeatAge(null)).toBeNull();
  });

  it("treats a paused engine as not running for the project card", () => {
    expect(deriveEngineState({ engine: { resident: true, paused: false } })).toBe("running");
    expect(deriveEngineState({ engine: { resident: true, paused: true } })).toBe("blocked");
    expect(deriveEngineState({ engine: { resident: false }, task_counts: { blocked: 0 } })).toBe("idle");
  });
});

describe("formatBlockedKind", () => {
  it("names the two ways a task ends up blocked", () => {
    expect(formatBlockedKind("gate")).toBe("human gate");
    expect(formatBlockedKind("engine")).toBe("engine");
    expect(formatBlockedKind(null)).toBe("");
  });
});

describe("formatTokenUsage", () => {
  it("names each part and leaves out the empty ones", () => {
    expect(
      formatTokenUsage({ input: 10, output: 5000, cache_read: 900000, cache_creation: 0 }),
    ).toBe("10 in · 5K out · 900K cache read");
  });

  it("is empty when nothing was reported", () => {
    expect(formatTokenUsage(null)).toBe("");
    expect(formatTokenUsage({ input: 0, output: 0, cache_read: 0, cache_creation: 0 })).toBe("");
  });
});

describe("evidenceFacts", () => {
  const head = "b".repeat(40);

  it("says what passed and on which commit", () => {
    const rows = evidenceFacts({
      head_sha: head,
      tests_status: "passed",
      tested_sha: head,
      test_exit_code: 0,
      test_duration_seconds: 114.2,
      review_outcome: "approve",
      reviewed_sha: head,
      criteria_count: 2,
      judged_by: "none",
    });
    expect(rows.map((row) => [row.label, row.text, row.tone])).toEqual([
      ["Tests", "Passed on bbbbbbbb (exit 0, 114s)", "ok"],
      ["Code review", "Approved bbbbbbbb", "ok"],
      ["Criteria", "2 listed, not checked by a judge model; code review covers them", "none"],
    ]);
  });

  it("flags tests and a review that are about an older commit", () => {
    const rows = evidenceFacts({
      head_sha: head,
      tests_status: "stale",
      tested_sha: "a".repeat(40),
      review_outcome: "approve",
      reviewed_sha: "a".repeat(40),
      criteria_count: 1,
      criteria_addressed: 1,
      judged_by: "judge-model",
    });
    expect(rows[0]).toEqual({
      label: "Tests",
      text: "Ran on aaaaaaaa, but the branch is now at bbbbbbbb",
      tone: "bad",
    });
    expect(rows[1].text).toBe("Approved aaaaaaaa, but the branch is now at bbbbbbbb");
    expect(rows[1].tone).toBe("bad");
    expect(rows[2].text).toBe("1 of 1 passed, judged by judge-model");
  });

  it("never reports a check that did not run", () => {
    const rows = evidenceFacts({ criteria_count: 0 });
    expect(rows.map((row) => row.text)).toEqual(["Not run", "None yet", "None defined"]);
    expect(rows.every((row) => row.tone === "none")).toBe(true);
  });

  it("treats evidence saved with the old keyword match as unchecked", () => {
    const rows = evidenceFacts({ criteria_count: 3, criteria_addressed: 3, judged_by: "heuristic" });
    expect(rows[2].tone).toBe("none");
    expect(rows[2].text).toContain("not checked");
  });
});

describe("guidance", () => {
  it("says whether an agent step has read a note", () => {
    expect(formatGuidanceState({ delivered: false })).toBe("Waiting for the next agent step");
    expect(
      formatGuidanceState({ delivered: true, delivered_role: "developer", delivered_step: "develop" }),
    ).toBe("Read by developer at develop");
  });

  it("summarises the delivery event", () => {
    expect(
      formatEventSummary({
        event_type: "human.message_delivered",
        payload: { message_event_ids: ["a", "b"], role: "developer", step: "develop" },
      }),
    ).toBe("Guidance read by developer @ develop (2 notes)");
  });
});
