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
      description="It is planned last in the queue and runs after the sprints before it."
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
            {saving ? "Creating…" : "Create sprint"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
