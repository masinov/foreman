import { ProjectBacklogPage, ProjectPage } from "../pages/project/ProjectPages";
import { ProjectSettingsPage } from "../pages/settings/SettingsPages";
import { SprintPage } from "../pages/sprint/SprintPages";
import { TaskPage } from "../pages/task/TaskPages";
import { WorkspaceSettingsPage } from "../pages/workspaceSettings/WorkspaceSettingsPage";
import { WorkspacePage } from "../pages/workspace/WorkspacePage";

// Routes that have a rebuilt page. Every other route in ROUTES renders the
// shared "being rebuilt" page until its slice lands.
//
// The addresses of one thing's tabs share one page component, which is given
// the route's name and shows the tab for it. That is what keeps the head of
// the page in place, and what it has loaded, when only the tab changes.
export const BUILT_PAGES = {
  workspace: WorkspacePage,
  "workspace-settings": WorkspaceSettingsPage,
  project: ProjectPage,
  "project-backlog": ProjectBacklogPage,
  "project-activity": ProjectPage,
  "project-settings": ProjectSettingsPage,
  "project-settings-workflow": ProjectSettingsPage,
  "project-settings-roles": ProjectSettingsPage,
  sprint: SprintPage,
  "sprint-board": SprintPage,
  "sprint-activity": SprintPage,
  task: TaskPage,
  "task-changes": TaskPage,
  "task-checks": TaskPage,
  "task-activity": TaskPage,
};

// The page a route belongs to, where several routes are tabs of one page.
const TAB_OF = {
  "project-activity": "project",
  "project-settings-workflow": "project-settings",
  "project-settings-roles": "project-settings",
  "sprint-board": "sprint",
  "sprint-activity": "sprint",
  "task-changes": "task",
  "task-checks": "task",
  "task-activity": "task",
};

/**
 * What identifies the page on screen: the same for every tab of one thing,
 * different for another thing or another kind of page. A page's state is
 * reset when this changes and kept when only the tab does.
 */
export function pageKey(routeName, params) {
  return `${TAB_OF[routeName] ?? routeName}:${JSON.stringify(params)}`;
}
