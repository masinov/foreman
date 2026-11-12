import { segment } from "./client";

// Decision gates: the engine's proposals that a person settles, such as a
// sprint order conflict. A task waiting at a human-gate step is not one of
// these; see tasks.js.
export function listProjectGates(client, projectId, { status, ...options } = {}) {
  const query = status ? `?status=${segment(status)}` : "";
  return client
    .get(`/projects/${segment(projectId)}/gates${query}`, options)
    .then((payload) => payload?.gates ?? []);
}
