import { segment } from "./client";

const KINDS = { role: "roles", workflow: "workflows" };

// A project's definitions live under the project; with no project id these
// are the workspace's, the defaults every project starts from.
const scope = (projectId) => (projectId ? `/projects/${segment(projectId)}` : "");

/**
 * The roles and workflows a project runs with (the defaults with the
 * project's own over them), or the workspace's defaults when `projectId` is
 * null, and `vocabulary`, the words an editor chooses from: tools,
 * decisions, models, what can do a step.
 */
export function getProjectDefinitions(client, projectId, options) {
  return client.get(`${scope(projectId)}/definitions`, options);
}

/**
 * Save one role or workflow. `body` is `{ fields }` from the form or
 * `{ text }`, the TOML itself; a new one also names `copy_of`, the
 * definition it starts from. Answers the definitions afterwards.
 */
export function saveDefinition(client, projectId, kind, id, body, options) {
  return client.put(`${scope(projectId)}/${KINDS[kind]}/${segment(id)}`, body, options);
}

/** Drop the scope's own text: the id goes back to the definition beneath it, or is gone. */
export function resetDefinition(client, projectId, kind, id, options) {
  return client.delete(`${scope(projectId)}/${KINDS[kind]}/${segment(id)}`, options);
}
