import { queryString, segment } from "./client";

/** The states a backlog task is in (ADR-0021): filed, accepted or declined. */
export const BACKLOG_STATES = {
  filed: "filed",
  accepted: "accepted",
  declined: "declined",
};

// The kinds of task a person can file; the same list the API accepts.
export const TASK_TYPES = ["feature", "fix", "refactor", "docs", "spike", "chore"];

/**
 * One page of a project's backlog as `{ items, total, meta }`. `meta` is
 * `{ counts, triage }`: how many tasks are in each state across the whole
 * backlog, and who accepts filed work in this project (`human` or `auto`).
 * `q` matches on the server; without `statuses` the API lists filed and
 * accepted work, filed first.
 */
export function listBacklog(client, projectId, { statuses = [], q, limit, offset, ...options } = {}) {
  const query = queryString({ status: statuses, q, limit, offset });
  return client.get(`/projects/${segment(projectId)}/backlog${query}`, options).then((payload) => ({
    items: payload?.tasks ?? [],
    total: payload?.total ?? 0,
    meta: { counts: payload?.counts ?? {}, triage: payload?.triage ?? "human" },
  }));
}

/** File a task into the backlog. The project's triage policy decides if it is accepted. */
export function fileBacklogTask(client, projectId, { title, taskType, description, acceptanceCriteria }, options) {
  return client.post(
    `/projects/${segment(projectId)}/backlog`,
    {
      title,
      task_type: taskType,
      description: description || null,
      acceptance_criteria: acceptanceCriteria || null,
    },
    options,
  );
}

export function acceptTask(client, taskId, options) {
  return client.post(`/tasks/${segment(taskId)}/accept`, undefined, options);
}

export function declineTask(client, taskId, options) {
  return client.post(`/tasks/${segment(taskId)}/decline`, {}, options);
}

/**
 * Plan accepted tasks into a sprint: `{ sprintId }` for an existing planned or
 * active one, `{ newSprint: { title, goal } }` for a new planned one.
 */
export function planBacklog(client, projectId, { taskIds, sprintId, newSprint }, options) {
  const body = { task_ids: taskIds };
  if (sprintId) body.sprint_id = sprintId;
  else body.new_sprint = { title: newSprint.title, goal: newSprint.goal || null };
  return client.post(`/projects/${segment(projectId)}/backlog/plan`, body, options);
}
