import React, { createContext, useCallback, useContext, useMemo, useState } from "react";

const ApiClientContext = createContext(null);
const RefreshContext = createContext({ generation: 0, refresh: () => {} });

/**
 * The API client every page talks through, and a way to say "what the
 * server holds has changed": `refresh()` makes every loaded resource load
 * again (it keeps showing what it had until the new answer arrives).
 */
export function ApiProvider({ client, children }) {
  const [generation, setGeneration] = useState(0);
  const refresh = useCallback(() => setGeneration((value) => value + 1), []);
  const value = useMemo(() => ({ generation, refresh }), [generation, refresh]);
  return (
    <ApiClientContext.Provider value={client}>
      <RefreshContext.Provider value={value}>{children}</RefreshContext.Provider>
    </ApiClientContext.Provider>
  );
}

export function useApiClient() {
  const client = useContext(ApiClientContext);
  if (!client) {
    throw new Error("useApiClient needs an <ApiProvider> above it.");
  }
  return client;
}

/** `{ generation, refresh }`: the count of refreshes so far, and how to ask for one. */
export function useDataRefresh() {
  return useContext(RefreshContext);
}
