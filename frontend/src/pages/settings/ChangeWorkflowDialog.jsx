import React, { useEffect, useId, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { listWorkflows, updateProjectSettings } from "../../api/projects";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Mono } from "../../ui/Mono";
import { stepLabel } from "./workflowWords";

/**
 * "Use another workflow": pick one of the workflows Foreman has, read what it
 * does, and confirm. Confirming changes the project's workflow through the
 * API; nothing changes before that.
 */
export function ChangeWorkflowDialog({ open, projectId, current, onClose, onChanged }) {
  const client = useApiClient();
  const selectId = useId();
  const workflows = useResource(["workflows"], (apiClient, options) => listWorkflows(apiClient, options), { enabled: open });
  const [chosen, setChosen] = useState("");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setChosen("");
    setError(null);
  }, [open]);

  const others = (workflows.data ?? []).filter((workflow) => workflow.id !== current);
  const picked = others.find((workflow) => workflow.id === chosen) ?? null;

  async function confirm() {
    setSaving(true);
    setError(null);
    try {
      await updateProjectSettings(client, projectId, { workflowId: picked.id });
      onChanged();
    } catch (caught) {
      setError(errorSentence(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Use another workflow"
      description="Choose the workflow this project runs its tasks through."
      onClose={onClose}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!picked || saving} onClick={confirm}>
            {saving ? "Changing…" : picked ? `Use ${picked.name}` : "Use this workflow"}
          </Button>
        </>
      }
    >
      <div className="dialog__body">
        {workflows.error ? (
          <p className="notice notice--error" role="alert">
            {workflows.error}
          </p>
        ) : null}
        <div className="field">
          <label className="field__label" htmlFor={selectId}>
            Workflow
          </label>
          <select
            id={selectId}
            className="field__input"
            value={chosen}
            data-autofocus
            onChange={(event) => setChosen(event.target.value)}
          >
            <option value="">Choose a workflow</option>
            {others.map((workflow) => (
              <option key={workflow.id} value={workflow.id}>
                {workflow.name}
              </option>
            ))}
          </select>
        </div>
        {picked ? (
          <div className="change-workflow">
            <p>
              <Mono>{picked.id}</Mono> goes through {picked.steps.map((step) => stepLabel(step.id)).join(", then ")}.
            </p>
            <p>
              Tasks already underway are not moved. A task waiting at a step this workflow does not have cannot
              continue, so check the active sprint afterwards.
            </p>
          </div>
        ) : null}
        {error ? (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}
