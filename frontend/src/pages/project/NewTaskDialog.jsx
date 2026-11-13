import React, { useEffect, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { fileBacklogTask, TASK_SIZES, TASK_TYPES } from "../../api/backlog";
import { createSprintTask, listSprintTasks } from "../../api/sprints";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Disclosure } from "../../ui/Disclosure";
import { Field } from "../../ui/Field";
import { humanize, plural } from "../../ui/format";
import { Mono } from "../../ui/Mono";

/**
 * Write a new task. Without `sprint` it is filed into the backlog, where the
 * project's triage policy decides if it is accepted. With `sprint` it goes
 * straight into that sprint, where it can also be made to wait for other
 * tasks of the sprint.
 */
const OPEN = new Set(["todo", "in_progress", "blocked"]);

export function NewTaskDialog({ projectId, sprint = null, open, onClose, onFiled }) {
  const client = useApiClient();
  const [title, setTitle] = useState("");
  const [taskType, setTaskType] = useState(TASK_TYPES[0]);
  const [description, setDescription] = useState("");
  const [criteria, setCriteria] = useState("");
  const [size, setSize] = useState("");
  const [waitsFor, setWaitsFor] = useState(() => new Set());
  // Only unfinished tasks of the same sprint can be waited for.
  const siblings = useResource(
    ["sprint-tasks", sprint?.id ?? null],
    (apiClient, options) => listSprintTasks(apiClient, sprint.id, options),
    { enabled: open && Boolean(sprint) },
  );
  const candidates = (siblings.data ?? []).filter((task) => OPEN.has(task.status));
  const [titleError, setTitleError] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTitle("");
    setTaskType(TASK_TYPES[0]);
    setDescription("");
    setCriteria("");
    setSize("");
    setWaitsFor(new Set());
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
      const fields = {
        title: title.trim(),
        taskType,
        description: description.trim(),
        acceptanceCriteria: criteria.trim(),
        complexity: size,
      };
      if (sprint) fields.dependsOn = [...waitsFor];
      const task = sprint
        ? await createSprintTask(client, sprint.id, fields)
        : await fileBacklogTask(client, projectId, fields);
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
      description={
        sprint
          ? `It goes straight into ${sprint.title} and runs with it.`
          : "It goes to the backlog. It is planned into a sprint from there."
      }
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
        <div className="field">
          <label className="field__label" htmlFor="new-task-size">
            Size
          </label>
          <select id="new-task-size" className="field__input" value={size} onChange={(event) => setSize(event.target.value)}>
            <option value="">Not said</option>
            {TASK_SIZES.map((entry) => (
              <option key={entry} value={entry}>
                {humanize(entry)}
              </option>
            ))}
          </select>
          <span className="field__hint">Optional. A workflow can send small and large tasks to different models.</span>
        </div>
        {sprint && candidates.length > 0 ? (
          <Disclosure
            summary={waitsFor.size ? `Waits for ${plural(waitsFor.size, "task")}` : "Make it wait for other tasks"}
          >
            <p className="field__hint">It does not start until every task ticked here is done.</p>
            <ul className="choice-list">
              {candidates.map((task) => (
                <li key={task.id}>
                  <label className="choice-list__label">
                    <input
                      type="checkbox"
                      className="checkbox"
                      checked={waitsFor.has(task.id)}
                      onChange={() =>
                        setWaitsFor((current) => {
                          const next = new Set(current);
                          if (next.has(task.id)) next.delete(task.id);
                          else next.add(task.id);
                          return next;
                        })
                      }
                    />
                    {task.task_key ? <Mono quiet>{task.task_key}</Mono> : null}
                    <span>{task.title}</span>
                  </label>
                </li>
              ))}
            </ul>
          </Disclosure>
        ) : null}
        {error ? (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="dialog__footer">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving}>
            {saving ? (sprint ? "Adding…" : "Filing…") : sprint ? "Add task" : "File task"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
