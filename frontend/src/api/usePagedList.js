import { useCallback, useEffect, useRef, useState } from "react";

import { useApiClient } from "./ApiProvider";
import { errorSentence } from "./client";

function keyOf(key) {
  return typeof key === "string" ? key : JSON.stringify(key);
}

const EMPTY = { items: null, total: null, meta: null, error: null, loading: false, loadingMore: false };

/**
 * A list that pages on the server.
 *
 * `loadPage(client, { limit, offset, signal })` returns `{ items, total, meta }`; `meta` is whatever else the page says
 * (counts, a policy) and is passed through.
 * The first page (`pageSize` items) loads for each `key`; `loadMore(limit)`
 * appends the next `limit` (default `pageSize`) after what is loaded.
 *
 * Returns `{ items, total, meta, error, loading, loadingMore, hasMore, loadMore, reload }`.
 * A new key or `reload()` starts again from the first page; a response for
 * an older key or an earlier reload is ignored. `error` is a sentence.
 */
export function usePagedList(key, loadPage, { pageSize, enabled = true }) {
  const client = useApiClient();
  const listKey = keyOf(key);
  const loadRef = useRef(loadPage);
  loadRef.current = loadPage;
  const generation = useRef(0);
  const more = useRef(null);
  const [reloads, setReloads] = useState(0);
  const [state, setState] = useState({ key: listKey, ...EMPTY, loading: enabled });

  useEffect(() => {
    generation.current += 1;
    const current = generation.current;
    more.current?.abort();
    if (!enabled) {
      setState({ key: listKey, ...EMPTY });
      return undefined;
    }
    const controller = new AbortController();
    setState((previous) =>
      previous.key === listKey
        ? { ...previous, error: null, loading: true, loadingMore: false }
        : { key: listKey, ...EMPTY, loading: true },
    );
    Promise.resolve()
      .then(() => loadRef.current(client, { limit: pageSize, offset: 0, signal: controller.signal }))
      .then(
        (page) => {
          if (generation.current !== current) return;
          setState({ key: listKey, ...EMPTY, items: page.items, total: page.total, meta: page.meta ?? null });
        },
        (error) => {
          if (generation.current !== current || error?.name === "AbortError") return;
          setState((previous) => ({
            ...(previous.key === listKey ? previous : { key: listKey, ...EMPTY }),
            error: errorSentence(error),
            loading: false,
          }));
        },
      );
    return () => controller.abort();
  }, [client, listKey, reloads, enabled, pageSize]);

  const loadMore = useCallback(
    (limit = pageSize) => {
      const current = generation.current;
      const offset = state.items ? state.items.length : 0;
      const controller = new AbortController();
      more.current = controller;
      setState((previous) => ({ ...previous, error: null, loadingMore: true }));
      Promise.resolve()
        .then(() => loadRef.current(client, { limit, offset, signal: controller.signal }))
        .then(
          (page) => {
            if (generation.current !== current) return;
            setState((previous) => ({
              ...previous,
              items: [...(previous.items ?? []), ...page.items],
              total: page.total,
              meta: page.meta ?? previous.meta,
              loadingMore: false,
            }));
          },
          (error) => {
            if (generation.current !== current || error?.name === "AbortError") return;
            setState((previous) => ({ ...previous, error: errorSentence(error), loadingMore: false }));
          },
        );
    },
    [client, pageSize, state.items],
  );

  useEffect(() => () => more.current?.abort(), []);

  const reload = useCallback(() => setReloads((count) => count + 1), []);

  const current = state.key === listKey ? state : { ...EMPTY, loading: enabled };
  return {
    items: current.items,
    total: current.total,
    meta: current.meta,
    error: current.error,
    loading: current.loading,
    loadingMore: current.loadingMore,
    hasMore: current.items !== null && current.total !== null && current.items.length < current.total,
    loadMore,
    reload,
  };
}
