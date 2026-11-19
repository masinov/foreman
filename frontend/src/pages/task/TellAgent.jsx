import React, { useId, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { sendGuidance, steerTask } from "../../api/tasks";
import { Button } from "../../ui/Button";
import { formatDayTime, humanize } from "../../ui/format";

/** A step an agent is doing right now. */
export const agentAtWork = (run) => run.status === "running" && !String(run.role_id || "").startsWith("_builtin:");

/** Whether an agent step has been given a note, in words. */
export function noteState(note) {
  if (!note.delivered) return { tone: "attention", word: "Waiting for the developer's next step" };
  const step = note.delivered_step ? humanize(note.delivered_step).toLowerCase() : "";
  const when = formatDayTime(note.delivered_at);
  return { tone: "passed", word: ["Read by the agent", step ? `at ${step}` : "", when ? `on ${when}` : ""].filter(Boolean).join(" ") };
}

/**
 * The one place to tell a task's agent something: the bottom of the
 * conversation with it, in the task's side bar.
 *
 * A note is for the developer (the agent doing the work); a reviewer sees
 * notes as context, not as instructions (the owner, 2026-11-19).
 *
 * `running` is the agent step in progress, if there is one. Then there are
 * two ways to send: "Interrupt and tell it now" stops that step and starts
 * it again with the note; "Save for the developer" leaves it alone, and the
 * developer reads it on its next step. With no step in progress the note
 * can only wait for that.
 */
export function TellAgent({ task, running, onSent }) {
  const client = useApiClient();
  const fieldId = useId();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  async function send(request) {
    if (!text.trim()) {
      setNotice({ error: true, text: "Write what to tell it first." });
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      const result = await request(client, task.id, text.trim());
      setText("");
      setNotice({ error: false, text: result?.message || "Recorded." });
      onSent?.();
    } catch (error) {
      setNotice({ error: true, text: errorSentence(error) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="guidance tell-agent"
      aria-label="Tell the agent"
      onSubmit={(event) => {
        event.preventDefault();
        send(running ? steerTask : sendGuidance);
      }}
      noValidate
    >
      <label className="field__label" htmlFor={fieldId}>
        {running ? `Tell the agent (${humanize(running.step)} is running)` : "Tell the agent"}
      </label>
      <textarea
        id={fieldId}
        className="field__input field__input--multiline"
        rows={2}
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      <div className="guidance__actions">
        {running ? (
          <>
            <Button type="submit" disabled={busy}>
              Interrupt and tell it now
            </Button>
            <Button variant="quiet" disabled={busy} onClick={() => send(sendGuidance)}>
              Save for the developer
            </Button>
          </>
        ) : (
          <Button type="submit" disabled={busy}>
            Save for the developer
          </Button>
        )}
        {notice ? (
          <span className={notice.error ? "notice notice--error" : "notice"} role={notice.error ? "alert" : "status"}>
            {notice.text}
          </span>
        ) : null}
      </div>
    </form>
  );
}
