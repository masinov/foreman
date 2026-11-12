import { segment } from "./client";

export function listProjects(client, options) {
  return client.get("/projects", options).then((payload) => payload?.projects ?? []);
}

export function getProject(client, projectId, options) {
  return client.get(`/projects/${segment(projectId)}`, options);
}

/** The steps of the project's workflow, in the order its definition lists them. */
export function getProjectWorkflow(client, projectId, options) {
  return client.get(`/projects/${segment(projectId)}/workflow`, options);
}
