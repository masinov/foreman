import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { approveTask } from "../../api/tasks";
import { useDelayedFlag, useResource } from "../../api/useResource";
import { loadWorkspace } from "../../api/workspace";
import { SectionHeading } from "../../ui/SectionHeading";
import { NeedsYou } from "./NeedsYou";
import { ProjectsTable } from "./ProjectsTable";

import "../../styles/workspace.css";

/**
 * The workspace: the only page that spans projects
 * (docs/design/dashboard-v7/01-workspace.html).
 */
export function WorkspacePage() {
  const client = useApiClient();
  const workspace = useResource(["workspace"], loadWorkspace);
  const placeholder = useDelayedFlag(workspace.loading && !workspace.data);
  const [approvingId, setApprovingId] = useState(null);
  const [notice, setNotice] = useState(null);

  async function handleApprove(item) {
    setApprovingId(item.id);
    setNotice(null);
    try {
      const result = await approveTask(client, item.taskId);
      setNotice({ error: false, text: result?.message || `Approved ${item.taskKey || item.title}.` });
      workspace.reload();
    } catch (error) {
      setNotice({ error: true, text: errorSentence(error) });
    } finally {
      setApprovingId(null);
    }
  }

  const data = workspace.data;
  return (
    <div className="workspace">
      <h1 className="visually-hidden">Workspace</h1>
      {workspace.error ? (
        <p className="notice notice--error" role="alert">
          {workspace.error}
        </p>
      ) : null}
      <NeedsYou
        items={data ? data.needsYou : null}
        placeholder={placeholder}
        onApprove={handleApprove}
        approvingId={approvingId}
        notice={notice}
      />
      <section className="workspace__section" aria-labelledby="projects-title">
        <SectionHeading id="projects-title" title="Projects" />
        <ProjectsTable projects={data ? data.projects : null} placeholder={placeholder} />
      </section>
    </div>
  );
}
