import { queryString, segment } from "./client";

const task = (taskId) => `/tasks/${segment(taskId)}`;

export function getTask(client, taskId, options) {
  return client.get(task(taskId), options);
}

/** Change a task's title, type, description and acceptance criteria. */
export function updateTask(client, taskId, { title, taskType, description, acceptanceCriteria }, options) {
  return client.patch(
    task(taskId),
    {
      title,
      task_type: taskType,
      description: description || null,
      acceptance_criteria: acceptanceCriteria || null,
    },
    options,
  );
}

/**
 * Replace a task's overrides (who decides, the model for a step). The whole
 * object is sent; an empty one clears every override.
 */
export function setTaskOverrides(client, taskId, executorOverrides, options) {
  return client.patch(task(taskId), { executor_overrides: executorOverrides }, options);
}

// The decision a person takes at a human gate (plan or merge approval).

/** Approve the human gate a task is waiting at. */
export function approveTask(client, taskId, options) {
  return client.post(`${task(taskId)}/approve`, undefined, options);
}

/** Send a task back from its gate; the note is read by the next agent step. */
export function denyTask(client, taskId, note, options) {
  return client.post(`${task(taskId)}/deny`, { note: note || null }, options);
}

// What a person does to a task from its page.

/** Ask the engine to stop the step it is running; the engine blocks the task. */
export function stopTask(client, taskId, options) {
  return client.post(`${task(taskId)}/stop`, {}, options);
}

/** Park a task with a reason. */
export function blockTask(client, taskId, reason, options) {
  return client.post(`${task(taskId)}/block`, { reason }, options);
}

/** Return a blocked task to the queue; `note` is guidance for its next agent step. */
export function unblockTask(client, taskId, note, options) {
  return client.post(`${task(taskId)}/unblock`, { note: note || null }, options);
}

export function cancelTask(client, taskId, options) {
  return client.post(`${task(taskId)}/cancel`, undefined, options);
}

export function deleteTask(client, taskId, options) {
  return client.delete(task(taskId), options);
}

/** Record guidance for the task's next agent step. */
export function sendGuidance(client, taskId, text, options) {
  return client.post(`${task(taskId)}/messages`, { text }, options);
}

// Reads for the task page's tabs (sprint 58, slice 7).

/** The files the task's branch changed against the default branch, with totals. */
export function getTaskChanges(client, taskId, options) {
  return client.get(`${task(taskId)}/changes`, options);
}

/** One changed file's unified diff. */
export function getFileDiff(client, taskId, path, options) {
  return client.get(`${task(taskId)}/changes/diff${queryString({ path })}`, options);
}

/** Checks as facts (measured by the engine) and claims (reported by an agent). */
export function getTaskChecks(client, taskId, options) {
  return client.get(`${task(taskId)}/checks`, options);
}

/** One page of the task's runs, newest first, as `{ items, total }`. */
export function listTaskRuns(client, taskId, { limit, offset, ...options } = {}) {
  return client
    .get(`${task(taskId)}/runs${queryString({ limit, offset })}`, options)
    .then((payload) => ({ items: payload?.runs ?? [], total: payload?.total ?? 0 }));
}

/** What a run was given (its prompt) and what it did (its transcript). */
export function getRunOutput(client, runId, options) {
  return client.get(`/runs/${segment(runId)}/output`, options);
}
