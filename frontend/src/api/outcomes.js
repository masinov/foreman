import { queryString, segment } from "./client";

/**
 * How well a project's agents do (ADR-0034), for the whole project or one
 * sprint: tasks that passed first time, send-backs by cause, a person's part,
 * cost per merged task, time to merge, and the same per role and model.
 */
export function getOutcomes(client, projectId, { sprintId = null } = {}, options) {
  return client.get(`/projects/${segment(projectId)}/outcomes${queryString({ sprint: sprintId })}`, options);
}
