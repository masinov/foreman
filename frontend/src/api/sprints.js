import { segment } from "./client";

export function listProjectSprints(client, projectId, options) {
  return client
    .get(`/projects/${segment(projectId)}/sprints`, options)
    .then((payload) => payload?.sprints ?? []);
}

export function getSprint(client, sprintId, options) {
  return client.get(`/sprints/${segment(sprintId)}`, options);
}

export function listSprintTasks(client, sprintId, options) {
  return client
    .get(`/sprints/${segment(sprintId)}/tasks`, options)
    .then((payload) => payload?.tasks ?? []);
}
