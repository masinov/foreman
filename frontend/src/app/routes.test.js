import { matchRoute, ROUTES } from "./routes";
import { isAppPath, paths } from "./paths";

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

  it("names the commands for a route without a page, from the manual", () => {
    const byName = Object.fromEntries(ROUTES.map((route) => [route.name, route]));
    expect(byName.task.cli({ taskId: "t1" })).toContain("foreman approve t1");
    expect(byName["sprint-board"].cli({ sprintId: "s1" })).toEqual(["foreman board"]);
    expect(byName["project-settings"].cli({ projectId: "p1" })).toEqual(["foreman config p1"]);
    for (const route of ROUTES) {
      for (const command of route.cli?.({ projectId: "p", sprintId: "s", taskId: "t" }) ?? []) {
        expect(command).toMatch(/^foreman [a-z]/);
      }
    }
  });

  it("routes every path under /dashboard itself, and nothing else", () => {
    expect(isAppPath("/dashboard/tasks/t")).toBe(true);
    expect(isAppPath("/dashboard/legacy")).toBe(true);
    expect(isAppPath("/api/v1/projects")).toBe(false);
    expect(matchRoute("/dashboard/legacy").route.name).toBe("not-found");
    expect(matchRoute("/dashboard/legacy/projects/p").route.name).toBe("not-found");
  });
});
