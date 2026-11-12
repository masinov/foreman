// API answers for the sprint page, on top of the workspace's.
import { counts, on, workspaceRoutes } from "./workspaceFixture";

export const SPRINT_URL = "GET /api/v1/sprints/sprint-56";
export const TASKS_URL = "GET /api/v1/sprints/sprint-56/tasks";
export const WORKFLOW_URL = "GET /api/v1/projects/foreman/workflow";
export const STEPS_URL = "GET /api/v1/sprints/sprint-56/events?type=workflow.step_completed&limit=25";
export const ACCEPTED_URL = "GET /api/v1/projects/foreman/backlog?status=accepted&limit=25&offset=0";

export function sprintPayload(fields = {}) {
  return {
    id: "sprint-56",
    project_id: "foreman",
    title: "Sprint 56: engine truthfulness",
    goal: "What the engine records is what happened.",
    status: "active",
    started_at: on("11-11"),
    completed_at: null,
    picks_own_tasks: false,
    task_counts: { ...counts({ blocked: 1, in_progress: 1, todo: 2, done: 1 }), total: 5 },
    totals: { total_cost_usd: 1.314, total_token_count: 28500, run_count: 12 },
    ...fields,
  };
}

export function taskPayload(id, key, status, fields = {}) {
  return {
    id,
    project_id: "foreman",
    sprint_id: "sprint-56",
    task_key: key,
    title: `Title of ${key}`,
    status,
    workflow_current_step: null,
    awaiting_human_gate: false,
    gate_policy: null,
    checks: null,
    totals: { run_count: 0, total_cost_usd: 0 },
    ...fields,
  };
}

/** Deliberately out of order: the page must sort them. */
export const TASKS = [
  taskPayload("t-done", "FOR-10", "done", {
    workflow_current_step: "done",
    checks: { tests: "passed", review: "approve", commit: "aaaaaaa1111" },
    totals: { run_count: 4, total_cost_usd: 0.4 },
  }),
  taskPayload("t-q1", "FOR-17", "todo"),
  taskPayload("t-run", "FOR-13", "in_progress", { workflow_current_step: "test" }),
  taskPayload("t-merge", "FOR-14", "blocked", {
    workflow_current_step: "merge_approval",
    awaiting_human_gate: true,
    gate_policy: "merge_approval",
    checks: { tests: "passed", review: "approve", commit: "b232eb1aa0c0ffee" },
    totals: { run_count: 12, total_cost_usd: 0.72 },
  }),
  taskPayload("t-q2", "FOR-18", "todo"),
];

export const WORKFLOW = {
  id: "development",
  name: "Development",
  steps: [
    { id: "develop", role: "developer", policy: null },
    { id: "test", role: "_builtin:run_tests", policy: null },
    { id: "review", role: "code_reviewer", policy: null },
    { id: "merge_approval", role: "_builtin:human_gate", policy: "merge_approval" },
    { id: "merge", role: "_builtin:merge", policy: null },
    { id: "done", role: "_builtin:mark_done", policy: null },
  ],
};

export function stepEvent(id, taskId, step, outcome, at = on("11-11")) {
  return { id, task_id: taskId, project_id: "foreman", event_type: "workflow.step_completed", timestamp: at, role_id: "x", payload: { step, outcome } };
}

export function sprintRoutes({ sprint = sprintPayload(), tasks = TASKS, workflow = WORKFLOW, events = [] } = {}) {
  return {
    ...workspaceRoutes(),
    [SPRINT_URL]: sprint,
    [TASKS_URL]: { tasks },
    [WORKFLOW_URL]: workflow,
    [STEPS_URL]: { events, has_more: false },
    [ACCEPTED_URL]: { tasks: [], total: 0, counts: {}, triage: "human" },
  };
}

