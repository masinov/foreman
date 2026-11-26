import React from "react";

import { startWorker } from "../../api/engine";
import { pauseSprint, resumeSprint, stopSprint, unblockSprint } from "../../api/holds";
import { useResource } from "../../api/useResource";
import { getWorkspace } from "../../api/workspace";
import { Menu } from "../../ui/Menu";
import { StatusDot } from "../../ui/StatusDot";
import { useHoldAction } from "./useHoldAction";
import { changedSentence, workControls, workWords } from "./workWords";

/**
 * The project's work below project level (ADR-0043): the active sprint's
 * status line in the top bar's right-hand slot, as a menu of what applies
 * (Resume, Pause, Stop, Unblock, Start worker). Block takes a reason and is on
 * the sprint's page.
 */
export function WorkMenu({ projectId }) {
  const workspace = useResource(["workspace"], getWorkspace);
  const { busy, notice, act } = useHoldAction({ onChanged: workspace.reload });
  const project = workspace.data?.projects.find((item) => item.id === projectId) ?? null;
  if (!project) return null;
  const sprintId = project.active_sprint?.id ?? null;
  const work = project.work ?? null;
  const { tone, text } = workWords(work);
  const applies = sprintId ? workControls(work) : {};
  const keys = (result) => result?.task_keys ?? [];
  const items = [
    applies.unblock
      ? { key: "unblock", label: "Unblock", onSelect: () => act("unblock", (c) => unblockSprint(c, sprintId), () => "Unblocked the sprint.") }
      : null,
    applies.resume
      ? { key: "resume", label: "Resume", onSelect: () => act("resume", (c) => resumeSprint(c, sprintId), (r) => changedSentence("Resumed", keys(r))) }
      : null,
    applies.pause
      ? { key: "pause", label: "Pause", onSelect: () => act("pause", (c) => pauseSprint(c, sprintId), (r) => changedSentence("Paused", keys(r))) }
      : null,
    applies.stop
      ? { key: "stop", label: "Stop", onSelect: () => act("stop", (c) => stopSprint(c, sprintId), (r) => changedSentence("Stopped", keys(r))) }
      : null,
    work?.no_worker
      ? { key: "worker", label: "Start worker", onSelect: () => act("worker", (c) => startWorker(c, projectId), () => "Starting a worker.") }
      : null,
  ].filter(Boolean);

  return (
    <div className="work-menu">
      {notice ? (
        <span className="work-menu__notice work-menu__notice--error" role="alert">
          {notice}
        </span>
      ) : null}
      <Menu
        label="Work"
        triggerClassName="work-menu__trigger"
        triggerLabel={`Work: ${text}. ${items.length ? items.map((item) => item.label).join(", ") : "Nothing to do"}`}
        disabled={busy || items.length === 0}
        trigger={<StatusDot tone={tone}>{text}</StatusDot>}
        items={items}
      />
    </div>
  );
}
