import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { pauseEngine, resumeEngine, startEngine, stopEngine } from "../../api/engine";
import { ENGINE_STATES } from "../../api/workspace";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { StatusDot } from "../../ui/StatusDot";
import { humanize } from "../../ui/format";
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

const COMMANDS = {
  start: { call: startEngine, done: "Start requested." },
  resume: { call: resumeEngine, done: "Resume requested." },
  pause: { call: pauseEngine, done: "Pause requested." },
  stop: { call: stopEngine, done: "Stop requested." },
};

/**
 * The project's engine: its state, a sentence on what that means now, and
 * Start, Pause or Resume, and Stop. A control that does not apply to the
 * state is disabled; a command the API refuses shows its sentence.
 */
export function EngineRow({ projectId, engine, onChanged }) {
  const client = useApiClient();
  const [pending, setPending] = useState(null);
  const [notice, setNotice] = useState(null);
  const state = engine?.state ?? null;
  const running = state === ENGINE_STATES.running;
  const paused = state === ENGINE_STATES.paused;
  const notRunning = state === ENGINE_STATES.notRunning;
  const { tone, word } = engineWords(state);

  async function send(name) {
    setPending(name);
    setNotice(null);
    try {
      await COMMANDS[name].call(client, projectId);
      setNotice({ error: false, text: `${COMMANDS[name].done} The state here changes when the engine acts on it.` });
      onChanged?.();
    } catch (error) {
      setNotice({ error: true, text: errorSentence(error) });
    } finally {
      setPending(null);
    }
  }

  const busy = pending !== null;
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
        <Button disabled={busy || !notRunning} onClick={() => send("start")}>
          {pending === "start" ? "Starting…" : "Start"}
        </Button>
        {paused ? (
          <Button disabled={busy} onClick={() => send("resume")}>
            {pending === "resume" ? "Resuming…" : "Resume"}
          </Button>
        ) : (
          <Button disabled={busy || !running} onClick={() => send("pause")}>
            {pending === "pause" ? "Pausing…" : "Pause"}
          </Button>
        )}
        <Button disabled={busy || !(running || paused)} onClick={() => send("stop")}>
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
