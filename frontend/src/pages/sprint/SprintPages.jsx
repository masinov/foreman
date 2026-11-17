import React from "react";

import { SprintLayout, VIEWS } from "./SprintLayout";

/**
 * /dashboard/sprints/{id} (the list) and its /board: one page. The head
 * stays as it is when the view changes.
 */
export function SprintPage({ params, routeName }) {
  return <SprintLayout sprintId={params.sprintId} view={routeName === "sprint-board" ? VIEWS.board : VIEWS.list} />;
}
