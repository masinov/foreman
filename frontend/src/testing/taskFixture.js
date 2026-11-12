// API answers for the task page, shaped like foreman/dashboard_service.py
// (get_task) and foreman/dashboard/task_models.py, on top of the sprint's.
import { sprintRoutes, WORKFLOW_URL } from "./sprintFixture";
import { on } from "./workspaceFixture";

export const TASK_ID = "task-merge";
export const TASK_URL = `GET /api/v1/tasks/${TASK_ID}`;
export const CHECKS_URL = `GET /api/v1/tasks/${TASK_ID}/checks`;
export const CHANGES_URL = `GET /api/v1/tasks/${TASK_ID}/changes`;
export const RUNS_URL = `GET /api/v1/tasks/${TASK_ID}/runs?limit=25&offset=0`;
export const diffUrl = (path) => `GET /api/v1/tasks/${TASK_ID}/changes/diff?path=${encodeURIComponent(path)}`;
export const outputUrl = (runId) => `GET /api/v1/runs/${runId}/output`;
export const post = (action) => `POST /api/v1/tasks/${TASK_ID}/${action}`;

export const COMMIT = "b232eb1c0ffee00000000000000000000000000";
const at = (minute) => on("11-11").replace(":00:00Z", `:0${minute}:00Z`);

export function run(id, step, fields = {}) {
  return {
    id,
    role_id: step === "test" ? "_builtin:run_tests" : "developer",
    workflow_step: step,
    agent_backend: step === "test" ? "builtin" : "claude_code",
    status: "completed",
    outcome: "done",
    token_count: 1000,
    cost_usd: 0.1,
    duration_ms: 7000,
    created_at: on("11-11"),
    started_at: on("11-11"),
    completed_at: on("11-11"),
    model: step === "test" ? null : "sonnet-5-5",
    ...fields,
  };
}

/** FOR-14, waiting at the merge gate, as in docs/design/dashboard-v7/05. */
export function taskDetail(fields = {}) {
  return {
    id: TASK_ID,
    project_id: "foreman",
    sprint_id: "sprint-56",
    task_key: "FOR-14",
    title: "Make the test step report what happened",
    status: "blocked",
    in_backlog: false,
    task_type: "fix",
    description: "The test step says only pass or fail.\nIt should say how long and what the runner printed.",
    priority: 0,
    branch_name: "foreman/for-14",
    created_by: "human",
    created_at: on("11-10"),
    blocked_reason: "Waiting for merge approval.",
    acceptance_criteria: "Duration is reported\nThe result line is reported",
    workflow_current_step: "merge_approval",
    awaiting_human_gate: true,
    gate_policy: "merge_approval",
    blocked_kind: "gate",
    guidance: [],
    source: null,
    policy: {
      triage: { value: "human", source: "built_in_default" },
      plan_approval: { value: "human", source: "built_in_default" },
      merge_approval: { value: "human", source: "project_default" },
      notification: { value: "attention", source: "built_in_default" },
    },
    totals: { run_count: 4, total_cost_usd: 0.72 },
    runs: [
      run("run-1", "develop", { outcome: "done", duration_ms: 64000, started_at: at(1), commit_sha: COMMIT }),
      run("run-2", "test", { outcome: "passed", duration_ms: 114200, started_at: at(2) }),
      // A reviewer leaves the branch where the developer left it.
      run("run-3", "review", { outcome: "approve", role_id: "code_reviewer", started_at: at(3), commit_sha: COMMIT }),
    ],
    ...fields,
  };
}

export function checksPayload(fields = {}) {
  return {
    task_id: TASK_ID,
    proof_status: "passed",
    outstanding: [],
    built_at: on("11-11"),
    facts: {
      tests: {
        status: "passed",
        exit_code: 0,
        duration_seconds: 114.2,
        command: "make test",
        result_line: "Ran 1221 tests in 114.2s OK",
        commit: "b232eb1aa0c0ffee",
        head_sha: "b232eb1aa0c0ffee",
      },
      branch: { name: "foreman/for-14", default_branch: "main", ahead: 3, behind: 0, state: "current" },
      size: { files: 3, added: 118, deleted: 7 },
    },
    claims: {
      reviews: [
        {
          kind: "code",
          decision: "approve",
          model: "sonnet-5-5",
          role_id: "code_reviewer",
          duration_seconds: 7,
          commit: "b232eb1aa0c0ffee",
          summary: "Clean change, tests cover it.",
          run_id: "run-3",
          current: true,
        },
      ],
      judged_by: "haiku-5-5",
      criteria: [
        { criterion: "Duration is reported", status: "passed", evidence: "builtins.py reports it" },
        { criterion: "The result line is reported", status: "partial", evidence: null },
      ],
    },
    evidence_files: [],
    ...fields,
  };
}

export const FILES = [
  { path: "foreman/builtins.py", status: "modified", added: 12, deleted: 7, binary: false, old_path: null },
  { path: "tests/test_builtins.py", status: "added", added: 96, deleted: 0, binary: false, old_path: null },
  { path: "docs/shot.png", status: "added", added: 0, deleted: 0, binary: true, old_path: null },
];

export function changesPayload(fields = {}) {
  return {
    task_id: TASK_ID,
    files: FILES,
    totals: { files: 3, added: 118, deleted: 7 },
    base: { branch: "main", sha: "aaaaaaa0000" },
    head: { branch: "foreman/for-14", sha: "b232eb1aa0c0ffee" },
    empty_reason: null,
    ...fields,
  };
}

export function diffPayload(path, diff, fields = {}) {
  return { task_id: TASK_ID, path, status: "modified", old_path: null, diff, truncated: false, cap_chars: 200000, total_chars: diff.length, ...fields };
}

export const BUILTINS_DIFF = ["--- a/foreman/builtins.py", "+++ b/foreman/builtins.py", "@@ -1,2 +1,2 @@", " keep", "-old line", "+new line"].join("\n");

export function runItem(id, step, fields = {}) {
  return {
    id,
    step,
    role_id: "developer",
    model: "sonnet-5-5",
    backend: "claude_code",
    status: "completed",
    outcome: "done",
    started_at: on("11-11"),
    finished_at: on("11-11"),
    duration_ms: 7000,
    cost_usd: 0.12,
    tokens: 1000,
    token_usage: {},
    ...fields,
  };
}

export function outputPayload(runId, text, fields = {}) {
  return {
    run_id: runId,
    task_id: TASK_ID,
    prompt: `The prompt of ${runId}`,
    prompt_truncated: false,
    transcript: [{ at: on("11-11"), kind: "agent.raw_output", stream: "stdout", text }],
    transcript_truncated: false,
    total_entries: 1,
    cap_chars: 200000,
    ...fields,
  };
}

export function taskRoutes({ task = taskDetail(), checks = checksPayload(), changes = changesPayload(), runs = null } = {}) {
  const runList = runs ?? [runItem("run-3", "review", { outcome: "approve", commit_sha: COMMIT }), runItem("run-2", "test", { backend: "builtin", model: null })];
  return {
    ...sprintRoutes(),
    [TASK_URL]: task,
    [CHECKS_URL]: checks,
    [CHANGES_URL]: changes,
    [RUNS_URL]: { runs: runList, total: runList.length, limit: 25, offset: 0 },
    [diffUrl("foreman/builtins.py")]: diffPayload("foreman/builtins.py", BUILTINS_DIFF),
    [outputUrl("run-3")]: outputPayload("run-3", "Reviewed the change."),
    [outputUrl("run-2")]: outputPayload("run-2", "Ran 1221 tests"),
    [WORKFLOW_URL]: {
      id: "development",
      name: "development",
      steps: [
        { id: "develop", role: "developer", policy: null },
        { id: "test", role: "_builtin:run_tests", policy: null },
        { id: "review", role: "code_reviewer", policy: null },
        { id: "merge_approval", role: "_builtin:human_gate", policy: "merge_approval" },
        { id: "merge", role: "_builtin:merge", policy: null },
        { id: "done", role: "_builtin:mark_done", policy: null },
      ],
    },
  };
}
