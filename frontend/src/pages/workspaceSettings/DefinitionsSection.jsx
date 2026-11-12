import React, { useState } from "react";

import { listRoles } from "../../api/access";
import { listWorkflows } from "../../api/projects";
import { useDelayedFlag, useResource } from "../../api/useResource";
import { getWorkspace } from "../../api/workspace";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { formatMoney } from "../../ui/format";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { ReadOnlyRow } from "../settings/SettingRow";
import { stepRows } from "../settings/workflowWords";

function Where({ path }) {
  return (
    <ReadOnlyRow label="File">
      <Mono quiet>{path}</Mono>
    </ReadOnlyRow>
  );
}

function RoleDefinition({ role }) {
  return (
    <dl className="settings-section__rows">
      <ReadOnlyRow label="What it does">{role.description || "No description."}</ReadOnlyRow>
      <ReadOnlyRow label="Runs on">
        <Mono>{role.backend}</Mono>
      </ReadOnlyRow>
      <ReadOnlyRow label="Model">
        {role.model ? <Mono>{role.model}</Mono> : <span className="settings-block__aside">The project's default model</span>}
      </ReadOnlyRow>
      <ReadOnlyRow label="Permissions">
        <Mono>{role.permission_mode}</Mono>
      </ReadOnlyRow>
      <ReadOnlyRow label="Time limit">{role.timeout_minutes} minutes</ReadOnlyRow>
      <ReadOnlyRow label="Cost limit">{role.max_cost_usd ? formatMoney(role.max_cost_usd) : "None"}</ReadOnlyRow>
      <Where path={role.source_path} />
    </dl>
  );
}

function WorkflowDefinition({ workflow }) {
  return (
    <>
      <Table
        caption={`Steps of ${workflow.name}`}
        rows={stepRows(workflow)}
        columns={[
          { key: "step", header: "Step", render: (row) => row.label },
          { key: "by", header: "Done by", render: (row) => row.doneBy },
          {
            key: "moves",
            header: "Moves on when",
            render: (row) => (row.final ? <span className="settings-block__aside">The last step</span> : row.movesOn),
          },
        ]}
      />
      <dl className="settings-section__rows">
        <Where path={workflow.source_path} />
      </dl>
    </>
  );
}

/** A definition, read-only, with the file it comes from. Editing happens in that file. */
function DefinitionDialog({ definition, onClose }) {
  const workflow = definition?.kind === "workflow";
  return (
    <Dialog
      open={Boolean(definition)}
      title={definition ? (workflow ? definition.item.name : definition.item.name) : "Definition"}
      description={
        definition
          ? `${workflow ? "Workflow" : "Role"} ${definition.item.id}. To change it, edit its file; the dashboard shows it as it is.`
          : ""
      }
      onClose={onClose}
      className="dialog--wide"
      footer={
        <Button onClick={onClose} data-autofocus>
          Close
        </Button>
      }
    >
      {definition ? (
        workflow ? (
          <WorkflowDefinition workflow={definition.item} />
        ) : (
          <RoleDefinition role={definition.item} />
        )
      ) : null}
    </Dialog>
  );
}

/** Which projects use each workflow, by name, in the order the workspace lists them. */
function usedBy(workflowId, projects) {
  return projects.filter((project) => project.workflow_id === workflowId).map((project) => project.name);
}

/** Defaults for projects: the workflows and the roles Foreman has. */
export function DefinitionsSection() {
  const workflows = useResource(["workflows"], listWorkflows);
  const roles = useResource(["roles"], listRoles);
  const workspace = useResource(["workspace"], getWorkspace);
  const workflowsPlaceholder = useDelayedFlag(workflows.loading && !workflows.data);
  const rolesPlaceholder = useDelayedFlag(roles.loading && !roles.data);
  const [open, setOpen] = useState(null);
  const projects = workspace.data?.projects ?? [];

  return (
    <section className="settings-block" aria-labelledby="defaults-title">
      <SectionHeading
        id="defaults-title"
        title="Defaults for projects"
        note="Every project starts from these. A project can override any of them in its own repository."
      />
      {[workflows.error, roles.error].filter(Boolean).map((message) => (
        <p key={message} className="notice notice--error" role="alert">
          {message}
        </p>
      ))}
      <div className="definitions">
        <div className="definitions__workflows">
          <Table
            caption="Workflows"
            rows={workflows.data ?? []}
            placeholderRows={workflowsPlaceholder ? 3 : null}
            columns={[
              { key: "id", header: "Workflow", render: (workflow) => <Mono>{workflow.id}</Mono> },
              {
                key: "used",
                header: "Used by",
                render: (workflow) => {
                  const names = usedBy(workflow.id, projects);
                  return names.length ? names.join(", ") : <span className="settings-block__aside">No project</span>;
                },
              },
              {
                key: "open",
                header: <span className="visually-hidden">Actions</span>,
                className: "settings-block__action",
                render: (workflow) => (
                  <Button
                    inRow
                    variant="quiet"
                    aria-label={`Open workflow ${workflow.id}`}
                    onClick={() => setOpen({ kind: "workflow", item: workflow })}
                  >
                    Open
                  </Button>
                ),
              },
            ]}
          />
        </div>
        <div className="definitions__roles">
          <Table
            caption="Roles"
            rows={roles.data ?? []}
            placeholderRows={rolesPlaceholder ? 3 : null}
            columns={[
              { key: "id", header: "Role", render: (role) => <Mono>{role.id}</Mono> },
              {
                key: "open",
                header: <span className="visually-hidden">Actions</span>,
                className: "settings-block__action",
                render: (role) => (
                  <Button
                    inRow
                    variant="quiet"
                    aria-label={`Open role ${role.id}`}
                    onClick={() => setOpen({ kind: "role", item: role })}
                  >
                    Open
                  </Button>
                ),
              },
            ]}
          />
        </div>
      </div>
      <DefinitionDialog definition={open} onClose={() => setOpen(null)} />
    </section>
  );
}
