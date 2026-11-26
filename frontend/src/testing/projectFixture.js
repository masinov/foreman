// API answers for the project page, on top of the workspace's.
import { counts, MERGE_ITEM, milestone, needsYouPage, on, UNBLOCK_ITEM, workspaceRoutes } from "./workspaceFixture";

export const QUEUE_URL = "GET /api/v1/projects/foreman/sprints?status=active&status=planned&order=queue";
export const LATEST_FINISHED_URL = "GET /api/v1/projects/foreman/sprints?status=completed&limit=1&order=recent";
export const PROJECT_NEEDS_YOU_URL = "GET /api/v1/projects/foreman/needs-you?limit=5&offset=0";

export function finishedUrl({ q = "", offset = 0 } = {}) {
  const query = q ? `&q=${encodeURIComponent(q)}` : "";
  return `GET /api/v1/projects/foreman/sprints?status=completed${query}&limit=10&offset=${offset}&order=recent`;
}

export function milestonesUrl({ kinds = [], offset = 0 } = {}) {
  const query = kinds.map((kind) => `kind=${kind}&`).join("");
  return `GET /api/v1/projects/foreman/milestones?${query}limit=25&offset=${offset}`;
}

export function sprint(id, title, status, fields = {}) {
  return {
    id,
    project_id: "foreman",
    title,
    goal: null,
    status,
    order_index: 0,
    started_at: null,
    completed_at: null,
    task_counts: { ...counts(), total: 0 },
    totals: { total_cost_usd: 0 },
    ...fields,
  };
}

export const ACTIVE = sprint("sprint-56", "Sprint 56: engine truthfulness", "active", {
  goal: "What the engine records is what happened.",
  started_at: on("11-11"),
  task_counts: { ...counts({ blocked: 3, done: 1 }), total: 4 },
  totals: { total_cost_usd: 1.314 },
});

export const PLANNED = sprint("sprint-57", "Sprint 57: next", "planned", { order_index: 1 });

/** Twelve finished sprints, newest first: Sprint 55 down to Sprint 44. */
export const FINISHED = Array.from({ length: 12 }, (_, index) =>
  sprint(`sprint-${55 - index}`, `Sprint ${55 - index}: finished work ${index}`, "completed", {
    completed_at: on(`10-${String(28 - index).padStart(2, "0")}`),
    task_counts: { ...counts({ done: index + 1 }), total: index + 1 },
    totals: { total_cost_usd: 0.55 },
  }),
);

export function projectRoutes({ queue = [ACTIVE, PLANNED], finished = FINISHED, needsYou = [MERGE_ITEM, UNBLOCK_ITEM] } = {}) {
  const page = (items, offset) => ({ sprints: items.slice(offset, offset + 10), total: items.length });
  return {
    ...workspaceRoutes(),
    [PROJECT_NEEDS_YOU_URL]: needsYouPage(needsYou),
    [QUEUE_URL]: { sprints: queue, total: queue.length },
    [LATEST_FINISHED_URL]: { sprints: finished.slice(0, 1), total: finished.length },
    [finishedUrl()]: page(finished, 0),
    [finishedUrl({ offset: 10 })]: page(finished, 10),
    [milestonesUrl()]: {
      milestones: [
        milestone("sprint_started", { sprint_id: "sprint-56", sprint_title: "Sprint 56: engine truthfulness" }),
        milestone("engine_stopped", { at: on("11-10"), actor: "ana" }),
      ],
      total: 2,
    },
  };
}

// The backlog (ADR-0021): GET /projects/{id}/backlog.
export function backlogUrl({ q = "", offset = 0 } = {}) {
  const query = q ? `q=${encodeURIComponent(q)}&` : "";
  return `GET /api/v1/projects/foreman/backlog?${query}limit=25&offset=${offset}`;
}

export function backlogTask(id, title, state, fields = {}) {
  return {
    id,
    task_key: null,
    title,
    state,
    status: state === "filed" ? "triage" : "todo",
    task_type: "fix",
    priority: 0,
    description: null,
    acceptance_criteria: null,
    created_by: "human",
    created_at: on("11-09"),
    source: null,
    carried_from: null,
    ...fields,
  };
}

export const FILED = backlogTask("task-filed", "Retry the webhook on a timeout", "filed", {
  created_by: "manager",
  task_type: "feature",
});
export const ACCEPTED = [
  backlogTask("task-a", "Resume a stale agent step in place", "accepted", {
    carried_from: { id: "sprint-56", title: "Sprint 56: engine truthfulness" },
  }),
  backlogTask("task-b", "Check the lease fencing token on writes", "accepted", {
    source: { system: "github", external_ref: "42", url: null, reporter: "ada" },
  }),
  backlogTask("task-c", "JSON output on the remaining read commands", "accepted", { task_type: "feature" }),
];

/** What the API says of a project where Foreman starts backlog work on its own (ADR-0028). */
export const FOREMAN_STARTS = { starts: true, limit: 5, started: 1, ready: 3 };
const A_PERSON_PLANS = { starts: false, limit: 5, started: 0, ready: 0 };

export function backlogPayload(tasks, { triage = "human", total = tasks.length, foreman = A_PERSON_PLANS } = {}) {
  const count = (state) => tasks.filter((task) => task.state === state).length;
  return {
    project_id: "foreman",
    backlog_id: "foreman-backlog",
    triage,
    foreman,
    counts: { filed: count("filed"), accepted: count("accepted"), declined: 0 },
    tasks,
    total,
  };
}

export function backlogRoutes(tasks = [FILED, ...ACCEPTED], options) {
  return { ...projectRoutes(), [backlogUrl()]: backlogPayload(tasks, options) };
}
