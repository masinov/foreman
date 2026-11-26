import { queryString } from "./client";
import { runTaskNext, startWorker } from "./engine";
import {
  blockAll,
  blockSprint,
  pauseAll,
  pauseSprint,
  pauseTask,
  resumeAll,
  resumeSprint,
  resumeTask,
  stopAll,
  stopSprint,
  stopTask,
  unblockAll,
  unblockSprint,
} from "./holds";
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
      "GET /api/v1/projects/p/milestones?kind=engine_started&kind=engine_stopped&kind=engine_paused&kind=engine_resumed&kind=engine_lost&limit=25&offset=25": {
        milestones: [{ kind: "engine_stopped" }],
        total: 26,
      },
      "GET /api/v1/milestones?limit=10": { milestones: [], total: 0 },
    });
    const client = testClient(fetchImpl);
    expect(await getWorkspace(client)).toEqual({ projects: [{ id: "p" }], block: null });
    expect(await listNeedsYou(client, { limit: 5, offset: 0 })).toEqual({ items: [{ task_id: "t" }], total: 9 });
    expect(await listNeedsYou(client, { projectId: "p 1", limit: 5 })).toEqual({ items: [], total: 0 });
    const engine = MILESTONE_FILTERS.find((filter) => filter.key === "worker").kinds;
    expect(await listMilestones(client, { projectId: "p", kinds: engine, limit: 25, offset: 25 })).toEqual({
      items: [{ kind: "engine_stopped" }],
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

  it("start a worker and run a task next on the worker's routes", async () => {
    const fetchImpl = createFakeFetch({ "POST /api/v1/projects/p/agent/start": {} });
    const client = testClient(fetchImpl);
    await startWorker(client, "p");
    await runTaskNext(client, "p", "t");
    expect(fetchImpl.calls.map((call) => [call.url, call.body])).toEqual([
      ["/api/v1/projects/p/agent/start", {}],
      ["/api/v1/projects/p/agent/start", { task_id: "t" }],
    ]);
  });

  it("send holds to the routes that exist (ADR-0043)", async () => {
    const routes = [
      "POST /api/v1/tasks/t/pause",
      "POST /api/v1/tasks/t/stop",
      "POST /api/v1/tasks/t/resume",
      "POST /api/v1/sprints/s/pause",
      "POST /api/v1/sprints/s/stop",
      "POST /api/v1/sprints/s/resume",
      "POST /api/v1/sprints/s/block",
      "POST /api/v1/sprints/s/unblock",
      "POST /api/v1/workspace/pause",
      "POST /api/v1/workspace/stop",
      "POST /api/v1/workspace/resume",
      "POST /api/v1/workspace/block",
      "POST /api/v1/workspace/unblock",
    ];
    const fetchImpl = createFakeFetch(Object.fromEntries(routes.map((route) => [route, {}])));
    const client = testClient(fetchImpl);
    await pauseTask(client, "t");
    await stopTask(client, "t");
    await resumeTask(client, "t");
    await pauseSprint(client, "s");
    await stopSprint(client, "s");
    await resumeSprint(client, "s");
    await blockSprint(client, "s", "design review");
    await unblockSprint(client, "s");
    await pauseAll(client);
    await stopAll(client);
    await resumeAll(client);
    await blockAll(client, "freeze");
    await unblockAll(client);
    expect(fetchImpl.calls.map((call) => `${call.method} ${call.url}`)).toEqual(routes);
    expect(fetchImpl.calls[6].body).toEqual({ reason: "design review" });
    expect(fetchImpl.calls[11].body).toEqual({ reason: "freeze" });
  });
});
