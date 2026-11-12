import React, { useCallback, useState } from "react";

import { useResource } from "../../api/useResource";
import { getWorkspace } from "../../api/workspace";

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

/**
 * /dashboard/projects/{id}/backlog: the backlog, a page of its own below the
 * project, the way a sprint is. It holds the project's tasks that are in no
 * sprint; it is not a tab of the project page.
 */
export function ProjectBacklogPage({ params }) {
  const workspace = useResource(["workspace"], getWorkspace);
  const [revision, setRevision] = useState(0);
  const reloadWorkspace = workspace.reload;
  const changed = useCallback(() => {
    reloadWorkspace();
    setRevision((value) => value + 1);
  }, [reloadWorkspace]);
  const project = workspace.data?.projects.find((entry) => entry.id === params.projectId) ?? null;
  return (
    <div className="backlog-page">
      <div className="backlog-page__head">
        <h1 className="page-title">Backlog</h1>
        <p className="secondary">
          {project ? `${project.name}: ` : ""}work that is in no sprint. Filed work is accepted, then planned into a sprint.
        </p>
      </div>
      <BacklogTab projectId={params.projectId} revision={revision} onChanged={changed} />
    </div>
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
