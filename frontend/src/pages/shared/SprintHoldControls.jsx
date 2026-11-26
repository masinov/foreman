import React, { useState } from "react";

import { blockSprint, pauseSprint, resumeSprint, stopSprint, unblockSprint } from "../../api/holds";
import { Button } from "../../ui/Button";
import { ReasonDialog } from "./ReasonDialog";
import { useHoldAction } from "./useHoldAction";
import { changedSentence, workControls } from "./workWords";

/**
 * Pause, Stop, Resume, Block and Unblock of one sprint's work (ADR-0043).
 * Pause and Resume act on each task in it; Stop cuts the running step; Block
 * holds the whole sprint, with a reason, until Unblock. Only the controls that
 * would do something are shown (`workControls`). `work` is the sprint's
 * status line from the API. `showBlock` false leaves Block to a menu the page
 * has (the sprint page's More).
 */
export function SprintHoldControls({ sprintId, work, planned = false, showBlock = true, onChanged }) {
  const { pending, busy, notice, act, client, show } = useHoldAction({ onChanged });
  const [blocking, setBlocking] = useState(false);
  if (!sprintId || !work) return null;
  const applies = workControls(work, { planned });
  const keys = (result) => result?.task_keys ?? [];

  return (
    <div className="hold-controls">
      {applies.unblock ? (
        <Button
          icon="play"
          disabled={busy}
          onClick={() => act("unblock", (client) => unblockSprint(client, sprintId), () => "Unblocked the sprint.")}
        >
          {pending === "unblock" ? "Unblocking…" : "Unblock"}
        </Button>
      ) : null}
      {applies.resume ? (
        <Button
          icon="play"
          disabled={busy}
          onClick={() =>
            act("resume", (client) => resumeSprint(client, sprintId), (result) => changedSentence("Resumed", keys(result)))
          }
        >
          {pending === "resume" ? "Resuming…" : "Resume"}
        </Button>
      ) : null}
      {applies.pause ? (
        <Button
          icon="pause"
          disabled={busy}
          onClick={() =>
            act("pause", (client) => pauseSprint(client, sprintId), (result) => changedSentence("Paused", keys(result)))
          }
        >
          {pending === "pause" ? "Pausing…" : "Pause"}
        </Button>
      ) : null}
      {applies.stop ? (
        <Button
          icon="stop"
          variant="stop"
          disabled={busy}
          onClick={() =>
            act("stop", (client) => stopSprint(client, sprintId), (result) => changedSentence("Stopped", keys(result)))
          }
        >
          {pending === "stop" ? "Stopping…" : "Stop"}
        </Button>
      ) : null}
      {showBlock && applies.block ? (
        <Button variant="quiet" disabled={busy} onClick={() => setBlocking(true)}>
          Block
        </Button>
      ) : null}
      {notice ? (
        <p className="notice notice--error hold-controls__notice" role="alert">
          {notice}
        </p>
      ) : null}
      <ReasonDialog
        open={blocking}
        title="Block this sprint"
        effect="Nothing in the sprint runs until someone unblocks it: a running step finishes first. It waits in Needs you."
        ask="Why it is blocked"
        hint="Shown wherever it holds work."
        required
        confirm="Block sprint"
        doing="Blocking…"
        run={(text) => blockSprint(client, sprintId, text)}
        onClose={() => setBlocking(false)}
        onDone={() => {
          setBlocking(false);
          show("Blocked the sprint.");
          onChanged?.();
        }}
      />
    </div>
  );
}
