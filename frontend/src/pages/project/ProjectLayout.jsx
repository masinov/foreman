import React, { useCallback, useState } from "react";

import { useResource } from "../../api/useResource";
import { getWorkspace } from "../../api/workspace";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Icon } from "../../ui/Icon";
import { Mono } from "../../ui/Mono";
import { Tabs } from "../../ui/Tabs";
import { NeedsYou } from "../shared/NeedsYou";
import { EngineRow } from "./EngineRow";

import "../../styles/lists.css";
import "../../styles/project.css";

/** True when the project has an active sprint with no tasks in it at all. */
function activeSprintIsEmpty(project) {
  const counts = project?.active_sprint?.task_counts;
  if (!counts) return false;
  return Object.values(counts).reduce((sum, value) => sum + (Number(value) || 0), 0) === 0;
}

function TitleRow({ projectId, project }) {
  // Where the project lives, which branch it lands on, how it works: each
  // with the icon that says which is which.
  const facts = project
    ? [
        project.repo_path ? { icon: "folder", text: project.repo_path } : null,
        project.default_branch ? { icon: "branch", text: project.default_branch } : null,
        project.workflow_id ? { icon: null, text: `${project.workflow_id} workflow` } : null,
      ].filter(Boolean)
    : [];
  return (
    <div className="project__title-row">
      <div className="project__title">
        <h1 className="page-title">{project?.name ?? "\u00a0"}</h1>
        {facts.length ? (
          <Mono quiet className="facts">
            {facts.map((fact, index) => (
              <React.Fragment key={fact.text}>
                {index > 0 ? " · " : null}
                <span className="facts__item">
                  {fact.icon ? <Icon name={fact.icon} /> : null}
                  {fact.text}
                </span>
              </React.Fragment>
            ))}
          </Mono>
        ) : null}
      </div>
      <Link className="project__page-link" href={paths.projectSettings(projectId)}>
        <Icon name="settings" />
        Project settings
      </Link>
    </div>
  );
}

/**
 * Everything above the tabs of a project page, the same on every tab
 * (docs/design/dashboard-v7/02, 09 and 11): title row, engine, Needs you and
 * the tabs. `children(revision, changed)` is the tab; `revision` grows whenever
 * something changed the project (an engine command, an approval, or the tab
 * itself calling `changed()`), so the tab can reload what it shows and the
 * head and tab counts are read again.
 */
export function ProjectLayout({ projectId, children }) {
  const workspace = useResource(["workspace"], getWorkspace);
  const [revision, setRevision] = useState(0);
  const reloadWorkspace = workspace.reload;
  const changed = useCallback(() => {
    reloadWorkspace();
    setRevision((value) => value + 1);
  }, [reloadWorkspace]);

  const project = workspace.data?.projects.find((entry) => entry.id === projectId) ?? null;
  if (workspace.data && !project) {
    return (
      <div className="status-page">
        <h1 className="page-title">There is no project {projectId}</h1>
        <p className="status-page__text">
          It may have been removed, or the address is wrong.{" "}
          <Link className="status-page__link" href={paths.workspace()}>
            Go to the workspace
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="project">
      <div className="project__head">
        <TitleRow projectId={projectId} project={project} />
        {workspace.error ? (
          <p className="notice notice--error" role="alert">
            {workspace.error}
          </p>
        ) : null}
        <EngineRow
          projectId={projectId}
          engine={project?.engine ?? null}
          emptySprint={activeSprintIsEmpty(project)}
          onChanged={changed}
        />
      </div>
      <NeedsYou
        projectId={projectId}
        empty="Nothing needs you in this project. When a task waits for a decision, it appears here."
        onChanged={changed}
      />
      <div className="project__tabs">
        <Tabs
          label="Project"
          items={[
            { href: paths.project(projectId), label: "Sprints" },
            // The backlog is a page of its own (it has its own title and
            // breadcrumb step). It is listed here because this row is where
            // a person looks for the parts of a project.
            {
              href: paths.projectBacklog(projectId),
              label: (
                <>
                  Backlog
                  {project ? (
                    <>
                      <span className="visually-hidden"> </span>
                      <span className="tabs__count">{project.backlog ?? 0}</span>
                    </>
                  ) : null}
                </>
              ),
            },
            { href: paths.projectActivity(projectId), label: "Activity" },
          ]}
        />
        <div className="project__tab">{children(revision, changed)}</div>
      </div>
    </div>
  );
}
