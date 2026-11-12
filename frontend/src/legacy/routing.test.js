import { buildProjectPath, buildSprintPath, isLegacyPath, parseRoute } from "./routing";

describe("legacy routing", () => {
  it("lives under /dashboard/legacy", () => {
    expect(isLegacyPath("/dashboard/legacy")).toBe(true);
    expect(isLegacyPath("/dashboard/legacy/")).toBe(true);
    expect(isLegacyPath("/dashboard/legacy/projects/p")).toBe(true);
    expect(isLegacyPath("/dashboard")).toBe(false);
    expect(isLegacyPath("/dashboard/legacyish")).toBe(false);
  });

  it("parses its project and sprint paths below the base", () => {
    expect(parseRoute("/dashboard/legacy")).toEqual({ view: "dashboard", projectId: null, sprintId: null });
    expect(parseRoute("/dashboard/legacy/projects/a%20b")).toEqual({
      view: "project",
      projectId: "a b",
      sprintId: null,
    });
    expect(parseRoute("/dashboard/legacy/projects/p/sprints/s/")).toEqual({
      view: "sprint",
      projectId: "p",
      sprintId: "s",
    });
  });

  it("builds paths below the base", () => {
    expect(buildProjectPath("p 1")).toBe("/dashboard/legacy/projects/p%201");
    expect(buildSprintPath("p", "s")).toBe("/dashboard/legacy/projects/p/sprints/s");
  });
});
