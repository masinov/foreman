import { DASHBOARD, legacyPaths, normalizePath } from "./paths";

/**
 * The route table (ADR-0020, decision 6). Each route names its level, which
 * drives the breadcrumb, a title for the browser tab and the "being rebuilt"
 * page, and where the same thing lives in the pre-v7 application.
 * `legacyExact` is false where the pre-v7 application has no address for the
 * same thing (a sprint or task needs its project id, which the address here
 * does not carry), so the link can only go to its start.
 *
 * Which routes have a page is decided in pages.js, not here.
 */
export const ROUTES = [
  {
    name: "workspace",
    legacyExact: true,
    pattern: "",
    level: "workspace",
    title: "Workspace",
    legacyHref: () => legacyPaths.workspace(),
  },
  {
    name: "workspace-settings",
    legacyExact: false,
    pattern: "/settings",
    level: "workspace",
    title: "Workspace settings",
    legacyHref: () => legacyPaths.workspace(),
  },
  {
    name: "project",
    legacyExact: true,
    pattern: "/projects/:projectId",
    level: "project",
    title: "Project, Sprints",
    legacyHref: ({ projectId }) => legacyPaths.project(projectId),
  },
  {
    name: "project-backlog",
    legacyExact: true,
    pattern: "/projects/:projectId/backlog",
    level: "project",
    title: "Project, Backlog",
    legacyHref: ({ projectId }) => legacyPaths.project(projectId),
  },
  {
    name: "project-activity",
    legacyExact: true,
    pattern: "/projects/:projectId/activity",
    level: "project",
    title: "Project, Activity",
    legacyHref: ({ projectId }) => legacyPaths.project(projectId),
  },
  {
    name: "project-settings",
    legacyExact: true,
    pattern: "/projects/:projectId/settings",
    level: "project",
    title: "Project settings, General",
    legacyHref: ({ projectId }) => legacyPaths.project(projectId),
  },
  {
    name: "project-settings-workflow",
    legacyExact: true,
    pattern: "/projects/:projectId/settings/workflow",
    level: "project",
    title: "Project settings, Workflow",
    legacyHref: ({ projectId }) => legacyPaths.project(projectId),
  },
  {
    name: "sprint",
    legacyExact: false,
    pattern: "/sprints/:sprintId",
    level: "sprint",
    title: "Sprint, list",
    legacyHref: () => legacyPaths.workspace(),
  },
  {
    name: "sprint-board",
    legacyExact: false,
    pattern: "/sprints/:sprintId/board",
    level: "sprint",
    title: "Sprint, board",
    legacyHref: () => legacyPaths.workspace(),
  },
  {
    name: "task",
    legacyExact: false,
    pattern: "/tasks/:taskId",
    level: "task",
    title: "Task, Overview",
    legacyHref: () => legacyPaths.workspace(),
  },
  {
    name: "task-changes",
    legacyExact: false,
    pattern: "/tasks/:taskId/changes",
    level: "task",
    title: "Task, Changes",
    legacyHref: () => legacyPaths.workspace(),
  },
  {
    name: "task-checks",
    legacyExact: false,
    pattern: "/tasks/:taskId/checks",
    level: "task",
    title: "Task, Checks",
    legacyHref: () => legacyPaths.workspace(),
  },
  {
    name: "task-activity",
    legacyExact: false,
    pattern: "/tasks/:taskId/activity",
    level: "task",
    title: "Task, Activity",
    legacyHref: () => legacyPaths.workspace(),
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
