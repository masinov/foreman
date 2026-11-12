import React, { useEffect, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { fileBacklogTask, TASK_TYPES } from "../../api/backlog";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";
import { humanize } from "../../ui/format";

/** File a task into the backlog. The project's triage policy decides if it is accepted. */
export function NewTaskDialog({ projectId, open, onClose, onFiled }) {
  const client = useApiClient();
  const [title, setTitle] = useState("");
  const [taskType, setTaskType] = useState(TASK_TYPES[0]);
  const [description, setDescription] = useState("");
  const [criteria, setCriteria] = useState("");
  const [titleError, setTitleError] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTitle("");
    setTaskType(TASK_TYPES[0]);
    setDescription("");
    setCriteria("");
    setTitleError(null);
    setError(null);
  }, [open]);

  async function submit(event) {
    event.preventDefault();
    if (!title.trim()) {
      setTitleError("A task needs a title.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const task = await fileBacklogTask(client, projectId, {
        title: title.trim(),
        taskType,
        description: description.trim(),
        acceptanceCriteria: criteria.trim(),
      });
      onFiled(task);
    } catch (caught) {
      setError(errorSentence(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="New task"
      description="It goes to the backlog. It is planned into a sprint from there."
      onClose={onClose}
    >
      <form className="dialog__body" onSubmit={submit} noValidate>
        <Field
          label="Title"
          value={title}
          onChange={(event) => {
            setTitle(event.target.value);
            setTitleError(null);
          }}
          error={titleError}
          required
          data-autofocus
        />
        <div className="field">
          <label className="field__label" htmlFor="new-task-type">
            Type
          </label>
          <select
            id="new-task-type"
            className="field__input"
            value={taskType}
            onChange={(event) => setTaskType(event.target.value)}
          >
            {TASK_TYPES.map((type) => (
              <option key={type} value={type}>
                {humanize(type)}
              </option>
            ))}
          </select>
        </div>
        <Field
          label="Description"
          hint="Optional. What needs doing and why."
          multiline
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
        <Field
          label="Acceptance criteria"
          hint="Optional. What is true when it is done."
          multiline
          value={criteria}
          onChange={(event) => setCriteria(event.target.value)}
        />
        {error ? (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="dialog__footer">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving}>
            {saving ? "Filing…" : "File task"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
