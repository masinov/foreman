export const DASHBOARD_BASE_PATH = "/dashboard";

function decodeSegment(value) {
  return decodeURIComponent(value || "");
}

function trimTrailingSlash(pathname) {
  if (!pathname || pathname === "/") {
    return "/";
  }
  return pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
}

export function parseRoute(pathname) {
  const cleaned = trimTrailingSlash(pathname);
  if (cleaned === "/" || cleaned === DASHBOARD_BASE_PATH) {
    return { view: "dashboard", projectId: null, sprintId: null };
  }

  const parts = cleaned.split("/").filter(Boolean);
  if (parts[0] !== "dashboard") {
    return { view: "dashboard", projectId: null, sprintId: null };
  }

  if (parts.length >= 3 && parts[1] === "projects") {
    const projectId = decodeSegment(parts[2]);
    if (parts.length >= 5 && parts[3] === "sprints") {
      return {
        view: "sprint",
        projectId,
        sprintId: decodeSegment(parts[4]),
      };
    }
    return { view: "project", projectId, sprintId: null };
  }

  return { view: "dashboard", projectId: null, sprintId: null };
}

export function buildDashboardPath() {
  return DASHBOARD_BASE_PATH;
}

export function buildProjectPath(projectId) {
  return `${DASHBOARD_BASE_PATH}/projects/${encodeURIComponent(projectId)}`;
}

export function buildSprintPath(projectId, sprintId) {
  return `${buildProjectPath(projectId)}/sprints/${encodeURIComponent(sprintId)}`;
}
