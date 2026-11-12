import { segment } from "./client";

export function getTask(client, taskId, options) {
  return client.get(`/tasks/${segment(taskId)}`, options);
}

/** Approve the human gate a task is waiting at. */
export function approveTask(client, taskId, options) {
  return client.post(`/tasks/${segment(taskId)}/approve`, undefined, options);
}
