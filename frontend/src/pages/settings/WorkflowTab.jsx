import React, { useState } from "react";

import { getProjectSettings, getProjectWorkflow } from "../../api/projects";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { ChangeWorkflowDialog } from "./ChangeWorkflowDialog";
import { decider } from "./settingsWords";
import { REQUIREMENT_SOURCES, stepRows } from "./workflowWords";

function How({ how }) {
  return (
    <>
      {how.text}
      {how.model !== undefined ? how.model ? <Mono>{how.model}</Mono> : how.fallback : null}
    </>
  );
}

function Steps({ rows }) {
  return (
    <Table
      caption="Steps of the workflow"
      rows={rows}
      columns={[
        { key: "step", header: "Step", render: (row) => row.label },
        { key: "by", header: "Done by", render: (row) => row.doneBy },
        { key: "how", header: "How", render: (row) => <How how={row.how} /> },
        {
          key: "moves",
          header: "Moves on when",
          render: (row) => (row.final ? <span className="setting-row__none">The last step</span> : row.movesOn),
        },
        {
          key: "otherwise",
          header: "Otherwise",
          render: (row) =>
            row.otherwise.map((line) => (
              <p key={line} className="workflow__line">
                {line}
              </p>
            )),
        },
      ]}
    />
  );
}

function Requirements({ workflow }) {
  if (workflow.requirements.length === 0) {
    return (
      <p className="notice">
        This workflow has no test or review step, so finishing a task needs neither.
      </p>
    );
  }
  return (
    <Table
      caption="What finishing requires"
      rows={workflow.requirements}
      columns={[
        { key: "needs", header: "To finish, a task needs", render: (row) => row.text },
        { key: "kind", header: "Kind", render: (row) => REQUIREMENT_SOURCES[row.kind]?.kind ?? row.kind },
        { key: "source", header: "Where it comes from", render: (row) => REQUIREMENT_SOURCES[row.kind]?.source ?? "" },
      ]}
    />
  );
}

function Roles({ roles }) {
  return (
    <Table
      caption="Roles in this workflow"
      rows={roles}
      columns={[
        { key: "role", header: "Role", render: (row) => row.name },
        { key: "does", header: "What it does", render: (row) => row.description },
        { key: "on", header: "Runs on", render: (row) => <Mono>{row.backend}</Mono> },
        { key: "model", header: "Model", render: (row) => (row.model ? <Mono>{row.model}</Mono> : "project default") },
      ]}
    />
  );
}

/** /dashboard/projects/{id}/settings/workflow: the Workflow tab. */
export function WorkflowTab({ projectId }) {
  const workflow = useResource(["project-workflow", projectId], (client, options) =>
    getProjectWorkflow(client, projectId, options),
  );
  const settings = useResource(["project-settings", projectId], (client, options) =>
    getProjectSettings(client, projectId, options),
  );
  const [changing, setChanging] = useState(false);

  const error = workflow.error || settings.error;
  if (error && !(workflow.data && settings.data)) {
    return (
      <p className="notice notice--error" role="alert">
        {error}
      </p>
    );
  }
  if (!workflow.data || !settings.data) return <p className="notice">Loading the workflow…</p>;

  const definition = workflow.data;
  const effective = settings.data.effective;
  const decidedBy = {
    merge_approval: decider(effective.merge_approval),
    plan_approval: decider(effective.plan_approval),
  };
  const rows = stepRows(definition, { decidedBy, defaultBranch: settings.data.default_branch });

  return (
    <div className="workflow">
      <section className="settings-section" aria-labelledby="workflow-steps">
        <SectionHeading
          id="workflow-steps"
          title={
            <>
              {definition.name} <Mono quiet>{definition.id}</Mono>
            </>
          }
          actions={<Button onClick={() => setChanging(true)}>Use another workflow</Button>}
        />
        <p className="workflow__source">
          Read from <Mono>{definition.source_path}</Mono>. Edit that file to change the steps; they cannot be edited
          here.
        </p>
        <Steps rows={rows} />
      </section>

      <section className="settings-section" aria-labelledby="workflow-finishing">
        <SectionHeading
          id="workflow-finishing"
          title="What finishing requires"
          note="A fact is measured by the engine. A claim is what an agent reported."
        />
        {definition.requirements_enforced ? null : (
          <p className="notice">The completion guard is off for this project, so a merge is not held to these.</p>
        )}
        <Requirements workflow={definition} />
      </section>

      <section className="settings-section" aria-labelledby="workflow-roles">
        <SectionHeading id="workflow-roles" title="Roles in this workflow" />
        <Roles roles={definition.roles} />
      </section>

      <ChangeWorkflowDialog
        open={changing}
        projectId={projectId}
        current={definition.id}
        onClose={() => setChanging(false)}
        onChanged={() => {
          setChanging(false);
          workflow.reload();
          settings.reload();
        }}
      />
    </div>
  );
}
