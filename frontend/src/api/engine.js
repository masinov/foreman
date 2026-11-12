import { segment } from "./client";

// The project's engine (one per project). Start brings up an engine that is
// not running, or resumes one that is; Pause and Stop steer a running one.

/** Start the engine, spawning one if none runs; it resumes a paused one. */
export function startEngine(client, projectId, options) {
  return client.post(`/projects/${segment(projectId)}/agent/start`, {}, options);
}

/** Resume a paused engine. The same request as Start: the engine decides. */
export const resumeEngine = startEngine;

/** Pause: no new work starts and the running step stops, its task resumable. */
export function pauseEngine(client, projectId, options) {
  return client.post(`/projects/${segment(projectId)}/agent/stop`, {}, options);
}

/** Stop: the running step stops, the engine releases its lock and exits. */
export function stopEngine(client, projectId, options) {
  return client.post(`/projects/${segment(projectId)}/engine/commands`, { command: "shutdown" }, options);
}
