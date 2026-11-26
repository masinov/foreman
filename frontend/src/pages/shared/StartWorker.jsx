import React from "react";

import { startWorker } from "../../api/engine";
import { Button } from "../../ui/Button";
import { useHoldAction } from "./useHoldAction";

/**
 * Start a worker for a project none runs (ADR-0043): the one worker control
 * on the page, shown beside "no worker". It is a fault to fix, not a switch
 * for the work; the work's holds are untouched by it.
 */
export function StartWorker({ projectId, onChanged }) {
  const { pending, notice, act } = useHoldAction({ onChanged });
  return (
    <>
      <Button
        icon="play"
        disabled={pending !== null}
        onClick={() => act("start", (client) => startWorker(client, projectId), () => "Starting a worker.")}
      >
        {pending ? "Starting…" : "Start worker"}
      </Button>
      {notice ? (
        <p className="notice notice--error hold-controls__notice" role="alert">
          {notice}
        </p>
      ) : null}
    </>
  );
}
