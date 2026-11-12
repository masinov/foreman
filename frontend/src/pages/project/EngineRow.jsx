import React from "react";

import { ENGINE_STATES } from "../../api/workspace";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { StatusDot } from "../../ui/StatusDot";
import { humanize } from "../../ui/format";
import { applicableCommands, useEngineControl } from "../shared/engineControl";
import { engineWords } from "../shared/words";

function TaskRef({ engine }) {
  return (
    <Link className="row-link" href={paths.task(engine.task_id)}>
      <Mono>{engine.task_key || engine.task_title}</Mono>
    </Link>
  );
}

/** What the engine's state means now, in a sentence. */
function EngineSentence({ engine }) {
  const step = engine?.step ? humanize(engine.step).toLowerCase() : null;
  if (engine?.state === ENGINE_STATES.running) {
    if (!engine.task_id) {
      return "Nothing is being worked on now. It takes the next task in the active sprint when one is ready.";
    }
    return (
      <>
        Working on <TaskRef engine={engine} />
        {step ? `, ${step}` : ""}.
      </>
    );
  }
  if (engine?.state === ENGINE_STATES.paused) {
    if (!engine.task_id) return "Paused. Nothing new starts until it is resumed.";
    return (
      <>
        Paused. Nothing new starts until it is resumed; <TaskRef engine={engine} /> resumes
        {step ? ` from ${step}` : ""}.
      </>
    );
  }
  return "Nothing is being worked on. Decisions you make are carried out when it starts.";
}

/**
 * The project's engine: its state, a sentence on what that means now, and
 * Start, Pause or Resume, and Stop. A control that does not apply to the
 * state is disabled; a command the API refuses shows its sentence.
 */
export function EngineRow({ projectId, engine, onChanged }) {
  const { pending, busy, notice, send } = useEngineControl({ projectId, onChanged });
  const state = engine?.state ?? null;
  const applies = applicableCommands(state);
  const paused = state === ENGINE_STATES.paused;
  const { tone, word } = engineWords(state);

  return (
    <section className="engine" aria-labelledby="engine-title">
      <h2 className="engine__label" id="engine-title">
        Engine
      </h2>
      <div className="engine__state">
        {state ? <StatusDot tone={tone}>{word}</StatusDot> : null}
        {state ? (
          <p className="engine__sentence">
            <EngineSentence engine={engine} />
          </p>
        ) : null}
      </div>
      <div className="engine__controls">
        <Button disabled={busy || !applies.start} onClick={() => send("start")}>
          {pending === "start" ? "Starting…" : "Start"}
        </Button>
        {paused ? (
          <Button disabled={busy} onClick={() => send("resume")}>
            {pending === "resume" ? "Resuming…" : "Resume"}
          </Button>
        ) : (
          <Button disabled={busy || !applies.pause} onClick={() => send("pause")}>
            {pending === "pause" ? "Pausing…" : "Pause"}
          </Button>
        )}
        <Button disabled={busy || !applies.stop} onClick={() => send("stop")}>
          {pending === "stop" ? "Stopping…" : "Stop"}
        </Button>
      </div>
      {notice ? (
        <p
          className={notice.error ? "notice notice--error engine__notice" : "notice engine__notice"}
          role={notice.error ? "alert" : "status"}
        >
          {notice.text}
        </p>
      ) : null}
    </section>
  );
}
