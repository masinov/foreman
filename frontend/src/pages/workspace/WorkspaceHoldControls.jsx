import React, { useState } from "react";

import { blockAll, pauseAll, resumeAll, stopAll, unblockAll } from "../../api/holds";
import { Button } from "../../ui/Button";
import { ReasonDialog } from "../shared/ReasonDialog";
import { useHoldAction } from "../shared/useHoldAction";
import { changedSentence } from "../shared/workWords";

/** What the workspace's controls can do, from every project's work and the workspace's block. */
export function workspaceControls(projects, block) {
  const works = (projects ?? []).map((project) => project.work).filter(Boolean);
  const paused = works.reduce((sum, work) => sum + (work.paused ?? 0), 0);
  const unpaused = works.reduce((sum, work) => sum + Math.max(0, (work.unfinished ?? 0) - (work.paused ?? 0)), 0);
  const running = works.some((work) => work.step_running && work.state !== "stopping");
  return {
    pause: !block && unpaused > 0,
    stop: !block && running,
    resume: !block && paused > 0,
    block: !block && (projects ?? []).length > 0,
    unblock: Boolean(block),
  };
}

/**
 * Pause all, Stop all, Resume all, and Block or Unblock the workspace
 * (ADR-0043). Pause, Stop and Resume act on each task of every planned or
 * active sprint; Block holds every project's work, with a reason.
 */
export function WorkspaceHoldControls({ projects, block, onChanged }) {
  const { pending, busy, notice, act, client, show } = useHoldAction({ onChanged });
  const [blocking, setBlocking] = useState(false);
  const applies = workspaceControls(projects, block);
  const keys = (result) => result?.task_keys ?? [];
  return (
    <>
      {applies.unblock ? (
        <Button
          icon="play"
          disabled={busy}
          title={block?.reason}
          onClick={() => act("unblock", (c) => unblockAll(c), () => "Unblocked the workspace.")}
        >
          {pending === "unblock" ? "Unblocking…" : "Unblock all"}
        </Button>
      ) : null}
      {applies.resume ? (
        <Button icon="play" disabled={busy} onClick={() => act("resume", (c) => resumeAll(c), (r) => changedSentence("Resumed", keys(r)))}>
          {pending === "resume" ? "Resuming…" : "Resume all"}
        </Button>
      ) : null}
      {applies.pause ? (
        <Button icon="pause" disabled={busy} onClick={() => act("pause", (c) => pauseAll(c), (r) => changedSentence("Paused", keys(r)))}>
          {pending === "pause" ? "Pausing…" : "Pause all"}
        </Button>
      ) : null}
      {applies.stop ? (
        <Button
          icon="stop"
          variant="stop"
          disabled={busy}
          onClick={() => act("stop", (c) => stopAll(c), (r) => changedSentence("Stopped", keys(r)))}
        >
          {pending === "stop" ? "Stopping…" : "Stop all"}
        </Button>
      ) : null}
      {applies.block ? (
        <Button variant="quiet" disabled={busy} onClick={() => setBlocking(true)}>
          Block all
        </Button>
      ) : null}
      {notice ? (
        <p className="notice notice--error hold-controls__notice" role="alert">
          {notice}
        </p>
      ) : null}
      <ReasonDialog
        open={blocking}
        title="Block every project"
        effect="Nothing in any project runs until someone unblocks the workspace: running steps finish first. No sprint is finished or started meanwhile."
        ask="Why it is blocked"
        hint="Shown wherever it holds work."
        required
        confirm="Block all"
        doing="Blocking…"
        run={(text) => blockAll(client, text)}
        onClose={() => setBlocking(false)}
        onDone={() => {
          setBlocking(false);
          show("Blocked the workspace.");
          onChanged?.();
        }}
      />
    </>
  );
}
