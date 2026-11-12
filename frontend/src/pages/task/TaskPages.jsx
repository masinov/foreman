import React from "react";

import { ActivityTab } from "./ActivityTab";
import { ChangesTab } from "./ChangesTab";
import { ChecksTab } from "./ChecksTab";
import { OverviewTab } from "./OverviewTab";
import { TaskLayout } from "./TaskLayout";

/** /dashboard/tasks/{id}: Overview. */
export function TaskOverviewPage({ params }) {
  return <TaskLayout taskId={params.taskId}>{(props) => <OverviewTab {...props} />}</TaskLayout>;
}

/** /dashboard/tasks/{id}/changes. */
export function TaskChangesPage({ params }) {
  return <TaskLayout taskId={params.taskId}>{(props) => <ChangesTab {...props} />}</TaskLayout>;
}

/** /dashboard/tasks/{id}/checks. */
export function TaskChecksPage({ params }) {
  return <TaskLayout taskId={params.taskId}>{(props) => <ChecksTab {...props} />}</TaskLayout>;
}

/** /dashboard/tasks/{id}/activity. */
export function TaskActivityPage({ params }) {
  return <TaskLayout taskId={params.taskId}>{(props) => <ActivityTab {...props} />}</TaskLayout>;
}
