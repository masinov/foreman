import React, { useId, useState } from "react";

import { getProjectDefinitions } from "../../api/definitions";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { DEFAULT_ORIGIN } from "../settings/definitionWords";
import { WorkflowEditor } from "../settings/WorkflowEditor";

/** A new workflow starts as a copy of one the workspace has: which one. */
function StartFrom({ open, workflows, onClose, onChosen }) {
  const id = useId();
  const [chosen, setChosen] = useState("");
  return (
    <Dialog
      open={open}
      title="New workflow"
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
          <option value="">Choose a workflow</option>
          {workflows.map((workflow) => (
            <option key={workflow.id} value={workflow.id}>
              {workflow.name}
            </option>
          ))}
        </select>
      </div>
    </Dialog>
  );
}

/** The workspace's workflows: the ones every project can use, each editable. */
export function WorkflowsList() {
  const definitions = useResource(["project-definitions", null], (client, options) =>
    getProjectDefinitions(client, null, options),
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
  if (!definitions.data) return <p className="notice">Loading the workflows…</p>;

  const { workflows, vocabulary } = definitions.data;
  const edited = editing ? workflows.find((workflow) => workflow.id === editing.id) : null;

  return (
    <section className="settings-section" aria-labelledby="workspace-workflows">
      <SectionHeading
        id="workspace-workflows"
        title="Workflows"
        actions={<Button onClick={() => setStarting(true)}>New workflow</Button>}
      />
      <Table
        caption="Workflows"
        rows={workflows}
        columns={[
          {
            key: "workflow",
            header: "Workflow",
            className: "definition__nowrap",
            render: (workflow) => (
              <>
                {workflow.name} <Mono quiet>{workflow.id}</Mono>
                {DEFAULT_ORIGIN[workflow.origin] ? (
                  <span className="definition__origin"> {DEFAULT_ORIGIN[workflow.origin]}</span>
                ) : null}
              </>
            ),
          },
          {
            key: "steps",
            header: "Steps",
            render: (workflow) => workflow.steps.length,
          },
          {
            key: "used",
            header: "Used by",
            render: (workflow) =>
              workflow.used_by.length ? workflow.used_by.join(", ") : <span className="setting-row__none">No project</span>,
          },
          {
            key: "open",
            header: <span className="visually-hidden">Actions</span>,
            className: "settings-block__action",
            render: (workflow) => (
              <Button
                inRow
                variant="quiet"
                aria-label={`Edit workflow ${workflow.name}`}
                onClick={() => setEditing({ id: workflow.id })}
              >
                Edit
              </Button>
            ),
          },
        ]}
      />
      <StartFrom
        open={starting}
        workflows={workflows}
        onClose={() => setStarting(false)}
        onChosen={(id) => {
          setStarting(false);
          setEditing({ id, isNew: true });
        }}
      />
      <WorkflowEditor
        open={Boolean(edited)}
        projectId={null}
        workflow={edited}
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
