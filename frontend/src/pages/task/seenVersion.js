import { useCallback, useEffect, useState } from "react";

import { MERGE_APPROVAL, versionToken } from "../shared/gateVersion";

/**
 * One stop of a task at a gate: its step, how many times it got there and
 * what the gate decides on. A new stop is a new version to look at.
 */
export function gateStopKey(task) {
  const version = task?.gate_version;
  const step = task?.workflow_current_step;
  if (!version?.kind || !step) return null;
  const visits = task.step_visit_counts?.[step] ?? 0;
  return `${task.id}|${step}|${visits}|${version.kind}`;
}

/**
 * The version a person at a gate is looking at, kept while the page reads
 * the task again underneath them (every few seconds, and on focus).
 *
 * It is taken when the gate stop is first shown, and again from the diff
 * when the person opens the Changes tab (`sawDiff(sha)`, the head the diff
 * was read at). A reload that brings another version leaves it as it is:
 * `moved` says the gate's version is no longer the one shown, and `look()`
 * takes the new one.
 *
 * Returns `{ version, current, moved, look, sawDiff }`.
 */
export function useSeenGateVersion(task) {
  const key = gateStopKey(task);
  const current = key ? task.gate_version : null;
  const [seen, setSeen] = useState(null);

  useEffect(() => {
    // An update, not a plain set: the Changes tab may have taken the diff's
    // head in the same render (child effects run first).
    if (key && current && seen?.key !== key) {
      setSeen((previous) => (previous?.key === key ? previous : { key, version: current }));
    }
  }, [key, current, seen?.key]);

  const look = useCallback(() => {
    if (key && current) setSeen({ key, version: current });
  }, [key, current]);

  const sawDiff = useCallback(
    (sha) => {
      if (!key || !sha || current?.kind !== MERGE_APPROVAL) return;
      setSeen((previous) => {
        const base = previous?.key === key ? previous.version : current;
        return { key, version: { ...base, branch_sha: sha, token: sha } };
      });
    },
    [key, current],
  );

  const version = key ? (seen?.key === key ? seen.version : current) : null;
  const moved = Boolean(version && current && versionToken(version) !== versionToken(current));
  return { version, current, moved, look, sawDiff };
}
