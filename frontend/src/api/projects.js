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

/**
 * A project's settings: `settings` as stored, `effective` with every default
 * filled in, and `host_level_settings`, the keys the dashboard shows but
 * cannot change (ADR-0017).
 */
export function getProjectSettings(client, projectId, options) {
  return client.get(`/projects/${segment(projectId)}/settings`, options);
}

/**
 * Change settings. `settings` holds only the keys that change. A refusal's
 * error carries `field`, the key it is about, when the API knows it.
 */
export function updateProjectSettings(client, projectId, { settings, workflowId } = {}, options) {
  const body = {};
  if (settings) body.settings = settings;
  if (workflowId) body.workflow_id = workflowId;
  return client.patch(`/projects/${segment(projectId)}/settings`, body, options);
}

/** Every workflow a project can use, each with its steps, transitions and roles. */
export function listWorkflows(client, options) {
  return client.get("/workflows", options).then((payload) => payload?.workflows ?? []);
}

/** Register a repository on this machine as a project. */
export function createProject(client, { name, repoPath, workflowId }, options) {
  return client.post("/projects", { name, repo_path: repoPath, workflow_id: workflowId }, options);
}
