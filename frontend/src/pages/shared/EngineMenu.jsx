import React from "react";

import { useResource } from "../../api/useResource";
import { getWorkspace } from "../../api/workspace";
import { Menu } from "../../ui/Menu";
import { StatusDot } from "../../ui/StatusDot";
import { applicableCommands, useEngineControl } from "./engineControl";
import { engineWords } from "./words";

/**
 * The engine below project level: its state in the top bar's right-hand slot,
 * as a menu of the commands that apply (Start, Pause or Resume, Stop). The
 * same commands as the project page's engine row (engineControl.js).
 */
export function EngineMenu({ projectId }) {
  const workspace = useResource(["workspace"], getWorkspace);
  const reload = workspace.reload;
  const { busy, notice, send } = useEngineControl({ projectId, onChanged: reload });
  const engine = workspace.data?.projects.find((project) => project.id === projectId)?.engine ?? null;
  if (!engine) return null;

  const { tone, word } = engineWords(engine.state);
  const applies = applicableCommands(engine.state);
  const items = [
    applies.start ? { key: "start", label: "Start", onSelect: () => send("start") } : null,
    applies.resume ? { key: "resume", label: "Resume", onSelect: () => send("resume") } : null,
    applies.pause ? { key: "pause", label: "Pause", onSelect: () => send("pause") } : null,
    applies.stop ? { key: "stop", label: "Stop", onSelect: () => send("stop") } : null,
  ].filter(Boolean);

  return (
    <div className="engine-menu">
      {notice ? (
        <span
          className={notice.error ? "engine-menu__notice engine-menu__notice--error" : "visually-hidden"}
          role={notice.error ? "alert" : "status"}
        >
          {notice.text}
        </span>
      ) : null}
      <Menu
        label="Engine"
        triggerClassName="engine-menu__trigger"
        triggerLabel={`Engine: ${word.toLowerCase()}. Start, pause or stop`}
        disabled={busy || items.length === 0}
        trigger={<StatusDot tone={tone}>{`Engine ${word.toLowerCase()}`}</StatusDot>}
        items={items}
      />
    </div>
  );
}
