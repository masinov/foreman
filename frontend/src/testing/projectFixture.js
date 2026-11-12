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
        milestone("task_merged", { at: on("11-10"), task_id: "task-m", task_key: "FOR-12", task_title: "Merged work" }),
      ],
      total: 2,
    },
  };
}
