import { stepRows } from "../task/taskWords";
import { FOREMAN, runBy, runResult } from "./activityWords";

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

describe("how a run ended", () => {
  it("says a send-back is one, with the reviewer's reason", () => {
    const steer = run({ role_id: "code_reviewer", outcome: "steer", outcome_detail: "The log can still contain the host and port." });
    expect(runResult(steer)).toEqual({ tone: "attention", word: "Sent back", note: "The log can still contain the host and port." });
    const denied = run({ role_id: "_builtin:human_gate", agent_backend: "human", outcome: "deny", outcome_detail: "Use the helper." });
    expect(runResult(denied)).toEqual({ tone: "attention", word: "Sent back", note: "Use the helper." });
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
