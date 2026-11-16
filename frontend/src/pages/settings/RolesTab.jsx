import React, { useId, useState } from "react";

import { getProjectDefinitions } from "../../api/definitions";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { endsWords, ORIGIN, toolsWords } from "./definitionWords";
import { RoleEditor } from "./RoleEditor";

/** A new role starts as a copy of one the project has: which one. */
function StartFrom({ open, roles, onClose, onChosen }) {
  const id = useId();
  const [chosen, setChosen] = useState("");
  return (
    <Dialog
      open={open}
      title="New role"
      description="A new role starts as a copy of one you have. Choose the closest."
      onClose={onClose}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!chosen} onClick={() => onChosen(chosen)}>
            Continue
          </Button>
        </>
      }
    >
      <div className="field">
        <label className="field__label" htmlFor={id}>
          Start from
        </label>
        <select id={id} className="field__input" value={chosen} data-autofocus onChange={(event) => setChosen(event.target.value)}>
          <option value="">Choose a role</option>
          {roles.map((role) => (
            <option key={role.id} value={role.id}>
              {role.name}
            </option>
          ))}
        </select>
      </div>
    </Dialog>
  );
}

/** /dashboard/projects/{id}/settings/roles: the roles this project runs with. */
export function RolesTab({ projectId }) {
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

  const { roles, vocabulary } = definitions.data;
  const edited = editing ? roles.find((role) => role.id === editing.id) : null;

  return (
    <section className="settings-section" aria-labelledby="project-roles">
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
            render: (role) => (role.model ? <Mono>{role.model}</Mono> : "Project default"),
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
        roles={roles}
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
