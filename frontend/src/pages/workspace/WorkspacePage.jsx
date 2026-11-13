import React, { useState } from "react";

import { listMilestones } from "../../api/milestones";
import { useDelayedFlag, useResource } from "../../api/useResource";
import { getWorkspace } from "../../api/workspace";
import { paths } from "../../app/paths";
import { useNavigate } from "../../app/router";
import { Button } from "../../ui/Button";
import { SectionHeading } from "../../ui/SectionHeading";
import { MilestoneTable } from "../shared/milestones";
import { NeedsYou } from "../shared/NeedsYou";
import { AddProjectDialog } from "./AddProjectDialog";
import { ProjectsTable } from "./ProjectsTable";

import "../../styles/lists.css";
import "../../styles/workspace.css";

// How many milestones the workspace shows. Each project's Activity tab has
// the rest.
export const RECENT_MILESTONES = 10;

/**
 * The workspace: the only page that spans projects
 * (docs/design/dashboard-v7/01-workspace.html).
 */
export function WorkspacePage() {
  const workspace = useResource(["workspace"], getWorkspace);
  const recent = useResource(["milestones", "workspace"], (client, options) =>
    listMilestones(client, { limit: RECENT_MILESTONES, ...options }),
  );
  const placeholder = useDelayedFlag(workspace.loading && !workspace.data);
  const recentPlaceholder = useDelayedFlag(recent.loading && !recent.data);
  const [adding, setAdding] = useState(false);
  const navigate = useNavigate();

  return (
    <div className="workspace">
      <h1 className="visually-hidden">Workspace</h1>
      <NeedsYou
        note="across all projects"
        empty="Nothing needs you. When a task waits for a decision in any project, it appears here."
        onChanged={workspace.reload}
      />
      <section className="workspace__section" aria-labelledby="projects-title">
        <SectionHeading
          id="projects-title"
          title="Projects"
          actions={
            <Button icon="plus" onClick={() => setAdding(true)}>
              Add project
            </Button>
          }
        />
        {workspace.error ? (
          <p className="notice notice--error" role="alert">
            {workspace.error}
          </p>
        ) : null}
        <ProjectsTable projects={workspace.data ? workspace.data.projects : null} placeholder={placeholder} />
      </section>
      <section className="workspace__section" aria-labelledby="recent-title">
        <SectionHeading
          id="recent-title"
          title="Recent"
          note="Milestones only: sprints started and finished, tasks merged, the engine started, paused or stopped."
        />
        {recent.error ? (
          <p className="notice notice--error" role="alert">
            {recent.error}
          </p>
        ) : null}
        {recentPlaceholder ? <MilestoneTable caption="Recent milestones" showProject placeholderRows={3} /> : null}
        {recent.data && recent.data.items.length === 0 ? (
          <p className="empty">Nothing has happened yet. Sprints starting and finishing, merges and engine changes appear here.</p>
        ) : null}
        {recent.data && recent.data.items.length > 0 ? (
          <MilestoneTable caption="Recent milestones" items={recent.data.items} showProject />
        ) : null}
      </section>
      <AddProjectDialog
        open={adding}
        onClose={() => setAdding(false)}
        onAdded={(project) => {
          setAdding(false);
          workspace.reload();
          if (project?.id) navigate(paths.project(project.id));
        }}
      />
    </div>
  );
}
