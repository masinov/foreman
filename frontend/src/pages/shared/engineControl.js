import { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { pauseEngine, resumeEngine, startEngine, stopEngine } from "../../api/engine";
import { ENGINE_STATES } from "../../api/workspace";

/**
 * The engine's commands and what each says when requested. One module, two
 * presentations: the project page's engine row and the top bar's menu both
 * use `useEngineControl`.
 */
export const ENGINE_COMMANDS = {
  start: { call: startEngine, done: "Start requested." },
  resume: { call: resumeEngine, done: "Resume requested." },
  pause: { call: pauseEngine, done: "Pause requested." },
  stop: { call: stopEngine, done: "Stop requested." },
};

/** Which commands apply to an engine state. */
export function applicableCommands(state) {
  return {
    start: state === ENGINE_STATES.notRunning,
    resume: state === ENGINE_STATES.paused,
    pause: state === ENGINE_STATES.running,
    stop: state === ENGINE_STATES.running || state === ENGINE_STATES.paused,
  };
}

/**
 * Send commands to a project's engine. `send(name)` requests one; `pending`
 * names the one in flight and `notice` is `{ error, text }` for the last one:
 * confirmed, or the API's sentence when it refused. `onChanged` runs after a
 * command was accepted.
 */
export function useEngineControl({ projectId, onChanged }) {
  const client = useApiClient();
  const [pending, setPending] = useState(null);
  const [notice, setNotice] = useState(null);

  async function send(name) {
    setPending(name);
    setNotice(null);
    try {
      await ENGINE_COMMANDS[name].call(client, projectId);
      setNotice({ error: false, text: `${ENGINE_COMMANDS[name].done} The state here changes when the engine acts on it.` });
      onChanged?.();
    } catch (error) {
      setNotice({ error: true, text: errorSentence(error) });
    } finally {
      setPending(null);
    }
  }

  return { pending, busy: pending !== null, notice, send };
}
