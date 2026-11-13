import React, { useEffect, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { createProject, listWorkflows } from "../../api/projects";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";

const DEFAULT_WORKFLOW = "development";

/**
 * Register a repository as a project. The folder must already exist on the
 * machine Foreman runs on; the API says so when it does not.
 */
export function AddProjectDialog({ open, onClose, onAdded }) {
  const client = useApiClient();
  const workflows = useResource(["workflows"], listWorkflows, { enabled: open });
  const [name, setName] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [workflowId, setWorkflowId] = useState(DEFAULT_WORKFLOW);
  const [errors, setErrors] = useState({});
  const [refusal, setRefusal] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName("");
    setRepoPath("");
    setWorkflowId(DEFAULT_WORKFLOW);
    setErrors({});
    setRefusal(null);
  }, [open]);

  async function submit(event) {
    event.preventDefault();
    const missing = {};
    if (!name.trim()) missing.name = "A project needs a name.";
    if (!repoPath.trim()) missing.repoPath = "Say where the repository is.";
    setErrors(missing);
    if (Object.keys(missing).length) return;
    setSaving(true);
    setRefusal(null);
    try {
      const project = await createProject(client, { name: name.trim(), repoPath: repoPath.trim(), workflowId });
      onAdded(project);
    } catch (caught) {
      setRefusal(errorSentence(caught));
    } finally {
      setSaving(false);
    }
  }

  const options = workflows.data ?? [];
  return (
    <Dialog
      open={open}
      title="Add a project"
      description="A project is one repository on this machine. Nothing in it changes until a sprint is started."
      onClose={onClose}
    >
      <form className="dialog__body" onSubmit={submit} noValidate>
        <Field
          label="Name"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setErrors((current) => ({ ...current, name: null }));
          }}
          error={errors.name}
          required
          data-autofocus
        />
        <Field
          label="Repository folder"
          hint="The full path on the machine Foreman runs on, for example /home/you/src/shop."
          value={repoPath}
          onChange={(event) => {
            setRepoPath(event.target.value);
            setErrors((current) => ({ ...current, repoPath: null }));
          }}
          error={errors.repoPath}
          required
        />
        <div className="field">
          <label className="field__label" htmlFor="add-project-workflow">
            Workflow
          </label>
          <select
            id="add-project-workflow"
            className="field__input"
            value={workflowId}
            onChange={(event) => setWorkflowId(event.target.value)}
          >
            {options.length === 0 ? <option value={DEFAULT_WORKFLOW}>{DEFAULT_WORKFLOW}</option> : null}
            {options.map((workflow) => (
              <option key={workflow.id} value={workflow.id}>
                {workflow.name}
              </option>
            ))}
          </select>
          <span className="field__hint">The steps every task goes through. It can be changed in project settings.</span>
        </div>
        {workflows.error ? (
          <p className="notice notice--error" role="alert">
            {workflows.error}
          </p>
        ) : null}
        {refusal ? (
          <p className="notice notice--error" role="alert">
            {refusal}
          </p>
        ) : null}
        <div className="dialog__footer">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving}>
            {saving ? "Adding…" : "Add project"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
