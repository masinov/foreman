import { segment } from "./client";

const KINDS = { role: "roles", workflow: "workflows" };

/**
 * The roles and workflows a project runs with (the shipped ones with the
 * project's own over them) and `vocabulary`, the words an editor chooses
 * from: tools, decisions, models, what can do a step.
 */
export function getProjectDefinitions(client, projectId, options) {
  return client.get(`/projects/${segment(projectId)}/definitions`, options);
}

/**
 * Save one role or workflow for a project. `body` is `{ fields }` from the
 * form or `{ text }`, the TOML itself; a new one also names `copy_of`, the
 * definition it starts from. Answers the project's definitions afterwards.
 */
export function saveDefinition(client, projectId, kind, id, body, options) {
  return client.put(`/projects/${segment(projectId)}/${KINDS[kind]}/${segment(id)}`, body, options);
}

/** Drop the project's own text: a shipped id goes back to the shipped definition, any other is gone. */
export function resetDefinition(client, projectId, kind, id, options) {
  return client.delete(`/projects/${segment(projectId)}/${KINDS[kind]}/${segment(id)}`, options);
}
