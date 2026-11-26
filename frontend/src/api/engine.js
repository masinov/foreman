import { segment } from "./client";

// The program that runs a project's work: its worker (ADR-0043). Whether the
// work may go on is a user's holds on it (holds.js), not the worker's state.

/** Start a worker for a project none runs. It works on whatever is started and not held. */
export function startWorker(client, projectId, options) {
  return client.post(`/projects/${segment(projectId)}/agent/start`, {}, options);
}

/**
 * Put a task first in line. Queued for the worker, so it holds whether or not
 * one is up; one is started if none is running. Refused for a held task.
 */
export function runTaskNext(client, projectId, taskId, options) {
  return client.post(`/projects/${segment(projectId)}/agent/start`, { task_id: taskId }, options);
}
