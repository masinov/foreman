import React from "react";
import { render } from "@testing-library/react";

import { ApiProvider } from "../api/ApiProvider";
import { createApiClient } from "../api/client";
import { App } from "../app/App";
import { RouterProvider } from "../app/router";

function jsonResponse(status, body) {
  return new Response(body === undefined ? "" : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * A fetch that answers from a table of `"METHOD /api/v1/path": handler`.
 * A handler is a body (200), `{ status, body }` via `reply()`, or a function
 * returning either (or a promise of either). Unknown routes answer the API's
 * not_found envelope. Every call is recorded in `fetch.calls`.
 */
export function createFakeFetch(routes = {}) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    const method = (init.method || "GET").toUpperCase();
    const key = `${method} ${url}`;
    calls.push({ method, url, body: init.body ? JSON.parse(init.body) : undefined });
    if (!(key in routes)) {
      return jsonResponse(404, { error: `Not found: ${url}`, code: "not_found" });
    }
    let answer = routes[key];
    if (typeof answer === "function") answer = await answer({ method, url, init });
    if (answer && answer.__reply) return jsonResponse(answer.status, answer.body);
    return jsonResponse(200, answer);
  };
  fetchImpl.calls = calls;
  fetchImpl.routes = routes;
  fetchImpl.EventSource = createFakeEventSource();
  return fetchImpl;
}

/**
 * An EventSource class that records every stream opened (`.sources`). A test
 * sends a message with `source.emit(data)`.
 */
export function createFakeEventSource() {
  const sources = [];
  class FakeEventSource {
    constructor(url) {
      this.url = url;
      this.closed = false;
      this.onmessage = null;
      sources.push(this);
    }

    close() {
      this.closed = true;
    }

    emit(data) {
      this.onmessage?.({ data: JSON.stringify(data) });
    }
  }
  FakeEventSource.sources = sources;
  return FakeEventSource;
}

export function reply(status, body) {
  return { __reply: true, status, body };
}

export function testClient(fetchImpl) {
  return createApiClient({ fetchImpl, eventSourceImpl: fetchImpl?.EventSource, tokenProvider: () => "" });
}

export function renderWithApi(ui, fetchImpl) {
  return render(<ApiProvider client={testClient(fetchImpl)}>{ui}</ApiProvider>);
}

/** Render the whole application at `pathname`. */
export function renderApp(pathname, fetchImpl = createFakeFetch()) {
  window.history.replaceState({}, "", pathname);
  const utils = renderWithApi(
    <RouterProvider browser={window}>
      <App />
    </RouterProvider>,
    fetchImpl,
  );
  return { ...utils, fetchImpl };
}
