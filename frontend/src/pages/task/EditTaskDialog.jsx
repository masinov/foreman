import React, { useEffect, useId, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { TASK_TYPES } from "../../api/backlog";
import { errorSentence } from "../../api/client";
import { updateTask } from "../../api/tasks";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";
import { humanize } from "../../ui/format";

/**
 * Edit a task's title, type, description and acceptance criteria. When the
 * task is running or blocked the engine records the edit, and its next agent
 * step reads it.
 */
export function EditTaskDialog({ open, task, onClose, onSaved }) {
  const client = useApiClient();
  const typeId = useId();
  const [title, setTitle] = useState("");
  const [taskType, setTaskType] = useState(TASK_TYPES[0]);
  const [description, setDescription] = useState("");
  const [criteria, setCriteria] = useState("");
  const [titleError, setTitleError] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTitle(task.title ?? "");
    setTaskType(task.task_type ?? TASK_TYPES[0]);
    setDescription(task.description ?? "");
    setCriteria(task.acceptance_criteria ?? "");
    setTitleError(null);
    setError(null);
  }, [open, task.title, task.task_type, task.description, task.acceptance_criteria]);

  async function submit(event) {
    event.preventDefault();
    if (!title.trim()) {
      setTitleError("A task needs a title.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateTask(client, task.id, {
        title: title.trim(),
        taskType,
        description: description.trim(),
        acceptanceCriteria: criteria.trim(),
      });
      onSaved();
    } catch (caught) {
      setError(errorSentence(caught));
    } finally {
      setSaving(false);
    }
  }

  const types = TASK_TYPES.includes(taskType) ? TASK_TYPES : [taskType, ...TASK_TYPES];
  const live = task.status === "in_progress" || task.status === "blocked";
  return (
    <Dialog
      open={open}
      title="Edit task"
      description={live ? "The change is recorded, and the next agent step reads it." : undefined}
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
          <label className="field__label" htmlFor={typeId}>
            Type
          </label>
          <select id={typeId} className="field__input" value={taskType} onChange={(event) => setTaskType(event.target.value)}>
            {types.map((type) => (
              <option key={type} value={type}>
                {humanize(type)}
              </option>
            ))}
          </select>
        </div>
        <Field label="Description" multiline value={description} onChange={(event) => setDescription(event.target.value)} />
        <Field
          label="Acceptance criteria"
          hint="One per line."
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
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
