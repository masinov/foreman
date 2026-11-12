import React, { useEffect, useState } from "react";

import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";
import { plural } from "../../ui/format";

/**
 * Asks for the title and goal of the sprint the selected tasks are planned
 * into. `onSubmit({ title, goal })` does the planning and throws a sentence
 * (or returns an error string) the dialog shows when the API refuses.
 */
export function PlanNewSprintDialog({ open, taskCount, onClose, onSubmit }) {
  const [title, setTitle] = useState("");
  const [goal, setGoal] = useState("");
  const [titleError, setTitleError] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTitle("");
    setGoal("");
    setTitleError(null);
    setError(null);
  }, [open]);

  async function submit(event) {
    event.preventDefault();
    if (!title.trim()) {
      setTitleError("A sprint needs a title.");
      return;
    }
    setSaving(true);
    setError(null);
    const refusal = await onSubmit({ title: title.trim(), goal: goal.trim() });
    setSaving(false);
    if (refusal) setError(refusal);
  }

  return (
    <Dialog
      open={open}
      title="Plan into a new sprint"
      description={`${plural(taskCount, "task")} will move into it. It is planned last in the queue.`}
      onClose={onClose}
    >
      <form className="dialog__body" onSubmit={submit} noValidate>
        <Field
          label="Title"
          hint="The sprint number and what it is for."
          value={title}
          onChange={(event) => {
            setTitle(event.target.value);
            setTitleError(null);
          }}
          error={titleError}
          required
          data-autofocus
        />
        <Field
          label="Goal"
          hint="Optional. What is true when it is finished."
          multiline
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
        />
        {error ? (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="dialog__footer">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving}>
            {saving ? "Planning…" : "Create sprint and plan"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
