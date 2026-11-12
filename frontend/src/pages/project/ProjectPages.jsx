import React from "react";

import { ActivityTab } from "./ActivityTab";
import { BacklogTab } from "./BacklogTab";
import { ProjectLayout } from "./ProjectLayout";
import { SprintsTab } from "./SprintsTab";

/** /dashboard/projects/{id}: the Sprints tab. */
export function ProjectSprintsPage({ params }) {
  return (
    <ProjectLayout projectId={params.projectId}>
      {(revision) => <SprintsTab projectId={params.projectId} revision={revision} />}
    </ProjectLayout>
  );
}

/** /dashboard/projects/{id}/backlog: the Backlog tab. */
export function ProjectBacklogPage({ params }) {
  return (
    <ProjectLayout projectId={params.projectId}>
      {(revision, changed) => <BacklogTab projectId={params.projectId} revision={revision} onChanged={changed} />}
    </ProjectLayout>
  );
}

/** /dashboard/projects/{id}/activity: the Activity tab. */
export function ProjectActivityPage({ params }) {
  return (
    <ProjectLayout projectId={params.projectId}>
      {() => <ActivityTab projectId={params.projectId} />}
    </ProjectLayout>
  );
}
