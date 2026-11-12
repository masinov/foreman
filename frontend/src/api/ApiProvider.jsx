import React, { createContext, useContext } from "react";

const ApiClientContext = createContext(null);

export function ApiProvider({ client, children }) {
  return <ApiClientContext.Provider value={client}>{children}</ApiClientContext.Provider>;
}

export function useApiClient() {
  const client = useContext(ApiClientContext);
  if (!client) {
    throw new Error("useApiClient needs an <ApiProvider> above it.");
  }
  return client;
}
