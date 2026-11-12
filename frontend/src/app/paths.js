// Addresses of every screen (ADR-0020, decision 6). Build links with these,
// never by hand.
export const DASHBOARD = "/dashboard";
export const LEGACY = `${DASHBOARD}/legacy`;

const enc = (value) => encodeURIComponent(String(value));

export const paths = {
  workspace: () => DASHBOARD,
  workspaceSettings: () => `${DASHBOARD}/settings`,
  project: (projectId) => `${DASHBOARD}/projects/${enc(projectId)}`,
  projectBacklog: (projectId) => `${paths.project(projectId)}/backlog`,
  projectActivity: (projectId) => `${paths.project(projectId)}/activity`,
  projectSettings: (projectId) => `${paths.project(projectId)}/settings`,
  projectSettingsWorkflow: (projectId) => `${paths.project(projectId)}/settings/workflow`,
  sprint: (sprintId) => `${DASHBOARD}/sprints/${enc(sprintId)}`,
  sprintBoard: (sprintId) => `${paths.sprint(sprintId)}/board`,
  task: (taskId) => `${DASHBOARD}/tasks/${enc(taskId)}`,
  taskChanges: (taskId) => `${paths.task(taskId)}/changes`,
  taskChecks: (taskId) => `${paths.task(taskId)}/checks`,
  taskActivity: (taskId) => `${paths.task(taskId)}/activity`,
};

// The pre-v7 application, kept until the rebuild's last slice removes it.
export const legacyPaths = {
  workspace: () => LEGACY,
  project: (projectId) => `${LEGACY}/projects/${enc(projectId)}`,
  sprint: (projectId, sprintId) => `${legacyPaths.project(projectId)}/sprints/${enc(sprintId)}`,
};

export function normalizePath(pathname) {
  if (!pathname || pathname === "/") return "/";
  const trimmed = pathname.replace(/\/+$/, "");
  return trimmed || "/";
}

export function isLegacyPath(pathname) {
  const cleaned = normalizePath(pathname);
  return cleaned === LEGACY || cleaned.startsWith(`${LEGACY}/`);
}

/** True for a path the rebuilt application routes itself. */
export function isAppPath(pathname) {
  const cleaned = normalizePath(pathname);
  return (cleaned === DASHBOARD || cleaned.startsWith(`${DASHBOARD}/`)) && !isLegacyPath(cleaned);
}
