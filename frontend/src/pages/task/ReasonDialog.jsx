import React, { useEffect, useState } from "react";

import { errorSentence } from "../../api/client";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";

/**
 * Confirm an action on a task. The dialog says what will happen
 * (`effect`); with `ask` it also takes a text (guidance, a reason), required
 * when `required`. `run(text)` performs the action; a refusal is shown as the
 * API's sentence and the dialog stays open. Without a text to write, focus
 * starts on the button that changes nothing.
 */
export function ReasonDialog({ open, title, effect, ask, hint, required = false, confirm, doing, run, onClose, onDone }) {
  const [text, setText] = useState("");
  const [textError, setTextError] = useState(null);
  const [refusal, setRefusal] = useState(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!open) return;
    setText("");
    setTextError(null);
    setRefusal(null);
  }, [open]);

  async function submit(event) {
    event.preventDefault();
    if (ask && required && !text.trim()) {
      setTextError(`${ask} is needed.`);
      return;
    }
    setPending(true);
    setRefusal(null);
    try {
      const result = await run(text.trim());
      onDone(result);
    } catch (error) {
      setRefusal(errorSentence(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} title={title} description={effect} onClose={onClose}>
      <form className="dialog__body" onSubmit={submit} noValidate>
        {ask ? (
          <Field
            label={ask}
            hint={hint}
            multiline
            value={text}
            required={required}
            error={textError}
            onChange={(event) => {
              setText(event.target.value);
              setTextError(null);
            }}
            data-autofocus
          />
        ) : null}
        {refusal ? (
          <p className="notice notice--error" role="alert">
            {refusal}
          </p>
        ) : null}
        <div className="dialog__footer">
          <Button onClick={onClose}>Keep it as it is</Button>
          <Button type="submit" disabled={pending}>
            {pending ? doing : confirm}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
