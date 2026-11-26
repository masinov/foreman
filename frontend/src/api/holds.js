import { segment } from "./client";

// A user's holds on work (ADR-0043). Pause lets a running step finish and
// then nothing after it starts; Stop cuts the step now; Resume lifts pauses.
// On a sprint or the workspace, Pause, Stop and Resume act on each task in
// it. Block holds a sprint or the workspace, with a reason, until Unblock.
// Each answer names the tasks it changed (`task_ids`, `task_keys`).

const task = (taskId) => `/tasks/${segment(taskId)}`;
const sprint = (sprintId) => `/sprints/${segment(sprintId)}`;

export function pauseTask(client, taskId, options) {
  return client.post(`${task(taskId)}/pause`, {}, options);
}

export function stopTask(client, taskId, options) {
  return client.post(`${task(taskId)}/stop`, {}, options);
}

export function resumeTask(client, taskId, options) {
  return client.post(`${task(taskId)}/resume`, {}, options);
}

export function pauseSprint(client, sprintId, options) {
  return client.post(`${sprint(sprintId)}/pause`, {}, options);
}

export function stopSprint(client, sprintId, options) {
  return client.post(`${sprint(sprintId)}/stop`, {}, options);
}

export function resumeSprint(client, sprintId, options) {
  return client.post(`${sprint(sprintId)}/resume`, {}, options);
}

export function blockSprint(client, sprintId, reason, options) {
  return client.post(`${sprint(sprintId)}/block`, { reason }, options);
}

export function unblockSprint(client, sprintId, options) {
  return client.post(`${sprint(sprintId)}/unblock`, {}, options);
}

export function pauseAll(client, options) {
  return client.post("/workspace/pause", {}, options);
}

export function stopAll(client, options) {
  return client.post("/workspace/stop", {}, options);
}

export function resumeAll(client, options) {
  return client.post("/workspace/resume", {}, options);
}

export function blockAll(client, reason, options) {
  return client.post("/workspace/block", { reason }, options);
}

export function unblockAll(client, options) {
  return client.post("/workspace/unblock", {}, options);
}
