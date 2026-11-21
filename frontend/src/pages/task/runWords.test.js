import { describe, expect, it } from "vitest";

import { narrate, sayEntry, shortPath } from "./runWords";

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
    expect(sayEntry(entry("agent.tool_use", { tool: "WebFetch", input: { url: "https://example.com" } }))).toEqual({
      says: "Used WebFetch",
      mono: '{"url":"https://example.com"}',
    });
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
      clamp: true,
    });
  });

  it("says how a step went, with the colour of its outcome", () => {
    expect(sayEntry(entry("engine.test_run", { exit_code: 0, duration_seconds: 187.1, head_sha: "c52648ddceab" }))).toEqual({
      says: "Tests passed in 3 min 7 s at c52648d",
      tone: "passed",
    });
    expect(sayEntry(entry("engine.test_run", { exit_code: 2, duration_seconds: 3 })).says).toBe("Tests failed (exit code 2) in 3 s");
    expect(sayEntry(entry("workflow.step_completed", { step: "review", outcome: "approve" }))).toEqual({
      says: "Review ended: Approved",
      tone: "passed",
    });
    expect(sayEntry(entry("workflow.paused", { reason: "human_gate", policy: "merge_approval" })).says).toBe(
      "Waiting for a user: merge approval",
    );
    expect(sayEntry(entry("workflow.resumed", { decision: "approve", next_step: "merge" })).says).toBe(
      "A user approved. Next step: Merge",
    );
    expect(sayEntry(entry("agent.completed", { duration_ms: 9400, token_count: 1200, cost_usd: 0.12 })).says).toBe(
      "Finished in 9.4 s · 1.2K tokens · $0.12",
    );
  });

  it("says why the engine asked again", () => {
    expect(sayEntry(entry("engine.output_contract_retry", { reason: "approved_unread" })).says).toMatch(/without opening a file/);
    expect(sayEntry(entry("engine.output_contract_retry", { reason: "missing_completion_marker" })).says).toMatch(/completion marker/);
  });

  it("says what tools a role had", () => {
    expect(sayEntry(entry("engine.role_policy", { allowed_tools: ["Read", "Grep"], disallowed_tools: ["Bash"] })).says).toBe("May use: Read, Grep");
    expect(sayEntry(entry("engine.role_policy", { allowed_tools: [], disallowed_tools: ["Bash", "Write"] })).says).toBe(
      "May use every tool except Bash, Write",
    );
    expect(sayEntry(entry("engine.role_policy", {})).says).toBe("May use every tool");
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
      clamp: true,
    });
    expect(sayEntry(entry("agent.tool_result", { is_error: true, preview: "boom" }))).toMatchObject({ says: "It failed", tone: "failed" });
    expect(sayEntry(entry("agent.tool_result", { is_error: false, preview: "" }))).toBeNull();
  });

  it("leaves the engine's bookkeeping out and never drops what it does not know", () => {
    expect(sayEntry(entry("engine.context_write", { path: ".foreman/context.md" }))).toBeNull();
    expect(sayEntry(entry("agent.cost_update", { cumulative_usd: 1 }))).toBeNull();
    expect(sayEntry(entry("engine.something_new", { detail: "x" }))).toEqual({ says: "Engine something new", mono: '{"detail":"x"}' });
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
      entry("agent.message", { phase: "assistant", text: "APPROVE" }),
      entry("agent.message", { phase: "result", text: "APPROVE" }),
      entry("engine.context_write", { path: "x" }),
    ]);
    expect(lines.map((line) => line.kind)).toEqual(["engine.test_started", "engine.test_output", "engine.test_run", "agent.message"]);
    expect(lines[1]).toMatchObject({ output: true, body: "line one\nline two" });
    expect(lines[3]).toMatchObject({ body: "APPROVE", prose: true });
  });

  it("is empty for a run that recorded nothing", () => {
    expect(narrate([])).toEqual([]);
    expect(narrate(undefined)).toEqual([]);
  });
});
