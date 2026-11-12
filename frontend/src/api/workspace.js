/**
 * The workspace overview (GET /api/v1/workspace): every project with its
 * engine, active sprint, needs-you and backlog counts and latest milestone.
 * Needs you and milestones have their own modules.
 */

/** Engine states the workspace and project payloads report. */
export const ENGINE_STATES = {
  running: "running",
  paused: "paused",
  notRunning: "not_running",
};

export function getWorkspace(client, options) {
  return client.get("/workspace", options).then((payload) => ({ projects: payload?.projects ?? [] }));
}
