import { ProjectActivityPage, ProjectBacklogPage, ProjectSprintsPage } from "../pages/project/ProjectPages";
import { ProjectSettingsGeneralPage, ProjectSettingsWorkflowPage } from "../pages/settings/SettingsPages";
import { SprintBoardPage, SprintListPage } from "../pages/sprint/SprintPages";
import { TaskActivityPage, TaskChangesPage, TaskChecksPage, TaskOverviewPage } from "../pages/task/TaskPages";
import { WorkspacePage } from "../pages/workspace/WorkspacePage";

// Routes that have a rebuilt page. Every other route in ROUTES renders the
// shared "being rebuilt" page until its slice lands.
export const BUILT_PAGES = {
  workspace: WorkspacePage,
  project: ProjectSprintsPage,
  "project-backlog": ProjectBacklogPage,
  "project-activity": ProjectActivityPage,
  "project-settings": ProjectSettingsGeneralPage,
  "project-settings-workflow": ProjectSettingsWorkflowPage,
  sprint: SprintListPage,
  "sprint-board": SprintBoardPage,
  task: TaskOverviewPage,
  "task-changes": TaskChangesPage,
  "task-checks": TaskChecksPage,
  "task-activity": TaskActivityPage,
};
