// API answers shaped like foreman/dashboard_service.py, for workspace tests.

export function engine(state = "stopped", currentTask = null) {
  return { resident: state !== "stopped", paused: state === "paused", state, current_task: currentTask };
}

export function counts(overrides = {}) {
  return { triage: 0, todo: 0, in_progress: 0, blocked: 0, done: 0, cancelled: 0, ...overrides };
}

export function workspaceRoutes({ withGateTask = true } = {}) {
  const sprintCounts = withGateTask ? counts({ blocked: 2, todo: 1, done: 1 }) : counts({ todo: 1 });
  const tasks = withGateTask
    ? [
        {
          id: "task-merge",
          task_key: "FOR-14",
          title: "Make the test step report what happened",
          status: "blocked",
          awaiting_human_gate: true,
          blocked_kind: "gate",
          workflow_current_step: "merge_approval",
          blocked_reason: null,
          source: null,
        },
        {
          id: "task-stuck",
          task_key: "FOR-15",
          title: "Send triage events through the dispatcher",
          status: "blocked",
          awaiting_human_gate: false,
          blocked_kind: "engine",
          workflow_current_step: "develop",
          blocked_reason: "Agent exited without a completion marker",
          source: null,
        },
        { id: "task-todo", task_key: "FOR-16", title: "Something to do", status: "todo", awaiting_human_gate: false, blocked_kind: null },
      ]
    : [];

  return {
    "GET /api/v1/projects": {
      projects: [
        {
          id: "foreman",
          name: "Foreman",
          engine: engine("resident", {
            id: "task-x",
            task_key: "FOR-13",
            title: "x",
            status: "in_progress",
            workflow_current_step: "develop",
          }),
        },
        { id: "other", name: "Other project", engine: engine("stopped") },
      ],
    },
    "GET /api/v1/projects/foreman": {
      id: "foreman",
      name: "Foreman",
      repo_path: "/srv/foreman",
      default_branch: "main",
    },
    "GET /api/v1/projects/other": { id: "other", name: "Other project", repo_path: "/srv/other", default_branch: "trunk" },
    "GET /api/v1/projects/foreman/sprints": {
      sprints: [
        {
          id: "sprint-56",
          title: "Sprint 56: engine truthfulness",
          status: "active",
          task_counts: { ...sprintCounts, total: 4 },
          totals: { total_cost_usd: 1.314 },
        },
        { id: "sprint-57", title: "Sprint 57", status: "planned", task_counts: counts(), totals: { total_cost_usd: 0 } },
      ],
    },
    "GET /api/v1/projects/other/sprints": {
      sprints: [
        { id: "sprint-o", title: "Later", status: "planned", task_counts: counts(), totals: { total_cost_usd: 0 } },
      ],
    },
    "GET /api/v1/projects/foreman/gates?status=pending": { gates: [] },
    "GET /api/v1/projects/other/gates?status=pending": { gates: [] },
    "GET /api/v1/sprints/sprint-56/tasks": { tasks },
    "GET /api/v1/tasks/task-merge": {
      id: "task-merge",
      completion_evidence: {
        tests_status: "passed",
        review_outcome: "approved",
        security_review_outcome: "",
        head_sha: "b232eb1aa0c0ffee",
      },
    },
  };
}
