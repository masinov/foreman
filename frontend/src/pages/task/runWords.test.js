import { describe, expect, it } from "vitest";

import { narrate, ownWords, sayEntry, shortPath } from "./runWords";

const at = "2026-11-12T18:27:39Z";
const entry = (kind, data, text = "") => ({ at, kind, text, data });

describe("what a run recorded, in words", () => {
  it("says what the agent did with what it ran or opened beside it", () => {
    expect(sayEntry(entry("agent.command", { command: "npm test", cwd: "/w" }))).toEqual({ says: "Ran", mono: "npm test" });
    expect(
      sayEntry(entry("agent.file_change", { tool: "Read", path: "/repo/.foreman/worktrees/FOR-38/frontend/src/a.js" })),
    ).toEqual({ says: "Read", mono: "frontend/src/a.js" });
    expect(sayEntry(entry("agent.file_change", { tool: "Edit", path: "docs/x.md" })).says).toBe("Edited");
    expect(sayEntry(entry("agent.tool_use", { tool: "Grep", input: { pattern: "shortSha", path: "/r/worktrees/K/src" } }))).toEqual({
      says: "Searched for",
      mono: "shortSha in src",
    });
    // What a tool was given shows as its values, never as JSON.
    expect(sayEntry(entry("agent.tool_use", { tool: "WebFetch", input: { url: "https://example.com" } }))).toEqual({
      says: "Used WebFetch",
      mono: "https://example.com",
    });
  });

  it("says a document the task rests on changed in a merge", () => {
    expect(
      sayEntry(entry("engine.document_changed", { path: "docs/adr/ADR-0041.md", heading: "", named_commit: "def5678abc", merge_sha: "abc1234def", merged_task_key: "FOR-80" })).says,
    ).toBe("docs/adr/ADR-0041.md changed in FOR-80's merge (abc1234) since this task named it at def5678");
  });

  it("says whether the project's folder was brought to the merge", () => {
    expect(sayEntry(entry("engine.checkout_updated", { path: "/p/assay", branch: "main", sha: "e63280b1c2d3", from_sha: "a1" }))).toEqual({
      says: "Brought the project's folder to main at e63280b",
      mono: "/p/assay",
    });
    expect(
      sayEntry(entry("engine.checkout_behind", { path: "/p/assay", branch: "main", sha: "e63280b1", reason: "it holds staged changes that are not a commit of main" })),
    ).toEqual({
      says: "The project's folder still shows an older main",
      mono: "/p/assay",
      body: "it holds staged changes that are not a commit of main",
      tone: "failed",
    });
  });

  it("says how a step went, with the colour of its outcome", () => {
    expect(sayEntry(entry("engine.test_run", { exit_code: 0, duration_seconds: 187.1, head_sha: "c52648ddceab" }))).toEqual({
      says: "Tests passed in 3 min 7 s at c52648d",
      tone: "passed",
    });
    expect(sayEntry(entry("engine.test_run", { exit_code: 2, duration_seconds: 3 })).says).toBe("Tests failed (exit code 2) in 3 s");
    expect(sayEntry(entry("workflow.paused", { reason: "human_gate", policy: "merge_approval" })).says).toBe(
      "Waiting for a user: merge approval",
    );
    expect(sayEntry(entry("workflow.resumed", { decision: "approve", next_step: "merge" })).says).toBe("A user approved");
    expect(sayEntry(entry("workflow.gate_auto_approved", { policy: "merge_approval", step: "merge_approval" })).says).toBe(
      "Approved without asking anyone",
    );
    expect(sayEntry(entry("engine.test_started", { command: "npm test" }))).toEqual({ says: "Ran", mono: "npm test" });
  });

  it("says why the engine asked again", () => {
    expect(sayEntry(entry("engine.output_contract_retry", { reason: "approved_unread" })).says).toMatch(/without opening a file/);
    expect(sayEntry(entry("engine.output_contract_retry", { reason: "missing_completion_marker" })).says).toMatch(/completion marker/);
  });

  it("leaves to the step's facts what they say: its model, its tools, how it started and ended, what came next", () => {
    for (const kind of [
      "workflow.step_started",
      "workflow.model_selected",
      "engine.role_policy",
      "agent.started",
      "agent.completed",
      "engine.review_recorded",
      "workflow.step_completed",
      "workflow.transition",
    ]) {
      expect(sayEntry(entry(kind, { step: "review", outcome: "approve" }))).toBeNull();
    }
  });

  it("says nothing of a usage limit that lets the account go on, and says one that stopped it", () => {
    expect(sayEntry(entry("agent.rate_limit", { rate_limit_type: "seven_day", status: "allowed_warning" }))).toBeNull();
    expect(sayEntry(entry("agent.rate_limit", { rate_limit_type: "seven_day", status: "rejected" }))).toEqual({
      says: "Stopped by the account's usage limit (seven day)",
      tone: "failed",
    });
  });

  it("shows an agent's words without the decision it opens with or the marker it ends with", () => {
    expect(ownWords("APPROVE\n\nI read the whole diff.")).toBe("I read the whole diff.");
    expect(ownWords("STEER: The log can still contain the host.\n\nMore.")).toBe("The log can still contain the host.\n\nMore.");
    expect(ownWords("Decision: DENY - out of scope")).toBe("out of scope");
    expect(ownWords("Done, and committed.\n\nTASK_COMPLETE\n")).toBe("Done, and committed.");
    // A word that only begins like a decision is the agent's own.
    expect(ownWords("APPROVED changes are listed below.")).toBe("APPROVED changes are listed below.");
    expect(sayEntry(entry("agent.message", { text: "APPROVE" }))).toBeNull();
  });

  it("says what a user did by hand, and why", () => {
    expect(
      sayEntry(entry("human.task_completed", { by: "Claude", reason: "Merged by hand.", from_status: "in_progress" })),
    ).toEqual({ says: "Marked done by hand by Claude", body: "Merged by hand.", prose: true });
    expect(sayEntry(entry("human.task_cancelled", {})).says).toBe("Cancelled");
  });

  it("shows what a tool returned without a line of its own, unless it failed", () => {
    expect(sayEntry(entry("agent.tool_result", { is_error: false, length: 12, preview: "\n\n  first\nsecond\n" }))).toEqual({
      says: "",
      body: "  first\nsecond",
      tone: null,
    });
    expect(sayEntry(entry("agent.tool_result", { is_error: true, preview: "boom" }))).toMatchObject({ says: "It failed", tone: "failed" });
    // A tool the role was not given: what happened, not an error.
    expect(
      sayEntry(entry("agent.tool_result", { is_error: true, preview: "<tool_use_error>Error: No such tool available: Bash. Bash is disabled.</tool_use_error>" })),
    ).toEqual({ says: "Not run: this role may not use Bash" });
    expect(sayEntry(entry("agent.tool_result", { is_error: false, preview: "" }))).toBeNull();
  });

  it("leaves out the engine's bookkeeping and what it has no words for; the transcript keeps them", () => {
    expect(sayEntry(entry("engine.context_write", { path: ".foreman/context.md" }))).toBeNull();
    expect(sayEntry(entry("agent.cost_update", { cumulative_usd: 1 }))).toBeNull();
    expect(sayEntry(entry("engine.sprint_ready", { sprint_id: "s", task_ids: ["a"] }))).toBeNull();
  });

  it("shortens a path inside a working copy and leaves others alone", () => {
    expect(shortPath("/a/.foreman/worktrees/FOR-1/src/x.py")).toBe("src/x.py");
    expect(shortPath("docs/x.md")).toBe("docs/x.md");
  });
});

describe("a run's story", () => {
  it("gathers test output into one block and drops a closing message that repeats", () => {
    const lines = narrate([
      entry("engine.test_started", { command: "npm test" }),
      { at, kind: "engine.test_output", stream: "stdout", text: "line one" },
      { at, kind: "engine.test_output", stream: "stdout", text: "line two" },
      entry("engine.test_run", { exit_code: 0, duration_seconds: 1 }),
      entry("agent.message", { phase: "assistant", text: "APPROVE\n\nThe change is right." }),
      entry("agent.message", { phase: "result", text: "APPROVE\n\nThe change is right." }),
      entry("engine.context_write", { path: "x" }),
    ]);
    expect(lines.map((line) => line.kind)).toEqual(["engine.test_started", "engine.test_output", "engine.test_run", "agent.message"]);
    expect(lines[1]).toMatchObject({ output: true, body: "line one\nline two" });
    expect(lines[3]).toMatchObject({ body: "The change is right.", prose: true });
  });

  it("is empty for a run that recorded nothing", () => {
    expect(narrate([])).toEqual([]);
    expect(narrate(undefined)).toEqual([]);
  });
});
