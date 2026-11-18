import React, { useEffect, useId, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { cancelTask, completeTask } from "../../api/tasks";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";

/**
 * The two ways a person ends a task by hand, in the order they are offered.
 * `run(client, task, reason)` performs it; `done` is the sentence shown after.
 */
export const CLOSE_WAYS = [
  {
    key: "cancel",
    word: "Not needed",
    effect: "Marked cancelled. Its worktree is removed; its branch and history stay.",
    confirm: "Cancel task",
    doing: "Cancelling…",
    run: (client, task) => cancelTask(client, task.id),
    done: "Cancelled.",
  },
  {
    key: "complete",
    word: "Already done",
    effect: "Marked done on your word. Foreman tests, reviews and merges nothing; its branch and worktree stay.",
    confirm: "Mark done",
    doing: "Marking done…",
    ask: "Why it is done",
    hint: "For example where it was merged. Shown on the task.",
    run: (client, task, reason) => completeTask(client, task.id, reason),
    done: "Marked done.",
  },
];

/**
 * End a task by hand: as not needed (cancelled) or as already done. The
 * person says which; "already done" also takes the reason, which is the only
 * trace that Foreman did not check it. A refusal is shown as the API's
 * sentence and the dialog stays open. `onDone(sentence)` runs once the API
 * accepted it.
 */
export function CloseTaskDialog({ open, task, onClose, onDone }) {
  const client = useApiClient();
  const group = useId();
  const [wayKey, setWayKey] = useState(null);
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState(null);
  const [refusal, setRefusal] = useState(null);
  const [pending, setPending] = useState(false);
  const way = CLOSE_WAYS.find((entry) => entry.key === wayKey) ?? null;

  useEffect(() => {
    if (!open) return;
    setWayKey(null);
    setReason("");
    setProblem(null);
    setRefusal(null);
  }, [open]);

  async function submit(event) {
    event.preventDefault();
    if (!way) {
      setProblem({ on: "way", text: "Say how it ends." });
      return;
    }
    if (way.ask && !reason.trim()) {
      setProblem({ on: "reason", text: `${way.ask} is needed.` });
      return;
    }
    setPending(true);
    setRefusal(null);
    try {
      await way.run(client, task, reason.trim());
      onDone(way.done);
    } catch (error) {
      setRefusal(errorSentence(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Close this task"
      description="The task leaves the queue and none of its remaining steps run. It can be reopened."
      onClose={onClose}
    >
      <form className="dialog__body" onSubmit={submit} noValidate>
        <fieldset className="close-ways" aria-describedby={problem?.on === "way" ? `${group}-problem` : undefined}>
          <legend className="field__label">How it ends</legend>
          {CLOSE_WAYS.map((entry) => (
            <label key={entry.key} className="close-ways__way">
              <input
                type="radio"
                name={group}
                value={entry.key}
                checked={wayKey === entry.key}
                onChange={() => {
                  setWayKey(entry.key);
                  setProblem(null);
                }}
              />
              <span className="close-ways__words">
                <span>{entry.word}</span>
                <span className="quiet">{entry.effect}</span>
              </span>
            </label>
          ))}
          {problem?.on === "way" ? (
            <span className="field__error" id={`${group}-problem`} role="alert">
              {problem.text}
            </span>
          ) : null}
        </fieldset>
        {way?.ask ? (
          <Field
            label={way.ask}
            hint={way.hint}
            multiline
            value={reason}
            required
            error={problem?.on === "reason" ? problem.text : null}
            onChange={(event) => {
              setReason(event.target.value);
              setProblem(null);
            }}
          />
        ) : null}
        {refusal ? (
          <p className="notice notice--error" role="alert">
            {refusal}
          </p>
        ) : null}
        <div className="dialog__footer">
          <Button onClick={onClose}>
            Keep it as it is
          </Button>
          <Button type="submit" disabled={pending}>
            {pending ? way.doing : (way?.confirm ?? "Close task")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
