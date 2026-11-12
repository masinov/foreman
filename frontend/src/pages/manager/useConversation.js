import { useCallback, useEffect, useRef, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { clearManagerSession, getManagerHistory, sendManagerMessage } from "../../api/manager";
import { useResource } from "../../api/useResource";

const STOPPED_EARLY = "The reply stopped before it was finished.";

/**
 * A stored turn as the panel shows it. `tool_uses` also carries an
 * `interrupted` marker and, for each proposal made in the turn, its
 * `proposal_id`.
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
    state: uses.some((use) => use?.interrupted) ? "interrupted" : "done",
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
export function useConversation(projectId, context) {
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
  const streaming = turns.some((turn) => turn.state === "streaming");

  // The first page of history replaces whatever was shown for another project.
  useEffect(() => {
    if (!history.data) return;
    setTurns((current) => (current.length === 0 || current.every((turn) => turn.id) ? (history.data.turns || []).map(fromStored) : current));
    setHasMore(Boolean(history.data.has_more));
  }, [history.data]);

  useEffect(() => () => controller.current?.abort(), []);

  const loadOlder = useCallback(async () => {
    const oldest = turns.find((turn) => turn.id);
    if (!oldest || loadingOlder) return;
    setLoadingOlder(true);
    setOlderError(null);
    try {
      const page = await getManagerHistory(client, projectId, { before: oldest.id });
      setTurns((current) => [...(page.turns || []).map(fromStored), ...current]);
      setHasMore(Boolean(page.has_more));
    } catch (error) {
      setOlderError(errorSentence(error));
    } finally {
      setLoadingOlder(false);
    }
  }, [client, projectId, turns, loadingOlder]);

  const run = useCallback(
    async (text, replacing = 0) => {
      counter.current += 1;
      const replyKey = `reply-${counter.current}`;
      const update = (change) =>
        setTurns((current) => current.map((turn) => (turn.key === replyKey ? { ...turn, ...change(turn) } : turn)));
      const sent = { key: `sent-${counter.current}`, role: "user", text, tools: [], proposals: [], state: "done", error: null };
      const reply = { key: replyKey, role: "assistant", text: "", tools: [], proposals: [], state: "streaming", error: null };
      setTurns((current) => [...current.slice(0, current.length - replacing), sent, reply]);

      const abort = new AbortController();
      controller.current = abort;
      let finished = false;
      try {
        for await (const line of sendManagerMessage(client, projectId, text, contextRef.current, { signal: abort.signal })) {
          if (line.type === "text_delta" && typeof line.text === "string") {
            update((turn) => ({ text: turn.text + line.text }));
          } else if (line.type === "tool_use" && line.name) {
            update((turn) => ({ tools: [...turn.tools, line.name] }));
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

  /** Send the last message again, in place of the failed attempt. */
  const retry = useCallback(() => {
    const last = turns[turns.length - 1];
    const before = turns[turns.length - 2];
    if (streaming || last?.state !== "failed" || before?.role !== "user") return Promise.resolve();
    return run(before.text, 2);
  }, [turns, streaming, run]);

  const clear = useCallback(async () => {
    await clearManagerSession(client, projectId);
    controller.current?.abort();
    setTurns([]);
    setHasMore(false);
  }, [client, projectId]);

  return {
    turns,
    streaming,
    hasMore,
    loadOlder,
    loadingOlder,
    olderError,
    loading: history.loading && turns.length === 0,
    loadError: history.data ? null : history.error,
    reloadHistory: history.reload,
    failed: turns[turns.length - 1]?.state === "failed",
    send,
    retry,
    clear,
  };
}
