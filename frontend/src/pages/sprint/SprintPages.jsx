import React from "react";

import { SprintLayout, VIEWS } from "./SprintLayout";

/** /dashboard/sprints/{id}: the list view. */
export function SprintListPage({ params }) {
  return <SprintLayout sprintId={params.sprintId} view={VIEWS.list} />;
}

/** /dashboard/sprints/{id}/board: the board view. */
export function SprintBoardPage({ params }) {
  return <SprintLayout sprintId={params.sprintId} view={VIEWS.board} />;
}
