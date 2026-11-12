import React, { useEffect, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { updateSprint } from "../../api/sprints";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";

/** Edit a sprint's title and goal. A refusal from the API is shown as its sentence. */
export function EditSprintDialog({ open, sprint, onClose, onSaved }) {
  const client = useApiClient();
  const [title, setTitle] = useState("");
  const [goal, setGoal] = useState("");
  const [titleError, setTitleError] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTitle(sprint.title ?? "");
    setGoal(sprint.goal ?? "");
    setTitleError(null);
    setError(null);
  }, [open, sprint.title, sprint.goal]);

  async function submit(event) {
    event.preventDefault();
    if (!title.trim()) {
      setTitleError("A sprint needs a title.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateSprint(client, sprint.id, { title: title.trim(), goal: goal.trim() });
      onSaved();
    } catch (failure) {
      setError(errorSentence(failure));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} title="Edit sprint" onClose={onClose}>
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
        <Field label="Goal" hint="Optional. What is true when it is finished." multiline value={goal} onChange={(event) => setGoal(event.target.value)} />
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
