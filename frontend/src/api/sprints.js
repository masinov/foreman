import { queryString, segment } from "./client";

export const SPRINT_STATUSES = {
  active: "active",
  planned: "planned",
  completed: "completed",
  cancelled: "cancelled",
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

/** Change a sprint's title and goal. */
export function updateSprint(client, sprintId, { title, goal }, options) {
  return client.patch(`/sprints/${segment(sprintId)}`, { title, goal: goal || null }, options);
}

/** Move a sprint to `active` (activate it) or `completed` (finish it). */
export function transitionSprint(client, sprintId, status, options) {
  return client.patch(`/sprints/${segment(sprintId)}`, { status }, options);
}

/** The event type the engine records each time a workflow step finishes. */
export const STEP_FINISHED = "workflow.step_completed";

/**
 * Events of one sprint, newest first, as `{ events, hasMore }`. `types`
 * keeps only those event types; `before` is the id of the oldest event
 * already shown, so the next call returns older ones.
 */
export function listSprintEvents(client, sprintId, { types = [], limit, before, ...options } = {}) {
  const query = queryString({ type: types, limit, before });
  return client.get(`/sprints/${segment(sprintId)}/events${query}`, options).then((payload) => ({
    events: [...(payload?.events ?? [])].reverse(),
    hasMore: Boolean(payload?.has_more),
  }));
}

/**
 * Write a new task straight into a sprint. A person doing this has decided
 * both that the work is wanted and where it goes, so it skips the backlog.
 */
export function createSprintTask(
  client,
  sprintId,
  { title, taskType, description, acceptanceCriteria, complexity, dependsOn = [] },
  options,
) {
  return client.post(
    `/sprints/${segment(sprintId)}/tasks`,
    {
      title,
      task_type: taskType,
      description: description || null,
      acceptance_criteria: acceptanceCriteria || null,
      complexity: complexity || null,
      depends_on: dependsOn,
    },
    options,
  );
}

/** Move a planned sprint one place `up` or `down` the queue. */
export function moveSprint(client, sprintId, direction, options) {
  return client.post(`/sprints/${segment(sprintId)}/move`, { direction }, options);
}

/** Delete a sprint with its tasks, runs and history. */
export function deleteSprint(client, sprintId, options) {
  return client.delete(`/sprints/${segment(sprintId)}`, options);
}
