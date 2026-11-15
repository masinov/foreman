import React, { useEffect, useId, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { TASK_SIZES, TASK_TYPES } from "../../api/backlog";
import { errorSentence } from "../../api/client";
import { listSprintTasks } from "../../api/sprints";
import { updateTask } from "../../api/tasks";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";
import { humanize } from "../../ui/format";
import { WaitsFor } from "../shared/WaitsFor";

// What a task waits for can change only before it starts, and only among
// the tasks of a sprint: the backlog has no run order.
const NOT_STARTED = new Set(["triage", "todo"]);
const OPEN = new Set(["triage", "todo", "in_progress", "blocked"]);

/**
 * Edit a task's title, type, description, acceptance criteria, size and
 * priority, and, before it starts, the tasks of its sprint it waits for.
 * When the task is running or blocked the engine records the edit, and its
 * next agent step reads it.
 */
export function EditTaskDialog({ open, task, onClose, onSaved }) {
  const client = useApiClient();
  const typeId = useId();
  const sizeId = useId();
  const [title, setTitle] = useState("");
  const [taskType, setTaskType] = useState(TASK_TYPES[0]);
  const [description, setDescription] = useState("");
  const [criteria, setCriteria] = useState("");
  const [size, setSize] = useState("");
  const [priority, setPriority] = useState("0");
  const [priorityError, setPriorityError] = useState(null);
  const [waitsFor, setWaitsFor] = useState(() => new Set());
  const canWait = !task.in_backlog && Boolean(task.sprint_id) && NOT_STARTED.has(task.status);
  const siblings = useResource(
    ["sprint-tasks", task.sprint_id ?? null],
    (apiClient, options) => listSprintTasks(apiClient, task.sprint_id, options),
    { enabled: open && canWait },
  );
  // Unfinished tasks of the sprint, and whatever it already waits for, so
  // that can be unticked even when it is done.
  const waitedFor = task.depends_on_task_ids ?? [];
  const candidates = (siblings.data ?? []).filter(
    (other) => other.id !== task.id && (OPEN.has(other.status) || waitedFor.includes(other.id)),
  );
  const [titleError, setTitleError] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTitle(task.title ?? "");
    setTaskType(task.task_type ?? TASK_TYPES[0]);
    setDescription(task.description ?? "");
    setCriteria(task.acceptance_criteria ?? "");
    setSize(task.complexity ?? "");
    setPriority(String(task.priority ?? 0));
    setWaitsFor(new Set(task.depends_on_task_ids ?? []));
    setTitleError(null);
    setPriorityError(null);
    setError(null);
    // The list it waits for is compared by content: the page reads the task
    // again while the dialog is open, and a new array is not a new answer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, task.title, task.task_type, task.description, task.acceptance_criteria, task.complexity, task.priority, waitedFor.join(" ")]);

  async function submit(event) {
    event.preventDefault();
    if (!title.trim()) {
      setTitleError("A task needs a title.");
      return;
    }
    const priorityNumber = priority.trim() === "" ? 0 : Number(priority);
    if (!Number.isInteger(priorityNumber)) {
      setPriorityError("A whole number. Lower runs first.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const fields = {
        title: title.trim(),
        taskType,
        description: description.trim(),
        acceptanceCriteria: criteria.trim(),
        complexity: size,
        priority: priorityNumber,
      };
      if (canWait) fields.dependsOn = [...waitsFor];
      await updateTask(client, task.id, fields);
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
        <div className="field-pair">
          <div className="field">
            <label className="field__label" htmlFor={sizeId}>
              Size
            </label>
            <select id={sizeId} className="field__input" value={size} onChange={(event) => setSize(event.target.value)}>
              <option value="">Not said</option>
              {TASK_SIZES.map((entry) => (
                <option key={entry} value={entry}>
                  {humanize(entry)}
                </option>
              ))}
            </select>
          </div>
          <Field
            label="Priority"
            hint="Lower runs first. 0 is the default."
            inputMode="numeric"
            value={priority}
            onChange={(event) => {
              setPriority(event.target.value);
              setPriorityError(null);
            }}
            error={priorityError}
          />
        </div>
        {canWait ? <WaitsFor candidates={candidates} value={waitsFor} onChange={setWaitsFor} /> : null}
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
