// API answers shaped like foreman/dashboard_overview.py and
// foreman/dashboard_service.py, for page tests.

// Dates in this year, so they print without a year whenever the tests run.
export const YEAR = new Date().getFullYear();
export const on = (monthDay) => `${YEAR}-${monthDay}T12:00:00Z`;

export function counts(overrides = {}) {
  return { triage: 0, todo: 0, in_progress: 0, blocked: 0, done: 0, cancelled: 0, ...overrides };
}

export function engine(state = "not_running", task = null) {
  return {
    state,
    task_id: task?.id ?? null,
    task_key: task?.task_key ?? null,
    task_title: task?.title ?? null,
    step: task?.step ?? null,
  };
}

export function milestone(kind, fields = {}) {
  return {
    kind,
    at: on("11-11"),
    project_id: "foreman",
    project_name: "Foreman",
    sprint_id: null,
    sprint_title: null,
    task_id: null,
    task_key: null,
    task_title: null,
    actor: null,
    ...fields,
  };
}

export const MERGE_ITEM = {
  kind: "approve_merge",
  project_id: "foreman",
  project_name: "Foreman",
  sprint_id: "sprint-56",
  sprint_title: "Sprint 56: engine truthfulness",
  task_id: "task-merge",
  task_key: "FOR-14",
  task_title: "Make the test step report what happened",
  since: on("11-11"),
  evidence: {
    tests_status: "passed",
    tested_sha: "b232eb1aa0c0ffee",
    review_outcome: "approved",
    reviewed_sha: "b232eb1aa0c0ffee",
    head_sha: "b232eb1aa0c0ffee",
    proof_status: null,
  },
};

export const UNBLOCK_ITEM = {
  kind: "unblock",
  project_id: "foreman",
  project_name: "Foreman",
  sprint_id: "sprint-56",
  sprint_title: "Sprint 56: engine truthfulness",
  task_id: "task-stuck",
  task_key: "FOR-15",
  task_title: "Send triage events through the dispatcher",
  since: on("11-10"),
};

export function needsYouPage(items) {
  return { items, total: items.length, limit: 5, offset: 0 };
}

export function workspacePayload({ withGateTask = true } = {}) {
  const waiting = withGateTask ? 2 : 0;
  return {
    projects: [
      {
        id: "foreman",
        name: "Foreman",
        repo_path: "/srv/foreman",
        default_branch: "main",
        workflow_id: "development",
        engine: engine("running", { id: "task-x", task_key: "FOR-13", title: "x", step: "develop" }),
        active_sprint: {
          id: "sprint-56",
          title: "Sprint 56: engine truthfulness",
          task_counts: withGateTask ? counts({ blocked: 2, todo: 1, done: 1 }) : counts({ todo: 1, done: 1 }),
          needs_you: waiting,
          spend_usd: 1.314,
        },
        needs_you: waiting,
        backlog: 4,
        latest_milestone: milestone("sprint_started", {
          sprint_id: "sprint-56",
          sprint_title: "Sprint 56: engine truthfulness",
        }),
      },
      {
        id: "other",
        name: "Other project",
        repo_path: "/srv/other",
        default_branch: "trunk",
        workflow_id: "development",
        engine: engine("not_running"),
        active_sprint: null,
        needs_you: 0,
        backlog: 0,
        latest_milestone: null,
      },
    ],
  };
}

export const RECENT = [
  milestone("sprint_started", { sprint_id: "sprint-56", sprint_title: "Sprint 56: engine truthfulness" }),
  milestone("sprint_finished", {
    at: on("11-10"),
    sprint_id: "sprint-55",
    sprint_title: "Sprint 55: baseline and host safety",
  }),
  milestone("engine_paused", { at: on("11-09"), project_id: "other", project_name: "Other project", actor: "ana" }),
];

export function workspaceRoutes({ withGateTask = true } = {}) {
  const items = withGateTask ? [MERGE_ITEM, UNBLOCK_ITEM] : [];
  return {
    "GET /api/v1/workspace": workspacePayload({ withGateTask }),
    "GET /api/v1/needs-you?limit=5&offset=0": needsYouPage(items),
    "GET /api/v1/milestones?limit=10": { milestones: RECENT, total: RECENT.length, limit: 10, offset: 0 },
  };
}
