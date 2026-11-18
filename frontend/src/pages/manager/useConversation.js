import { useCallback, useEffect, useRef, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { clearManagerSession, getManagerHistory, sendManagerMessage } from "../../api/manager";
import { useResource } from "../../api/useResource";

const STOPPED_EARLY = "The reply stopped before it was finished.";

// While the side bar is open the conversation is read again now and then, so
// a message sent from elsewhere (another person, another window) and its
// reply appear; while such a reply is being written, often enough to see it grow.
export const POLL_IDLE_MS = 5000;
export const POLL_ANSWERING_MS = 1500;

/**
 * A stored turn as the panel shows it. `tool_uses` also carries an
 * `interrupted` marker, an `in_progress` one while the reply is still being
 * written, and, for each proposal made in the turn, its `proposal_id`.
 */
function fromStored(turn) {
  const uses = Array.isArray(turn.tool_uses) ? turn.tool_uses : [];
  return {
    key: turn.id,
    id: turn.id,
    role: turn.role === "user" ? "user" : "assistant",
    text: turn.text || "",
    tools: uses.map((use) => use?.name).filter(Boolean),
    proposals: uses.map((use) => use?.proposal_id).filter(Boolean),
    state: uses.some((use) => use?.in_progress) ? "streaming" : uses.some((use) => use?.interrupted) ? "interrupted" : "done",
    error: null,
  };
}

/**
 * One project's conversation with the manager: the history from the API, a
 * reply that grows as it is written, a failure kept with what had arrived so
 * it can be retried, and clearing the conversation.
 *
 * A turn is `{ key, role, text, tools, proposals, state, error }`, with
 * `proposals` the ids of proposals the manager made in it, and `state` one of
 * `done`, `streaming`, `failed` or `interrupted` (a stored reply that was cut
 * short).
 */
export function useConversation(projectId, context, { onSettled } = {}) {
  const client = useApiClient();
  const history = useResource(["manager-history", projectId], (api, options) => getManagerHistory(api, projectId, {}, options), {
    enabled: Boolean(projectId),
  });
  const [turns, setTurns] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [olderError, setOlderError] = useState(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const counter = useRef(0);
  const controller = useRef(null);
  const contextRef = useRef(context);
  contextRef.current = context;
  const settledRef = useRef(onSettled);
  settledRef.current = onSettled;
  // Earlier pages the person asked for, kept when the latest page is read again.
  const older = useRef({ turns: [], hasMore: false });
  const streaming = turns.some((turn) => turn.state === "streaming");
  const writingHere = turns.some((turn) => turn.local && turn.state === "streaming");
  const answeringElsewhere = turns.some((turn) => !turn.local && turn.state === "streaming");

  // The latest page of history replaces what is shown, after the earlier
  // pages the person loaded. What this side bar sent stays as it arrived
  // until a page holds it: while its reply is written, while a failed one
  // waits to be retried, and against a page read before it was sent.
  useEffect(() => {
    if (!history.data) return;
    const page = (history.data.turns || []).map(fromStored);
    const ids = new Set(page.map((turn) => turn.id));
    setTurns((current) => {
      const last = current[current.length - 1];
      const unsettled = current.some((turn) => turn.local && (turn.state === "streaming" || !turn.id || !ids.has(turn.id)));
      if (unsettled || (last?.local && last.state === "failed")) return current;
      return [...older.current.turns.filter((turn) => !ids.has(turn.id)), ...page];
    });
    setHasMore(older.current.turns.length ? older.current.hasMore : Boolean(history.data.has_more));
  }, [history.data]);

  const reloadHistory = history.reload;
  useEffect(() => {
    if (!projectId || writingHere) return undefined;
    const id = setInterval(
      () => {
        if (document.visibilityState === "visible") reloadHistory();
      },
      answeringElsewhere ? POLL_ANSWERING_MS : POLL_IDLE_MS,
    );
    return () => clearInterval(id);
  }, [projectId, writingHere, answeringElsewhere, reloadHistory]);

  useEffect(() => () => controller.current?.abort(), []);

  const loadOlder = useCallback(async () => {
    const oldest = turns.find((turn) => turn.id);
    if (!oldest || loadingOlder) return;
    setLoadingOlder(true);
    setOlderError(null);
    try {
      const page = await getManagerHistory(client, projectId, { before: oldest.id });
      const earlier = (page.turns || []).map(fromStored);
      older.current = { turns: [...earlier, ...older.current.turns], hasMore: Boolean(page.has_more) };
      setTurns((current) => [...earlier, ...current]);
      setHasMore(Boolean(page.has_more));
    } catch (error) {
      setOlderError(errorSentence(error));
    } finally {
      setLoadingOlder(false);
    }
  }, [client, projectId, turns, loadingOlder]);

  const run = useCallback(
    async (text, replacing = 0, plan = null) => {
      counter.current += 1;
      const replyKey = `reply-${counter.current}`;
      const update = (change) =>
        setTurns((current) => current.map((turn) => (turn.key === replyKey ? { ...turn, ...change(turn) } : turn)));
      const sentKey = `sent-${counter.current}`;
      const sent = { key: sentKey, local: true, role: "user", text, plan, tools: [], proposals: [], state: "done", error: null };
      const reply = { key: replyKey, local: true, role: "assistant", text: "", tools: [], proposals: [], state: "streaming", error: null };
      setTurns((current) => [...current.slice(0, current.length - replacing), sent, reply]);

      const abort = new AbortController();
      controller.current = abort;
      let finished = false;
      try {
        for await (const line of sendManagerMessage(client, projectId, text, contextRef.current, { signal: abort.signal }, plan)) {
          if (line.type === "turn") {
            setTurns((current) =>
              current.map((turn) =>
                turn.key === sentKey ? { ...turn, id: line.message_id } : turn.key === replyKey ? { ...turn, id: line.reply_id } : turn,
              ),
            );
          } else if (line.type === "text_delta" && typeof line.text === "string") {
            update((turn) => ({ text: turn.text + line.text }));
          } else if (line.type === "tool_use" && line.name) {
            update((turn) => ({ tools: [...turn.tools, line.name] }));
          } else if (line.type === "proposal" && line.proposal_id && line.settled) {
            // Decided by the project's policy while the turn ended: show it as it now is.
            update((turn) => ({ settled: (turn.settled || 0) + 1 }));
            settledRef.current?.();
          } else if (line.type === "proposal" && line.proposal_id) {
            update((turn) => (turn.proposals.includes(line.proposal_id) ? {} : { proposals: [...turn.proposals, line.proposal_id] }));
          } else if (line.type === "error") {
            finished = true;
            update(() => ({ state: "failed", error: errorSentence(new Error(line.message || "The manager could not answer")) }));
          } else if (line.type === "done") {
            finished = true;
            update(() => ({ state: "done" }));
          }
        }
        if (!finished) update(() => ({ state: "failed", error: STOPPED_EARLY }));
      } catch (error) {
        if (error?.name === "AbortError") return;
        update(() => ({ state: "failed", error: errorSentence(error) }));
      }
    },
    [client, projectId],
  );

  const send = useCallback((text) => (streaming ? Promise.resolve() : run(text)), [streaming, run]);

  /** Make a planning request: `{ says, plan }` from `app/managerRequests`. */
  const plan = useCallback(
    (request) => (streaming ? Promise.resolve() : run(request.says, 0, request.plan)),
    [streaming, run],
  );

  /** Send the last message again, in place of the failed attempt. */
  const retry = useCallback(() => {
    const last = turns[turns.length - 1];
    const before = turns[turns.length - 2];
    if (streaming || last?.state !== "failed" || before?.role !== "user") return Promise.resolve();
    return run(before.text, 2, before.plan ?? null);
  }, [turns, streaming, run]);

  const clear = useCallback(async () => {
    const cleared = await clearManagerSession(client, projectId);
    controller.current?.abort();
    older.current = { turns: [], hasMore: false };
    setTurns([]);
    setHasMore(false);
    // Its waiting proposals were declined with it: what the page shows changed.
    if (cleared?.declined_proposals?.length) settledRef.current?.();
  }, [client, projectId]);

  return {
    plan,
    turns,
    streaming,
    hasMore,
    loadOlder,
    loadingOlder,
    olderError,
    loading: history.loading && turns.length === 0,
    loadError: history.data ? null : history.error,
    reloadHistory: history.reload,
    // Proposals still waiting for an answer; clearing the conversation declines them.
    waitingProposals: history.data?.waiting_proposals || 0,
    failed: turns[turns.length - 1]?.state === "failed",
    send,
    retry,
    clear,
  };
}
