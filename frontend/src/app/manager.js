import { useCallback, useEffect, useState } from "react";

import { getSprint } from "../api/sprints";
import { getTask } from "../api/tasks";
import { useResource } from "../api/useResource";

// Whether the manager side bar is open is remembered per browser, so it stays
// as it was across pages and reloads.
const STORAGE_KEY = "foreman.dashboard.manager.open";

function defaultStorage() {
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}

export function readManagerOpen(storage = defaultStorage()) {
  try {
    return storage?.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

function writeManagerOpen(open, storage = defaultStorage()) {
  try {
    storage?.setItem(STORAGE_KEY, open ? "true" : "false");
  } catch {
    // Storage may be full or blocked; the bar still works for this visit.
  }
}

/** `[open, setOpen]`, remembered in this browser. */
export function useManagerOpen() {
  const [open, setOpenState] = useState(() => readManagerOpen());
  const setOpen = useCallback((next) => {
    setOpenState((previous) => {
      const value = typeof next === "function" ? next(previous) : next;
      writeManagerOpen(value);
      return value;
    });
  }, []);
  return [open, setOpen];
}

const PROJECT_PAGES = {
  project: "Sprints",
  "project-backlog": "Backlog",
  "project-activity": "Activity",
  "project-settings": "Settings",
  "project-settings-workflow": "Workflow settings",
  "project-settings-roles": "Role settings",
};

/**
 * The page the person is on, for "You are on: ...": a project's tab or a
 * sprint's title. Null until a sprint has loaded, and for pages the manager
 * is not on (the workspace's; a task's, where the side bar is its agents').
 */
export function youAreOn(route, { sprint = null } = {}) {
  if (route.level === "project") return PROJECT_PAGES[route.name] || null;
  if (route.level === "sprint") return sprint?.title || null;
  return null;
}

/**
 * What the side bar needs from the route: the project the page is in and,
 * for the manager, the "You are on" label and the context sent with a
 * message. A sprint or task page learns its project from the sprint or task.
 * On a task page the side bar is the task's agents' and `task` is that task.
 * `hasManager` (a side bar at all) is false on workspace pages.
 */
export function useManagerTarget(route, params) {
  const sprintId = route.level === "sprint" ? params.sprintId : null;
  const taskId = route.level === "task" ? params.taskId : null;
  const { data: sprint } = useResource(["sprint", sprintId], (client, options) => getSprint(client, sprintId, options), {
    enabled: Boolean(sprintId),
  });
  const { data: task } = useResource(["task", taskId], (client, options) => getTask(client, taskId, options), {
    enabled: Boolean(taskId),
  });

  const hasManager = route.level === "project" || route.level === "sprint" || route.level === "task";
  let projectId = null;
  if (route.level === "project") projectId = params.projectId;
  else if (sprintId) projectId = sprint?.project_id || null;
  else if (taskId) projectId = task?.project_id || null;

  const page = youAreOn(route, { sprint });
  const context = { page: page || undefined };
  if (sprintId) context.sprint_id = sprintId;
  return { hasManager, projectId, page, context, task: taskId && task?.id === taskId ? task : null };
}

/**
 * Below this width the manager side bar covers the page instead of sitting
 * beside it (shell.css; a media query cannot read a custom property, so
 * tokens.css records the breakpoint and this repeats it).
 */
export const OVERLAY_QUERY = "(max-width: 960px)";

function overlayMatches() {
  try {
    return Boolean(globalThis.matchMedia?.(OVERLAY_QUERY).matches);
  } catch {
    return false;
  }
}

/** True while the side bar covers the page, kept current as the window changes. */
export function useOverlay() {
  const [overlay, setOverlay] = useState(overlayMatches);
  useEffect(() => {
    const list = globalThis.matchMedia?.(OVERLAY_QUERY);
    if (!list?.addEventListener) return undefined;
    const update = () => setOverlay(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, []);
  return overlay;
}
