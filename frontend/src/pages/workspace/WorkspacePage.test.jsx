import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp, reply } from "../../testing/fakeApi";
import { workspaceRoutes } from "../../testing/workspaceFixture";

function needsYouSection() {
  return screen.getByRole("region", { name: /Needs you/ });
}

function projectsSection() {
  return screen.getByRole("region", { name: "Projects" });
}

describe("WorkspacePage", () => {
  afterEach(() => vi.useRealTimers());

  it("renders Needs you and the projects from API data", async () => {
    renderApp("/dashboard", createFakeFetch(workspaceRoutes()));

    const needsYou = await waitFor(() => {
      const section = needsYouSection();
      within(section).getByText("FOR-14");
      return section;
    });
    expect(within(needsYou).getByRole("heading", { name: /Needs you\s*2/ })).toBeInTheDocument();
    const approval = within(needsYou).getByText("FOR-14").closest("tr");
    expect(within(approval).getByText("Foreman")).toBeInTheDocument();
    expect(within(approval).getByText("Approve a merge")).toBeInTheDocument();
    expect(within(approval).getByText(/tests passed · review approved/)).toBeInTheDocument();
    expect(within(approval).getByText("b232eb1")).toBeInTheDocument();
    expect(within(approval).getByRole("link", { name: "Make the test step report what happened" })).toHaveAttribute(
      "href",
      "/dashboard/tasks/task-merge",
    );
    const unblock = within(needsYou).getByText("FOR-15").closest("tr");
    expect(within(unblock).getByText("Unblock")).toBeInTheDocument();
    expect(within(unblock).getByText("Agent exited without a completion marker")).toBeInTheDocument();
    expect(within(unblock).queryByRole("button")).toBeNull();

    const projects = projectsSection();
    const foremanRow = within(projects).getByRole("link", { name: "Foreman" }).closest("tr");
    expect(within(projects).getByRole("link", { name: "Foreman" })).toHaveAttribute("href", "/dashboard/projects/foreman");
    expect(within(foremanRow).getByText("/srv/foreman · main")).toBeInTheDocument();
    expect(within(foremanRow).getByText("Running")).toBeInTheDocument();
    expect(within(foremanRow).getByText("FOR-13")).toBeInTheDocument();
    expect(within(foremanRow).getByRole("link", { name: "Sprint 56: engine truthfulness" })).toHaveAttribute(
      "href",
      "/dashboard/sprints/sprint-56",
    );
    expect(within(foremanRow).getByText("2 blocked · 1 to do · 1 done")).toBeInTheDocument();
    expect(within(foremanRow).getByText("$1.31")).toBeInTheDocument();
    expect(within(foremanRow).getByText("2")).toBeInTheDocument();

    const otherRow = within(projects).getByRole("link", { name: "Other project" }).closest("tr");
    expect(within(otherRow).getByText("Not running")).toBeInTheDocument();
    expect(within(otherRow).getByText("working on nothing")).toBeInTheDocument();
    expect(within(otherRow).getByText("None")).toBeInTheDocument();
    expect(within(otherRow).getByText("1 planned")).toBeInTheDocument();
  });

  it("says nothing needs you when nothing does", async () => {
    renderApp("/dashboard", createFakeFetch(workspaceRoutes({ withGateTask: false })));
    expect(await screen.findByText(/^Nothing needs you\./)).toBeInTheDocument();
    expect(within(needsYouSection()).queryByRole("table")).toBeNull();
  });

  it("approves a merge through the approve endpoint and reloads", async () => {
    const routes = workspaceRoutes();
    routes["POST /api/v1/tasks/task-merge/approve"] = () => {
      // After approval the task is no longer at the gate.
      Object.assign(routes, workspaceRoutes({ withGateTask: false }));
      return { status: "approved", message: "Decision recorded. The engine continues from `merge`." };
    };
    const fetchImpl = createFakeFetch(routes);
    renderApp("/dashboard", fetchImpl);

    const button = await screen.findByRole("button", { name: "Approve FOR-14" });
    const projectListsBefore = fetchImpl.calls.filter((call) => call.url === "/api/v1/projects").length;
    fireEvent.click(button);

    expect(await screen.findByText(/^Nothing needs you\./)).toBeInTheDocument();
    expect(fetchImpl.calls.some((call) => call.method === "POST" && call.url === "/api/v1/tasks/task-merge/approve")).toBe(true);
    expect(fetchImpl.calls.filter((call) => call.url === "/api/v1/projects").length).toBe(projectListsBefore + 1);
    expect(screen.getByRole("status")).toHaveTextContent("Decision recorded. The engine continues from `merge`.");
  });

  it("shows an approval the API refused as a sentence", async () => {
    const routes = workspaceRoutes();
    routes["POST /api/v1/tasks/task-merge/approve"] = reply(409, {
      error: "Failed to approve: task is not at a human gate",
      code: "action_failed",
    });
    renderApp("/dashboard", createFakeFetch(routes));
    fireEvent.click(await screen.findByRole("button", { name: "Approve FOR-14" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to approve: task is not at a human gate.");
  });

  it("shows an API error as a sentence", async () => {
    const routes = workspaceRoutes();
    routes["GET /api/v1/projects"] = reply(401, { error: "Unauthorized: a dashboard token is required.", code: "unauthorized" });
    renderApp("/dashboard", createFakeFetch(routes));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unauthorized: a dashboard token is required.");
  });

  it("shows placeholder rows only after 200 ms of loading", async () => {
    vi.useFakeTimers();
    const routes = workspaceRoutes();
    routes["GET /api/v1/projects"] = () => new Promise(() => {});
    const { container } = renderApp("/dashboard", createFakeFetch(routes));
    expect(container.querySelectorAll(".table__placeholder")).toHaveLength(0);
    act(() => vi.advanceTimersByTime(200));
    expect(container.querySelectorAll(".table__placeholder").length).toBeGreaterThan(0);
  });

  it("caps Needs you at five with a way to see the rest", async () => {
    const routes = workspaceRoutes({ withGateTask: false });
    const tasks = Array.from({ length: 7 }, (_, index) => ({
      id: `t${index}`,
      task_key: `FOR-${100 + index}`,
      title: `Stuck ${index}`,
      status: "blocked",
      blocked_kind: "engine",
      blocked_reason: "stopped",
    }));
    routes["GET /api/v1/projects/foreman/sprints"].sprints[0].task_counts.blocked = 7;
    routes["GET /api/v1/sprints/sprint-56/tasks"] = { tasks };
    renderApp("/dashboard", createFakeFetch(routes));

    await screen.findByText("FOR-100");
    expect(screen.queryByText("FOR-105")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show all 7" }));
    expect(screen.getByText("FOR-106")).toBeInTheDocument();
  });
});
