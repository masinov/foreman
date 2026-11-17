import React from "react";

import { ActivityTab } from "./ActivityTab";
import { ChangesTab } from "./ChangesTab";
import { ChecksTab } from "./ChecksTab";
import { OverviewTab } from "./OverviewTab";
import { TaskLayout } from "./TaskLayout";

// The tab each of a task's addresses shows.
const TABS = {
  task: OverviewTab,
  "task-changes": ChangesTab,
  "task-checks": ChecksTab,
  "task-activity": ActivityTab,
};

/**
 * /dashboard/tasks/{id} and its /changes, /checks and /activity: one page.
 * The title, the decision and the tab bar stay as they are when the tab
 * changes; only what is under the tab bar is replaced.
 */
export function TaskPage({ params, routeName }) {
  const Tab = TABS[routeName] ?? OverviewTab;
  return <TaskLayout taskId={params.taskId}>{(props) => <Tab {...props} />}</TaskLayout>;
}
