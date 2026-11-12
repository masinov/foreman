import { queryString } from "./client";
import { pauseEngine, resumeEngine, startEngine, stopEngine } from "./engine";
import { listMilestones, MILESTONE_FILTERS } from "./milestones";
import { listNeedsYou } from "./needsYou";
import { confirmProposal, declineProposal, getProposal, listProposals } from "./proposals";
import { createSprint, listProjectSprints } from "./sprints";
import { getWorkspace } from "./workspace";
import { createFakeFetch, testClient } from "../testing/fakeApi";

describe("queryString", () => {
  it("repeats arrays, drops empties and encodes", () => {
    expect(queryString({ kind: ["a", "b"], q: "x y", limit: 10, offset: 0, none: null, blank: "" })).toBe(
      "?kind=a&kind=b&q=x+y&limit=10&offset=0",
    );
    expect(queryString({ kind: [] })).toBe("");
  });
});

describe("resource modules", () => {
  it("read, list, confirm and decline proposals", async () => {
    const fetchImpl = createFakeFetch({
      "GET /api/v1/proposals/prop%201": { id: "prop 1", state: "proposed" },
      "GET /api/v1/projects/p/proposals?state=proposed&state=failed&limit=5": { proposals: [], total: 0 },
      "POST /api/v1/proposals/prop-1/confirm": { id: "prop-1", state: "confirmed" },
      "POST /api/v1/proposals/prop-1/decline": { id: "prop-1", state: "declined" },
    });
    const client = testClient(fetchImpl);
    expect((await getProposal(client, "prop 1")).state).toBe("proposed");
    expect(await listProposals(client, "p", { state: ["proposed", "failed"], limit: 5 })).toEqual({ proposals: [], total: 0 });
    expect((await confirmProposal(client, "prop-1")).state).toBe("confirmed");
    expect((await declineProposal(client, "prop-1")).state).toBe("declined");
    expect(fetchImpl.calls.filter((call) => call.method === "POST").map((call) => call.body)).toEqual([{}, {}]);
  });

  it("read the workspace, needs you and milestones", async () => {
    const fetchImpl = createFakeFetch({
      "GET /api/v1/workspace": { projects: [{ id: "p" }] },
      "GET /api/v1/needs-you?limit=5&offset=0": { items: [{ task_id: "t" }], total: 9 },
      "GET /api/v1/projects/p%201/needs-you?limit=5": { items: [], total: 0 },
      "GET /api/v1/projects/p/milestones?kind=task_merged&limit=25&offset=25": { milestones: [{ kind: "task_merged" }], total: 26 },
      "GET /api/v1/milestones?limit=10": { milestones: [], total: 0 },
    });
    const client = testClient(fetchImpl);
    expect(await getWorkspace(client)).toEqual({ projects: [{ id: "p" }] });
    expect(await listNeedsYou(client, { limit: 5, offset: 0 })).toEqual({ items: [{ task_id: "t" }], total: 9 });
    expect(await listNeedsYou(client, { projectId: "p 1", limit: 5 })).toEqual({ items: [], total: 0 });
    const merges = MILESTONE_FILTERS.find((filter) => filter.key === "merges").kinds;
    expect(await listMilestones(client, { projectId: "p", kinds: merges, limit: 25, offset: 25 })).toEqual({
      items: [{ kind: "task_merged" }],
      total: 26,
    });
    expect(await listMilestones(client, { limit: 10 })).toEqual({ items: [], total: 0 });
  });

  it("page, filter and create sprints", async () => {
    const fetchImpl = createFakeFetch({
      "GET /api/v1/projects/p/sprints?status=completed&q=55&limit=10&offset=10&order=recent": { sprints: [{ id: "s" }], total: 11 },
      "POST /api/v1/projects/p/sprints": { id: "sprint-new" },
    });
    const client = testClient(fetchImpl);
    const page = await listProjectSprints(client, "p", { statuses: ["completed"], q: "55", limit: 10, offset: 10, order: "recent" });
    expect(page).toEqual({ items: [{ id: "s" }], total: 11 });
    await createSprint(client, "p", { title: "Sprint 59", goal: "" });
    expect(fetchImpl.calls.at(-1)).toEqual({ method: "POST", url: "/api/v1/projects/p/sprints", body: { title: "Sprint 59", goal: null } });
  });

  it("send engine commands to the routes that exist", async () => {
    const fetchImpl = createFakeFetch({
      "POST /api/v1/projects/p/agent/start": {},
      "POST /api/v1/projects/p/agent/stop": {},
      "POST /api/v1/projects/p/engine/commands": {},
    });
    const client = testClient(fetchImpl);
    await startEngine(client, "p");
    await resumeEngine(client, "p");
    await pauseEngine(client, "p");
    await stopEngine(client, "p");
    expect(fetchImpl.calls.map((call) => [call.url, call.body])).toEqual([
      ["/api/v1/projects/p/agent/start", {}],
      ["/api/v1/projects/p/agent/start", {}],
      ["/api/v1/projects/p/agent/stop", {}],
      ["/api/v1/projects/p/engine/commands", { command: "shutdown" }],
    ]);
  });
});
