import { DASHBOARD, normalizePath } from "./paths";

/**
 * The route table (ADR-0020, decision 6). Each route names its level, which
 * drives the breadcrumb, a title for the browser tab and the "being rebuilt"
 * page. `cli` (optional) returns the commands from docs/MANUAL.md that do the
 * same job in a terminal, for the "being rebuilt" page to name until the page
 * is built.
 *
 * Which routes have a page is decided in pages.js, not here.
 */
export const ROUTES = [
  {
    name: "workspace",
    pattern: "",
    level: "workspace",
    title: "Workspace",
  },
  {
    name: "workspace-settings",
    cli: () => ["foreman roles", "foreman workflows"],
    pattern: "/settings",
    level: "workspace",
    title: "Workspace settings",
  },
  {
    name: "project",
    pattern: "/projects/:projectId",
    level: "project",
    title: "Project, Sprints",
  },
  {
    name: "project-backlog",
    pattern: "/projects/:projectId/backlog",
    level: "project",
    title: "Project, Backlog",
  },
  {
    name: "project-activity",
    pattern: "/projects/:projectId/activity",
    level: "project",
    title: "Project, Activity",
  },
  {
    name: "project-settings",
    cli: ({ projectId }) => [`foreman config ${projectId}`],
    pattern: "/projects/:projectId/settings",
    level: "project",
    title: "Project settings, General",
  },
  {
    name: "project-settings-workflow",
    cli: ({ projectId }) => [`foreman config ${projectId}`, "foreman workflows"],
    pattern: "/projects/:projectId/settings/workflow",
    level: "project",
    title: "Project settings, Workflow",
  },
  {
    name: "sprint",
    cli: ({ sprintId }) => ["foreman board", `foreman watch --sprint ${sprintId}`],
    pattern: "/sprints/:sprintId",
    level: "sprint",
    title: "Sprint, list",
  },
  {
    name: "sprint-board",
    cli: () => ["foreman board"],
    pattern: "/sprints/:sprintId/board",
    level: "sprint",
    title: "Sprint, board",
  },
  {
    name: "task",
    cli: ({ taskId }) => [`foreman task show ${taskId}`, `foreman approve ${taskId}`, `foreman deny ${taskId}`],
    pattern: "/tasks/:taskId",
    level: "task",
    title: "Task, Overview",
  },
  {
    name: "task-changes",
    cli: ({ taskId }) => [`foreman task show ${taskId}`],
    pattern: "/tasks/:taskId/changes",
    level: "task",
    title: "Task, Changes",
  },
  {
    name: "task-checks",
    cli: ({ taskId }) => [`foreman task show ${taskId}`],
    pattern: "/tasks/:taskId/checks",
    level: "task",
    title: "Task, Checks",
  },
  {
    name: "task-activity",
    cli: ({ taskId }) => [`foreman history ${taskId}`],
    pattern: "/tasks/:taskId/activity",
    level: "task",
    title: "Task, Activity",
  },
];

export const NOT_FOUND = { name: "not-found", level: "workspace", title: "Not found" };

function compile(pattern) {
  const segments = `${DASHBOARD}${pattern}`.split("/").filter(Boolean);
  return (parts) => {
    if (parts.length !== segments.length) return null;
    const params = {};
    for (let index = 0; index < segments.length; index += 1) {
      const expected = segments[index];
      const actual = parts[index];
      if (expected.startsWith(":")) {
        try {
          params[expected.slice(1)] = decodeURIComponent(actual);
        } catch {
          return null;
        }
      } else if (expected !== actual) {
        return null;
      }
    }
    return params;
  };
}

const MATCHERS = ROUTES.map((route) => ({ route, match: compile(route.pattern) }));

/** Resolve a pathname to `{ route, params }`; unknown paths resolve to NOT_FOUND. */
export function matchRoute(pathname) {
  const parts = normalizePath(pathname).split("/").filter(Boolean);
  for (const { route, match } of MATCHERS) {
    const params = match(parts);
    if (params) return { route, params };
  }
  return { route: NOT_FOUND, params: {} };
}
