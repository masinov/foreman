// A request a page makes of the manager: "plan this sprint", "split this
// task". The page does not hold the manager's side bar, so it leaves the
// request here; the app opens the side bar and the side bar takes it.

let pending = null;
const listeners = new Set();

/**
 * Ask the manager. `request` is `{ projectId, says, plan }`: the line shown
 * as the person's message, and the plan the API is sent (`{ kind:
 * "plan_sprint", sprint_id }` or `{ kind: "split_task", task_id }`).
 */
export function askManager(request) {
  pending = request;
  for (const listener of [...listeners]) listener();
}

/** The waiting request for this project, once: taking it clears it. */
export function takeManagerRequest(projectId) {
  if (!pending || pending.projectId !== projectId) return null;
  const request = pending;
  pending = null;
  return request;
}

/** Run `listener` whenever a request is made. Returns how to stop. */
export function onManagerRequest(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function planSprintRequest(sprint) {
  return {
    projectId: sprint.project_id,
    says: `Plan this sprint: ${sprint.title}`,
    plan: { kind: "plan_sprint", sprint_id: sprint.id },
  };
}

export function splitTaskRequest(task) {
  return {
    projectId: task.project_id,
    says: `Split this task: ${task.title}`,
    plan: { kind: "split_task", task_id: task.id },
  };
}
