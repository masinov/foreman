import { useEffect, useRef, useState } from "react";

import { onProjectEvent } from "../../app/projectEvents";

// An agent prints many times a second; what it printed is read again this often at most.
export const PULSE_MS = 1000;

/**
 * A count that grows while events about this task arrive on the project's
 * stream, at most once every `PULSE_MS`. What a running step has printed is
 * read again on each change, so its output is followed as it is written.
 * It stays still while `active` is false.
 */
export function useTaskPulse(taskId, active = true) {
  const [pulse, setPulse] = useState(0);
  const timer = useRef(null);
  useEffect(() => {
    if (!active || !taskId) return undefined;
    const stop = onProjectEvent((event) => {
      if (event.task_id !== taskId || timer.current) return;
      timer.current = setTimeout(() => {
        timer.current = null;
        setPulse((count) => count + 1);
      }, PULSE_MS);
    });
    return () => {
      stop();
      clearTimeout(timer.current);
      timer.current = null;
    };
  }, [taskId, active]);
  return pulse;
}
