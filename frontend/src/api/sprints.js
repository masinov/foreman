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

/**
 * Write a new task straight into a sprint. A person doing this has decided
 * both that the work is wanted and where it goes, so it skips the backlog.
 */
export function createSprintTask(
  client,
  sprintId,
  { title, taskType, description, acceptanceCriteria, restsOn = [], dependsOn = [] },
  options,
) {
  return client.post(
    `/sprints/${segment(sprintId)}/tasks`,
    {
      title,
      task_type: taskType,
      description: description || null,
      acceptance_criteria: acceptanceCriteria || null,
      rests_on: restsOn,
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

/**
 * One page of a sprint's activity, newest first, as `{ items, total }`: each
 * run of its tasks that did work, and what a person did to one by hand. Each
 * carries its task's id, key and title. `problems` keeps only what sent a task
 * back or stopped it.
 */
export function listSprintActivity(client, sprintId, { problems = false, by = null, limit, offset, ...options } = {}) {
  return client
    .get(
      `/sprints/${segment(sprintId)}/activity${queryString({ only: problems ? "problems" : null, by: by || null, limit, offset })}`,
      options,
    )
    .then((payload) => ({ items: payload?.items ?? [], total: payload?.total ?? 0, meta: { who: payload?.who ?? [] } }));
}
