import React, { useState } from "react";

import { getProjectDefinitions } from "../../api/definitions";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { endsWords, originWords, toolsWords } from "./definitionWords";
import { RoleEditor } from "./RoleEditor";
import { BLANK, StartFrom } from "./StartFrom";

/**
 * /dashboard/projects/{id}/settings/roles: the roles this project runs with.
 * With no project it is the workspace's roles, the defaults for every project.
 */
export function RolesTab({ projectId = null }) {
  const ORIGIN = originWords(projectId);
  const definitions = useResource(["project-definitions", projectId], (client, options) =>
    getProjectDefinitions(client, projectId, options),
  );
  const [editing, setEditing] = useState(null);
  const [starting, setStarting] = useState(false);

  if (definitions.error && !definitions.data) {
    return (
      <p className="notice notice--error" role="alert">
        {definitions.error}
      </p>
    );
  }
  if (!definitions.data) return <p className="notice">Loading the roles…</p>;

  const { roles, vocabulary, blank } = definitions.data;
  const edited = !editing ? null : editing.id === BLANK ? blank.role : roles.find((role) => role.id === editing.id);

  return (
    <section className={projectId ? "settings-section" : "settings-block"} aria-labelledby="project-roles">
      <SectionHeading
        id="project-roles"
        title="Roles"
        actions={<Button onClick={() => setStarting(true)}>New role</Button>}
      />
      <Table
        caption="Roles"
        rows={roles}
        columns={[
          {
            key: "role",
            header: "Role",
            className: "definition__nowrap",
            render: (role) => (
              <>
                {role.name}
                {ORIGIN[role.origin] ? <span className="definition__origin"> {ORIGIN[role.origin]}</span> : null}
              </>
            ),
          },
          {
            key: "model",
            header: "Model",
            className: "definition__nowrap",
            render: (role) =>
              role.models?.length ? (
                <Mono>{role.models.join(" › ")}</Mono>
              ) : role.model ? (
                <Mono>{role.model}</Mono>
              ) : projectId ? (
                "Project default"
              ) : (
                "Each project's default"
              ),
          },
          { key: "tools", header: "Tools", render: (role) => toolsWords(role.tools) },
          { key: "ends", header: "Ends with", render: endsWords },
          {
            key: "used",
            header: "Used by",
            render: (role) =>
              role.used_by.length ? role.used_by.join(", ") : <span className="setting-row__none">No workflow</span>,
          },
          {
            key: "open",
            header: <span className="visually-hidden">Actions</span>,
            className: "settings-block__action",
            render: (role) => (
              <Button inRow variant="quiet" aria-label={`Edit role ${role.name}`} onClick={() => setEditing({ id: role.id })}>
                Edit
              </Button>
            ),
          },
        ]}
      />
      <StartFrom
        open={starting}
        kind="role"
        items={roles}
        onClose={() => setStarting(false)}
        onChosen={(id) => {
          setStarting(false);
          setEditing({ id, isNew: true });
        }}
      />
      <RoleEditor
        open={Boolean(edited)}
        projectId={projectId}
        role={edited}
        isNew={Boolean(editing?.isNew)}
        vocabulary={vocabulary}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          definitions.reload();
        }}
      />
    </section>
  );
}
