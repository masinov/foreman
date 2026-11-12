import { loadWorkspace, NEEDS_YOU_KINDS } from "./workspace";
import { createFakeFetch, reply, testClient } from "../testing/fakeApi";
import { counts, workspaceRoutes } from "../testing/workspaceFixture";

describe("loadWorkspace", () => {
  it("builds projects and one needs-you list from the per-resource endpoints", async () => {
    const fetchImpl = createFakeFetch(workspaceRoutes());
    const workspace = await loadWorkspace(testClient(fetchImpl));

    expect(workspace.projects).toHaveLength(2);
    const [foreman, other] = workspace.projects;
    expect(foreman).toMatchObject({
      id: "foreman",
      repoPath: "/srv/foreman",
      defaultBranch: "main",
      needsYouCount: 2,
      plannedSprints: 1,
      activeSprint: { id: "sprint-56", costUsd: 1.314 },
    });
    expect(other).toMatchObject({ activeSprint: null, plannedSprints: 1, needsYouCount: 0 });

    expect(workspace.needsYou.map((item) => [item.kind, item.taskKey])).toEqual([
      [NEEDS_YOU_KINDS.approval, "FOR-14"],
      [NEEDS_YOU_KINDS.unblock, "FOR-15"],
    ]);
    expect(workspace.needsYou[0].evidence.tests_status).toBe("passed");
    expect(workspace.needsYou[1].reason).toBe("Agent exited without a completion marker");
  });

  it("reads tasks only from sprints whose counts say something waits", async () => {
    const fetchImpl = createFakeFetch(workspaceRoutes());
    await loadWorkspace(testClient(fetchImpl));
    const taskLists = fetchImpl.calls.filter((call) => /\/sprints\/[^/]+\/tasks$/.test(call.url));
    expect(taskLists.map((call) => call.url)).toEqual(["/api/v1/sprints/sprint-56/tasks"]);
    // Task detail only for a task at a human gate, for what was checked.
    const details = fetchImpl.calls.filter((call) => call.url.startsWith("/api/v1/tasks/"));
    expect(details.map((call) => call.url)).toEqual(["/api/v1/tasks/task-merge"]);
  });

  it("includes filed work and pending decision gates", async () => {
    const routes = workspaceRoutes({ withGateTask: false });
    routes["GET /api/v1/projects/other/sprints"] = {
      sprints: [{ id: "intake", title: "Intake", status: "planned", task_counts: counts({ triage: 1 }), totals: {} }],
    };
    routes["GET /api/v1/sprints/intake/tasks"] = {
      tasks: [{ id: "t-filed", task_key: "OTH-1", title: "Filed", status: "triage", source: { system: "github" } }],
    };
    routes["GET /api/v1/projects/foreman/gates?status=pending"] = {
      gates: [{ id: "g1", conflict_description: "Sprint 57 depends on 58", suggested_reason: "Run 58 first" }],
    };
    const workspace = await loadWorkspace(testClient(createFakeFetch(routes)));
    expect(workspace.needsYou.map((item) => item.kind)).toEqual([
      NEEDS_YOU_KINDS.accept,
      NEEDS_YOU_KINDS.sprintOrder,
    ]);
    expect(workspace.needsYou[0].source.system).toBe("github");
    expect(workspace.needsYou[1]).toMatchObject({ projectId: "foreman", title: "Sprint 57 depends on 58" });
  });

  it("fails with the API's sentence when a request fails", async () => {
    const routes = workspaceRoutes();
    routes["GET /api/v1/projects/other/sprints"] = reply(500, { error: "Internal error. See the dashboard log.", code: "internal_error" });
    await expect(loadWorkspace(testClient(createFakeFetch(routes)))).rejects.toThrow(
      "Internal error. See the dashboard log.",
    );
  });
});
