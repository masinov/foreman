import { queryString, segment } from "./client";

export const SPRINT_STATUSES = {
  active: "active",
  planned: "planned",
  completed: "completed",
};

/**
 * One page of a project's sprints as `{ items, total }`. `statuses` filters,
 * `q` matches the title or id on the server, `order` is `queue` (the order
 * they run in) or `recent` (latest finished first). Without `limit`, every
 * matching sprint.
 */
export function listProjectSprints(
  client,
  projectId,
  { statuses = [], q, limit, offset, order, ...options } = {},
) {
  const query = queryString({ status: statuses, q, limit, offset, order });
  return client
    .get(`/projects/${segment(projectId)}/sprints${query}`, options)
    .then((payload) => ({ items: payload?.sprints ?? [], total: payload?.total ?? 0 }));
}

/** Create a planned sprint at the end of the queue. */
export function createSprint(client, projectId, { title, goal }, options) {
  return client.post(`/projects/${segment(projectId)}/sprints`, { title, goal: goal || null }, options);
}

export function getSprint(client, sprintId, options) {
  return client.get(`/sprints/${segment(sprintId)}`, options);
}

export function listSprintTasks(client, sprintId, options) {
  return client
    .get(`/sprints/${segment(sprintId)}/tasks`, options)
    .then((payload) => payload?.tasks ?? []);
}
