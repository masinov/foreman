// The application that predates dashboard design v7 lives under
// /dashboard/legacy until the last slice of the frontend rebuild removes it
// (ADR-0020, decision 11).
export const DASHBOARD_BASE_PATH = "/dashboard/legacy";

const BASE_SEGMENTS = DASHBOARD_BASE_PATH.split("/").filter(Boolean);

function decodeSegment(value) {
  return decodeURIComponent(value || "");
}

function trimTrailingSlash(pathname) {
  if (!pathname || pathname === "/") {
    return "/";
  }
  return pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
}

export function isLegacyPath(pathname) {
  const cleaned = trimTrailingSlash(pathname);
  return cleaned === DASHBOARD_BASE_PATH || cleaned.startsWith(`${DASHBOARD_BASE_PATH}/`);
}

export function parseRoute(pathname) {
  const dashboard = { view: "dashboard", projectId: null, sprintId: null };
  if (!isLegacyPath(pathname)) {
    return dashboard;
  }

  const parts = trimTrailingSlash(pathname).split("/").filter(Boolean).slice(BASE_SEGMENTS.length);
  if (parts.length >= 2 && parts[0] === "projects") {
    const projectId = decodeSegment(parts[1]);
    if (parts.length >= 4 && parts[2] === "sprints") {
      return {
        view: "sprint",
        projectId,
        sprintId: decodeSegment(parts[3]),
      };
    }
    return { view: "project", projectId, sprintId: null };
  }

  return dashboard;
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
