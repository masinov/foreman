/**
 * The workspace overview (GET /api/v1/workspace): every project with its
 * engine, active sprint, needs-you and backlog counts and latest milestone.
 * Needs you and milestones have their own modules.
 */

/** Whether a worker holds a project (ADR-0043): the program, not the work. */
export const ENGINE_STATES = {
  running: "running",
  notRunning: "not_running",
};

/** Every project, and the workspace's block when it is blocked. */
export function getWorkspace(client, options) {
  return client
    .get("/workspace", options)
    .then((payload) => ({ projects: payload?.projects ?? [], block: payload?.block ?? null }));
}
