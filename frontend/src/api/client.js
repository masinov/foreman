import { readDashboardToken } from "./token";

// Every request goes to the versioned API (ADR-0019).
export const API_BASE = "/api/v1";

const UNREADABLE_RESPONSE = "Foreman answered with something the dashboard could not read.";
const UNREACHABLE = "The dashboard could not reach Foreman. Check that the server is running.";

/**
 * An error from the API, carrying the one envelope ADR-0019 defines:
 * `{"error": "<a sentence>", "code": "<kind>"}`. `message` is always a
 * sentence a person can read.
 */
export class ApiError extends Error {
  constructor(message, { code = "http_error", status = 0, field = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    // The field of the request the error is about, when the API says.
    this.field = field;
  }
}

function asSentence(text) {
  const trimmed = String(text).trim();
  if (!trimmed) return trimmed;
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}

/** Turn anything thrown while loading into a sentence for the page. */
export function errorSentence(error) {
  if (error instanceof ApiError) return error.message;
  if (error && typeof error.message === "string" && error.message) {
    return asSentence(error.message);
  }
  return "Something went wrong.";
}

async function readEnvelope(response) {
  const text = await response.text();
  if (!text) return { ok: true, payload: null };
  try {
    return { ok: true, payload: JSON.parse(text) };
  } catch {
    return { ok: false, payload: null };
  }
}

function errorFromResponse(response, payload) {
  if (payload && typeof payload === "object" && typeof payload.error === "string") {
    return new ApiError(asSentence(payload.error), {
      code: typeof payload.code === "string" ? payload.code : "http_error",
      status: response.status,
      field: typeof payload.field === "string" ? payload.field : null,
    });
  }
  return new ApiError(`Foreman answered ${response.status} without saying why.`, {
    code: "http_error",
    status: response.status,
  });
}

/**
 * The one way the rebuilt frontend talks to the server. Pages never call
 * `fetch`; they call a resource module, which calls this.
 */
export function createApiClient({
  fetchImpl = globalThis.fetch,
  eventSourceImpl = globalThis.EventSource,
  tokenProvider = readDashboardToken,
  base = API_BASE,
} = {}) {
  if (typeof fetchImpl !== "function") {
    throw new Error("A fetch implementation is required.");
  }

  // Who wants to know that the server refused this browser's token (or the
  // lack of one). The application shows its sign-in page when that happens.
  const unauthorizedListeners = new Set();
  function onUnauthorized(listener) {
    unauthorizedListeners.add(listener);
    return () => unauthorizedListeners.delete(listener);
  }
  function refused(response) {
    if (response.status === 401) unauthorizedListeners.forEach((listener) => listener());
  }

  /**
   * `token` in the options presents that token instead of the stored one
   * (trying a token before keeping it); a refusal of it is the caller's to
   * handle and is not announced.
   */
  async function request(method, path, { body, signal, token: presented } = {}) {
    const token = presented ?? tokenProvider();
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;

    let response;
    try {
      response = await fetchImpl(`${base}${path}`, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal,
      });
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      throw new ApiError(UNREACHABLE, { code: "network_error", status: 0 });
    }

    const { ok, payload } = await readEnvelope(response);
    if (!response.ok) {
      if (presented === undefined) refused(response);
      throw errorFromResponse(response, payload);
    }
    if (!ok) throw new ApiError(UNREADABLE_RESPONSE, { code: "invalid_response", status: response.status });
    return payload;
  }

  /**
   * POST and read the answer as it is written: newline-delimited JSON, one
   * object per line. An async generator of the parsed lines; a line that is
   * not JSON is skipped. A refusal before the stream starts throws the API's
   * error; a stream that breaks part-way throws a sentence.
   */
  async function* postLines(path, body, { signal } = {}) {
    const token = tokenProvider();
    const headers = { Accept: "application/x-ndjson", "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;

    let response;
    try {
      response = await fetchImpl(`${base}${path}`, { method: "POST", headers, body: JSON.stringify(body), signal });
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      throw new ApiError(UNREACHABLE, { code: "network_error", status: 0 });
    }
    if (!response.ok) {
      refused(response);
      const { payload } = await readEnvelope(response);
      throw errorFromResponse(response, payload);
    }
    if (!response.body?.getReader) {
      throw new ApiError(UNREADABLE_RESPONSE, { code: "invalid_response", status: response.status });
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const parse = (line) => {
      if (!line.trim()) return [];
      try {
        return [JSON.parse(line)];
      } catch {
        return [];
      }
    };
    try {
      while (true) {
        let chunk;
        try {
          chunk = await reader.read();
        } catch (error) {
          if (error?.name === "AbortError") throw error;
          throw new ApiError(UNREACHABLE, { code: "network_error", status: 0 });
        }
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) yield* parse(line);
      }
      yield* parse(buffer + decoder.decode());
    } finally {
      reader.cancel().catch(() => {});
    }
  }

  /**
   * Follow a server-sent event stream. `onMessage` gets each message's data,
   * parsed. An EventSource cannot send headers, so the token goes in the
   * query, which the API accepts for this. Returns a function that closes the
   * stream. Where the browser has no EventSource nothing is opened.
   */
  function stream(path, { onMessage }) {
    if (typeof eventSourceImpl !== "function") return () => {};
    const token = tokenProvider();
    const separator = path.includes("?") ? "&" : "?";
    const url = `${base}${path}${token ? `${separator}token=${encodeURIComponent(token)}` : ""}`;
    const source = new eventSourceImpl(url);
    source.onmessage = (message) => {
      let data;
      try {
        data = JSON.parse(message.data);
      } catch {
        return;
      }
      onMessage(data);
    };
    return () => source.close();
  }

  return {
    stream,
    postLines,
    onUnauthorized,
    get: (path, options) => request("GET", path, options),
    post: (path, body, options) => request("POST", path, { ...options, body }),
    patch: (path, body, options) => request("PATCH", path, { ...options, body }),
    delete: (path, options) => request("DELETE", path, options),
  };
}

/** Encode one path segment. */
export function segment(value) {
  return encodeURIComponent(String(value));
}

/**
 * Build `?a=1&kind=x&kind=y` from an object. Arrays repeat their key; null,
 * undefined and empty strings are left out. Returns "" when nothing is left.
 */
export function queryString(params = {}) {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    const values = Array.isArray(value) ? value : [value];
    for (const item of values) {
      if (item === null || item === undefined || item === "") continue;
      search.append(name, String(item));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
