import React from "react";

import { useResource } from "../../api/useResource";
import { getWorkspace } from "../../api/workspace";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Mono } from "../../ui/Mono";
import { Tabs } from "../../ui/Tabs";
import { GeneralTab } from "./GeneralTab";
import { WorkflowTab } from "./WorkflowTab";

import "../../styles/lists.css";
import "../../styles/settings.css";

/**
 * Project settings is a page of its own, not a tab of the project: a title,
 * its two tabs, and nothing of the project page's head (no engine row, no
 * Needs you). The engine and manager are in the top bar.
 */
function SettingsLayout({ projectId, children }) {
  const workspace = useResource(["workspace"], getWorkspace);
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
    <div className="settings-page">
      <div className="settings-page__title">
        <h1 className="page-title">Project settings</h1>
        {project ? <Mono quiet>{[project.name, project.repo_path].filter(Boolean).join(" · ")}</Mono> : null}
      </div>
      {workspace.error ? (
        <p className="notice notice--error" role="alert">
          {workspace.error}
        </p>
      ) : null}
      <Tabs
        label="Project settings"
        items={[
          { href: paths.projectSettings(projectId), label: "General" },
          { href: paths.projectSettingsWorkflow(projectId), label: "Workflow" },
        ]}
      />
      <div className="settings-page__tab">{children}</div>
    </div>
  );
}

/** /dashboard/projects/{id}/settings: General. */
export function ProjectSettingsGeneralPage({ params }) {
  return (
    <SettingsLayout projectId={params.projectId}>
      <GeneralTab projectId={params.projectId} />
    </SettingsLayout>
  );
}

/** /dashboard/projects/{id}/settings/workflow: Workflow. */
export function ProjectSettingsWorkflowPage({ params }) {
  return (
    <SettingsLayout projectId={params.projectId}>
      <WorkflowTab projectId={params.projectId} />
    </SettingsLayout>
  );
}
