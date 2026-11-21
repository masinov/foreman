import React from "react";

import { SprintLayout, VIEWS } from "./SprintLayout";

const VIEW_OF = { "sprint-board": VIEWS.board, "sprint-activity": VIEWS.activity };

/**
 * /dashboard/sprints/{id} (the tasks as a list), its /board and its
 * /activity: one page. The head stays as it is when the tab changes.
 */
export function SprintPage({ params, routeName }) {
  return <SprintLayout sprintId={params.sprintId} view={VIEW_OF[routeName] ?? VIEWS.list} />;
}
