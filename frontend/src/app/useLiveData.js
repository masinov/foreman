import { useEffect, useRef } from "react";

import { useDataRefresh } from "../api/ApiProvider";
import { segment } from "../api/client";
import { useEventStream } from "../api/useEventStream";

// What an agent or a test run prints while it works. These arrive many times
// a second and change nothing a list or a count shows; the task page follows
// them itself for the task it is on.
const CHATTER = new Set([
  "agent.raw_output",
  "agent.message",
  "agent.command",
  "agent.tool_use",
  "agent.tool_result",
  "agent.file_change",
  "agent.rate_limit",
  "engine.test_output",
  "engine.context_write",
]);

// A new listener is first sent the project's most recent events, which the
// page has just read. Events in this first moment are that replay.
export const REPLAY_MS = 1500;
// Wait for a burst of events to end, and never reload more often than this.
export const SETTLE_MS = 400;
export const MIN_INTERVAL_MS = 2000;
// The workspace spans projects and follows no single stream; it reads again
// this often while it is the page being looked at.
export const WORKSPACE_POLL_MS = 20000;

/**
 * Keep what the page shows current without a reload.
 *
 * Inside a project (its page, a sprint, a task, settings, the backlog) the
 * project's event stream says when something changed, and everything the
 * page loaded is read again: once per burst, at most every two seconds. On
 * the workspace the page reads again on a slow timer. Either way, coming
 * back to a tab that was in the background reads again at once.
 */
export function useLiveData({ projectId, poll = false }) {
  const { refresh } = useDataRefresh();
  const openedAt = useRef(0);
  const lastRefresh = useRef(0);
  const timer = useRef(null);

  useEffect(() => {
    openedAt.current = Date.now();
    return () => clearTimeout(timer.current);
  }, [projectId]);

  useEventStream(projectId ? `/projects/${segment(projectId)}/stream` : null, (event) => {
    if (CHATTER.has(event.event_type)) return;
    const now = Date.now();
    if (now - openedAt.current < REPLAY_MS) return;
    clearTimeout(timer.current);
    const wait = Math.max(SETTLE_MS, lastRefresh.current + MIN_INTERVAL_MS - now);
    timer.current = setTimeout(() => {
      lastRefresh.current = Date.now();
      refresh();
    }, wait);
  });

  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === "visible") refresh();
    }
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [refresh]);

  useEffect(() => {
    if (!poll) return undefined;
    const id = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, WORKSPACE_POLL_MS);
    return () => clearInterval(id);
  }, [poll, refresh]);
}
