import { describe, it, expect } from "vitest";

import {
  costUnknownNote,
  deriveEngineState,
  engineState,
  eventMatchesFilter,
  formatBlockedKind,
  formatEngineSummary,
  formatEventSummary,
  formatHeartbeatAge,
  formatSelectionMode,
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
