import { useCallback, useEffect, useRef, useState } from "react";

import { useApiClient } from "./ApiProvider";
import { errorSentence } from "./client";

function keyOf(key) {
  return typeof key === "string" ? key : JSON.stringify(key);
}

// What each resource last loaded, per API client. A page that mounts with a
// key another page already loaded starts from that value and refreshes it,
// so moving between pages does not blank what is already known (a project's
// name, a sprint's title) while the same request is repeated.
const caches = new WeakMap();

function cacheOf(client) {
  let cache = caches.get(client);
  if (!cache) {
    cache = new Map();
    caches.set(client, cache);
  }
  return cache;
}

/**
 * Load one resource and keep it current.
 *
 * `key` names the resource (`["project", id]`); a new key starts a new
 * request. `load(client, { signal })` returns a promise of the data.
 *
 * Returns `{ data, error, loading, reload }`:
 * - `data` is the last value loaded for this key, kept while a reload runs,
 *   and available at once when anything loaded the same key before;
 * - `error` is a sentence from the API's error envelope, or null;
 * - a response that arrives after a newer request was started is ignored;
 * - `reload()` starts a new request for the same key.
 */
export function useResource(key, load, { enabled = true } = {}) {
  const client = useApiClient();
  const resourceKey = keyOf(key);
  const loadRef = useRef(load);
  loadRef.current = load;
  const latestRequest = useRef(0);
  const [reloads, setReloads] = useState(0);
  const cache = cacheOf(client);
  const [state, setState] = useState(() => ({
    key: resourceKey,
    data: cache.get(resourceKey) ?? null,
    error: null,
    loading: enabled,
  }));

  useEffect(() => {
    if (!enabled) {
      setState({ key: resourceKey, data: null, error: null, loading: false });
      return undefined;
    }
    const request = latestRequest.current + 1;
    latestRequest.current = request;
    const controller = new AbortController();
    setState((previous) =>
      previous.key === resourceKey
        ? { ...previous, loading: true }
        : { key: resourceKey, data: cache.get(resourceKey) ?? null, error: null, loading: true },
    );

    Promise.resolve()
      .then(() => loadRef.current(client, { signal: controller.signal }))
      .then(
        (data) => {
          if (latestRequest.current !== request) return;
          cache.set(resourceKey, data);
          setState({ key: resourceKey, data, error: null, loading: false });
        },
        (error) => {
          if (latestRequest.current !== request || error?.name === "AbortError") return;
          setState((previous) => ({
            key: resourceKey,
            data: previous.key === resourceKey ? previous.data : null,
            error: errorSentence(error),
            loading: false,
          }));
        },
      );

    return () => controller.abort();
  }, [client, cache, resourceKey, reloads, enabled]);

  const reload = useCallback(() => setReloads((count) => count + 1), []);

  const current = state.key === resourceKey;
  return {
    // Before the effect for a new key has run, the cached value stands in.
    data: current ? state.data : (cache.get(resourceKey) ?? null),
    error: current ? state.error : null,
    loading: current ? state.loading : enabled,
    reload,
  };
}

/**
 * True once `active` has stayed true for `delayMs`. Placeholder rows use it so
 * a fast load never flashes them (design README: only after 200 ms).
 */
export function useDelayedFlag(active, delayMs = 200) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!active) {
      setShown(false);
      return undefined;
    }
    const timer = setTimeout(() => setShown(true), delayMs);
    return () => clearTimeout(timer);
  }, [active, delayMs]);
  return active && shown;
}
