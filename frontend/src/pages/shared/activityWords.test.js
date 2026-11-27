import { stepRows } from "../task/taskWords";
import { FOREMAN, modelSourceWords, runBy, runResult, runRole, stepOutcome, testCountWords, whoWord } from "./activityWords";

// A run as the task's own record has it (`workflow_step`, `agent_backend`).
const run = (fields) => ({ status: "completed", agent_backend: "claude_code", model: "sonnet-5-5", ...fields });

describe("who did a run", () => {
  it("names the model, Foreman for the engine's own steps, and the person who filed the task", () => {
    expect(runBy(run({ role_id: "developer" }))).toBe("sonnet-5-5");
    expect(runBy(run({ role_id: "_builtin:run_tests", agent_backend: "builtin", model: null }))).toBe(FOREMAN);
    expect(runBy(run({ role_id: "_builtin:orchestrator", agent_backend: "orchestrator", model: null }))).toBe(FOREMAN);
    const filed = run({ role_id: "human", agent_backend: "cli", outcome: "file", model: null });
    expect(runBy(filed, { created_by: "masis" })).toBe("masis");
    expect(runBy(filed, { created_by: "human" })).toBe("a user");
    expect(runBy(run({ role_id: "api", agent_backend: "api", outcome: "created" }), { source: { system: "tracker" } })).toBe(
      "tracker, through the API",
    );
  });

  it("says a gate was decided by a user or by Foreman, as the run records", () => {
    const gate = { role_id: "_builtin:human_gate", workflow_step: "merge_approval", model: null };
    expect(runBy(run({ ...gate, agent_backend: "human", outcome: "approve" }))).toBe("a user");
    expect(runBy(run({ ...gate, agent_backend: "builtin", outcome: "approve" }))).toBe(FOREMAN);
  });
});

describe("who did a run, by role", () => {
  it("names an agent's role with its model on hover, and everyone else as runBy does", () => {
    expect(runRole(run({ role_id: "code_reviewer" }))).toEqual({ text: "Code reviewer", title: "sonnet-5-5" });
    expect(runRole(run({ role_id: "_builtin:run_tests", agent_backend: "builtin", model: null }))).toEqual({ text: FOREMAN, title: "" });
    expect(runRole(run({ role_id: "developer", agent_backend: "engine", model: null }))).toEqual({ text: FOREMAN, title: "" });
    expect(runRole({ source: "event", actor: "ana" })).toEqual({ text: "ana", title: "" });
    expect(runRole({ source: "event", actor: "dashboard" })).toEqual({ text: "a user", title: "" });
  });

  it("names the By filter's choices", () => {
    expect(["developer", "code_reviewer", "foreman", "user"].map(whoWord)).toEqual(["Developer", "Code reviewer", FOREMAN, "Users"]);
  });
});

describe("how a step of a task ended, in its row", () => {
  it("says a step that made a commit committed, and a gate the setting decided was approved by it", () => {
    const develop = run({ role_id: "developer", outcome: "done", commit_sha: "b".repeat(40) });
    expect(stepOutcome(develop, { step_commit: "a".repeat(40) })).toMatchObject({ word: "Committed", tone: "passed" });
    // A step that left the branch where it was made no commit.
    expect(stepOutcome(develop, { step_commit: "b".repeat(40) }).word).toBe("Done");
    const gate = { role_id: "_builtin:human_gate", outcome: "approve", model: null };
    expect(stepOutcome(run({ ...gate, agent_backend: "builtin" }))).toMatchObject({ word: "Approved by setting", tone: "idle" });
    expect(stepOutcome(run({ ...gate, agent_backend: "human" }))).toMatchObject({ word: "Approved", tone: "passed" });
    // A person's approval names the commit it was made at.
    expect(stepOutcome(run({ ...gate, agent_backend: "human", commit_sha: "abc1234".padEnd(40, "0") })).word).toBe(
      "Approved at abc1234",
    );
    // One that named no version says what it was recorded against; where the
    // row shows the commit, the words do not repeat it.
    const sha = "abc1234".padEnd(40, "0");
    const unnamed = run({ ...gate, agent_backend: "human", commit_sha: sha, gate_version: { branch_sha: sha, named: false } });
    const named = run({ ...gate, agent_backend: "human", commit_sha: sha, gate_version: { branch_sha: sha, named: true } });
    expect(stepOutcome(unnamed).word).toBe("Approved (recorded at abc1234)");
    expect(stepOutcome(named).word).toBe("Approved at abc1234");
    expect(stepOutcome(named, null, { commitShown: true }).word).toBe("Approved");
    const shown = stepOutcome(unnamed, null, { commitShown: true });
    expect(shown.word).toBe("Approved, version not named");
    expect(shown.note).toContain("Recorded at abc1234");
    // A plan's version is its fingerprint, never in a commit column.
    const plan = run({ ...gate, agent_backend: "human", gate_version: { fingerprint: "f00dbad".padEnd(64, "0"), named: false } });
    expect(stepOutcome(plan, null, { commitShown: true }).word).toBe("Approved (recorded at plan f00dbad)");
    expect(stepOutcome(run({ role_id: "code_reviewer", outcome: "steer", commit_sha: "c".repeat(40) })).word).toBe("Sent back");
  });

  it("says how many tests a test step ran, when the command reported them", () => {
    const tests = { role_id: "_builtin:run_tests", agent_backend: "builtin", model: null };
    const passed = run({ ...tests, outcome: "success", tests: { tests: 1599, passed: 1598, failed: 0, skipped: 1 } });
    expect(stepOutcome(passed)).toMatchObject({ word: "Passed · 1,599 tests, 1 skipped", tone: "passed" });
    const failed = run({ ...tests, outcome: "failure", tests: { tests: 186, passed: 183, failed: 3, skipped: 0 } });
    expect(stepOutcome(failed)).toMatchObject({ word: "Failed · 3 of 186 tests", tone: "failed" });
    // No report: the word alone.
    expect(stepOutcome(run({ ...tests, outcome: "success", tests: null })).word).toBe("Passed");
    expect(testCountWords({ tests: 1, passed: 1, failed: 0, skipped: 0 })).toBe("1 test");
    expect(testCountWords(undefined)).toBe("");
  });
});

describe("how a run ended", () => {
  it("says a send-back is one, with the reviewer's reason", () => {
    const steer = run({ role_id: "code_reviewer", outcome: "steer", outcome_detail: "The log can still contain the host and port." });
    expect(runResult(steer)).toEqual({ tone: "attention", word: "Sent back", note: "The log can still contain the host and port." });
    const denied = run({ role_id: "_builtin:human_gate", agent_backend: "human", outcome: "deny", outcome_detail: "Use the helper." });
    expect(runResult(denied)).toEqual({ tone: "attention", word: "Sent back", note: "Use the helper." });
  });

  it("says a question was asked, with the question, and that it was answered, with the answer and who gave it", () => {
    const asked = run({ role_id: "developer", outcome: "ask", outcome_detail: "Which store holds it?" });
    expect(runResult(asked)).toEqual({ tone: "attention", word: "Asked a question", note: "Which store holds it?" });
    const answer = run({
      role_id: "_builtin:answer",
      agent_backend: "human",
      outcome: "answered",
      outcome_detail: 'option 2 ("A file")',
      record: { kind: "answer", fields: { answered_by: "mario" } },
    });
    expect(runResult(answer)).toEqual({ tone: "passed", word: "Answered", note: 'option 2 ("A file")' });
    expect(runBy(answer)).toBe("mario");
    expect(runBy({ ...answer, record: { fields: { answered_by: "cli" } } })).toBe("a user");
  });

  it("names a success by what the step does", () => {
    const success = (role_id) => runResult(run({ role_id, agent_backend: "builtin", outcome: "success" })).word;
    expect(success("_builtin:run_tests")).toBe("Passed");
    expect(success("_builtin:merge")).toBe("Merged");
    expect(success("_builtin:mark_done")).toBe("Closed");
    expect(runResult(run({ role_id: "developer", outcome: "done" })).word).toBe("Done");
  });

  it("says a gate the project setting decided was decided by it", () => {
    const auto = run({
      role_id: "_builtin:human_gate",
      agent_backend: "builtin",
      outcome: "approve",
      outcome_detail: "Auto-approved by policy (merge_approval=auto).",
    });
    expect(runResult(auto)).toEqual({ tone: "passed", word: "Approved", note: "By the project setting" });
    const asked = run({ role_id: "_builtin:human_gate", agent_backend: "builtin", outcome: "paused", outcome_detail: "Awaiting human approval" });
    expect(runResult(asked)).toEqual({ tone: "attention", word: "Asked a user", note: "" });
  });

  it("gives a failure its message, and a merge conflict its first sentence", () => {
    const failed = run({ role_id: "developer", outcome: "error", outcome_detail: "Missing completion marker `TASK_COMPLETE`." });
    expect(runResult(failed)).toEqual({ tone: "failed", word: "Failed", note: "Missing completion marker `TASK_COMPLETE`." });
    const killed = run({ role_id: "developer", status: "killed", outcome: "error", outcome_detail: "Engine command 'shutdown' stopped the running step." });
    expect(runResult(killed).word).toBe("Stopped");
    const conflict = run({
      role_id: "_builtin:merge",
      agent_backend: "builtin",
      outcome: "conflict",
      outcome_detail: "Merge conflict in foreman/api.py. Resolve it on the branch.\nCONFLICT (content)",
    });
    expect(runResult(conflict)).toEqual({ tone: "attention", word: "Merge conflict", note: "Merge conflict in foreman/api.py." });
  });

  it("says the engine's own records as interruptions and resumptions", () => {
    const orchestrator = (detail) =>
      runResult(run({ role_id: "_builtin:orchestrator", agent_backend: "orchestrator", outcome: "success", outcome_detail: detail }));
    expect(orchestrator("Engine resumed.")).toEqual({ tone: "idle", word: "Resumed", note: "" });
    expect(orchestrator("Shut down during task 't': the agent process group was terminated.").word).toBe("Interrupted");
    expect(orchestrator("engine.sprint_ready")).toEqual({ tone: "idle", word: "Recorded", note: "engine.sprint_ready" });
  });
});

describe("a step on Overview", () => {
  it("says a step passed after sending the task back", () => {
    const workflow = { steps: [{ id: "develop", role: "developer" }, { id: "review", role: "code_reviewer" }] };
    const at = (minute) => `2026-11-20T17:${minute}:00Z`;
    const task = {
      id: "t",
      status: "done",
      runs: [
        run({ workflow_step: "develop", role_id: "developer", outcome: "done", started_at: at("40") }),
        run({ workflow_step: "review", role_id: "code_reviewer", outcome: "steer", started_at: at("48") }),
        run({ workflow_step: "develop", role_id: "developer", outcome: "done", started_at: at("49") }),
        run({ workflow_step: "review", role_id: "code_reviewer", outcome: "approve", started_at: at("55"), duration_ms: 17000 }),
      ],
    };
    const review = stepRows(task, workflow).find((row) => row.id === "review");
    expect(review.result).toEqual({ tone: "passed", word: "Approved after 1 send-back" });
    expect(review.runs).toBe(2);
  });
});

describe("a step moving up its role's models", () => {
  const moved = {
    role_id: "_builtin:orchestrator",
    agent_backend: "orchestrator",
    status: "completed",
    outcome: "success",
    outcome_detail: "Develop moves up to claude-opus-5-5 · the review sent it back twice",
  };

  it("is one sober line with its reason", () => {
    expect(runResult(moved)).toEqual({
      tone: "idle",
      word: "Moved up",
      note: "Develop moves up to claude-opus-5-5 · the review sent it back twice",
    });
  });

  it("says why a step ran on its model", () => {
    expect(modelSourceWords({ source: "override" })).toBe("set for this task");
    expect(modelSourceWords({ source: "ladder", moves_up: 1 })).toMatch(/moved up the role's models/);
    expect(modelSourceWords({ source: "ladder", moves_up: 0 })).toMatch(/first model/);
    expect(modelSourceWords({ source: "role" })).toBe("set by the role");
  });
});
