import { matchRoute, ROUTES } from "./routes";
import { isAppPath, isLegacyPath, paths } from "./paths";

describe("route table", () => {
  it.each([
    ["/dashboard", "workspace", {}],
    ["/dashboard/settings", "workspace-settings", {}],
    ["/dashboard/projects/p1", "project", { projectId: "p1" }],
    ["/dashboard/projects/p1/backlog", "project-backlog", { projectId: "p1" }],
    ["/dashboard/projects/p1/activity", "project-activity", { projectId: "p1" }],
    ["/dashboard/projects/p1/settings", "project-settings", { projectId: "p1" }],
    ["/dashboard/projects/p1/settings/workflow", "project-settings-workflow", { projectId: "p1" }],
    ["/dashboard/sprints/s1", "sprint", { sprintId: "s1" }],
    ["/dashboard/sprints/s1/board", "sprint-board", { sprintId: "s1" }],
    ["/dashboard/tasks/t1", "task", { taskId: "t1" }],
    ["/dashboard/tasks/t1/changes", "task-changes", { taskId: "t1" }],
    ["/dashboard/tasks/t1/checks", "task-checks", { taskId: "t1" }],
    ["/dashboard/tasks/t1/activity", "task-activity", { taskId: "t1" }],
  ])("resolves %s", (pathname, name, params) => {
    const match = matchRoute(pathname);
    expect(match.route.name).toBe(name);
    expect(match.params).toEqual(params);
  });

  it("ignores a trailing slash and decodes ids", () => {
    expect(matchRoute("/dashboard/").route.name).toBe("workspace");
    expect(matchRoute("/dashboard/projects/a%20b/").params).toEqual({ projectId: "a b" });
  });

  it("resolves unknown paths to not-found", () => {
    for (const pathname of ["/dashboard/nope", "/dashboard/projects", "/dashboard/tasks/t1/extra/more", "/elsewhere"]) {
      expect(matchRoute(pathname).route.name).toBe("not-found");
    }
  });

  it("builds every address it resolves", () => {
    expect(matchRoute(paths.projectSettingsWorkflow("x/y")).params).toEqual({ projectId: "x/y" });
    expect(matchRoute(paths.taskChecks("t")).route.name).toBe("task-checks");
    expect(matchRoute(paths.sprintBoard("s")).route.name).toBe("sprint-board");
  });

  it("gives every route a legacy address", () => {
    for (const route of ROUTES) {
      expect(isLegacyPath(route.legacyHref({ projectId: "p", sprintId: "s", taskId: "t" }))).toBe(true);
    }
  });

  it("separates the application from the legacy one", () => {
    expect(isAppPath("/dashboard/tasks/t")).toBe(true);
    expect(isAppPath("/dashboard/legacy/projects/p")).toBe(false);
    expect(isAppPath("/api/v1/projects")).toBe(false);
  });
});
