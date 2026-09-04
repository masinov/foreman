import { describe, expect, it, vi } from "vitest";

import {
  UnauthorizedError,
  buildStreamPath,
  createDashboardServices,
  getDashboardToken,
  setDashboardToken,
} from "./api";

function jsonResponse(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(payload),
  };
}

describe("dashboard access token", () => {
  it("sends the stored token as a bearer header", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(200, { projects: [] }));
    const services = createDashboardServices({ fetchImpl, tokenProvider: () => "s3cret" });

    await services.listProjects();

    const [, options] = fetchImpl.mock.calls[0];
    expect(options.headers.Authorization).toBe("Bearer s3cret");
  });

  it("omits the header when no token is stored", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(200, { projects: [] }));
    const services = createDashboardServices({ fetchImpl, tokenProvider: () => "" });

    await services.listProjects();

    const [, options] = fetchImpl.mock.calls[0];
    expect(options.headers.Authorization).toBeUndefined();
  });

  it("raises UnauthorizedError with status 401 so the app can prompt", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(401, { error: "Unauthorized: a dashboard token is required." }));
    const services = createDashboardServices({ fetchImpl, tokenProvider: () => "" });

    await expect(services.listProjects()).rejects.toMatchObject({
      name: "UnauthorizedError",
      status: 401,
    });
    expect(new UnauthorizedError("x").status).toBe(401);
  });

  it("puts the token on the event stream URL because EventSource cannot set headers", () => {
    expect(buildStreamPath("s1", "evt-9", "tok")).toBe("/api/sprints/s1/stream?after=evt-9&token=tok");
    expect(buildStreamPath("s1", undefined, "")).toBe("/api/sprints/s1/stream");
  });

  it("stores and clears the token in the provided storage", () => {
    const backing = new Map();
    const storage = {
      getItem: (key) => backing.get(key) ?? null,
      setItem: (key, value) => backing.set(key, value),
      removeItem: (key) => backing.delete(key),
    };
    setDashboardToken("abc", storage);
    expect(getDashboardToken(storage)).toBe("abc");
    setDashboardToken("", storage);
    expect(getDashboardToken(storage)).toBe("");
  });
});

describe("engine control calls", () => {
  it("reads the engine status from the agent status route", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(200, { resident: true }));
    const services = createDashboardServices({ fetchImpl, tokenProvider: () => "" });

    await services.agentStatus("proj-1");

    expect(fetchImpl.mock.calls[0][0]).toBe("/api/projects/proj-1/agent/status");
  });

  it("posts a pause request and forwards the requester", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(200, { command: { id: "cmd-1" } }));
    const services = createDashboardServices({ fetchImpl, tokenProvider: () => "" });

    await services.stopAgent("proj-1", { requestedBy: "ana" });

    const [path, options] = fetchImpl.mock.calls[0];
    expect(path).toBe("/api/projects/proj-1/agent/stop");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ requested_by: "ana" });
  });

  it("lists recent engine commands", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(200, { commands: [] }));
    const services = createDashboardServices({ fetchImpl, tokenProvider: () => "" });

    await services.listEngineCommands("proj-1", { limit: 5 });

    expect(fetchImpl.mock.calls[0][0]).toBe("/api/projects/proj-1/engine/commands?limit=5");
  });
});
