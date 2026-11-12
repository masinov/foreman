import React, { useEffect, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { createSprint } from "../../api/sprints";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";

/** Create a planned sprint; it joins the end of the queue. */
export function NewSprintDialog({ projectId, open, onClose, onCreated }) {
  const client = useApiClient();
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
    try {
      const sprint = await createSprint(client, projectId, { title: title.trim(), goal: goal.trim() });
      onCreated(sprint);
    } catch (caught) {
      setError(errorSentence(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="New sprint"
      description="It joins the end of the queue and starts empty. Add tasks on its page, new or from the backlog."
      onClose={onClose}
    >
      <form className="dialog__body" onSubmit={submit} noValidate>
        <Field
          label="Title"
          hint="A short name for this batch of work."
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
          hint="Optional. What should be true when it is finished. Agents working in the sprint are told it."
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
            {saving ? "Creating…" : "Create sprint"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
