import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp, reply } from "../../testing/fakeApi";
import { UNBLOCK_ITEM, workspaceRoutes } from "../../testing/workspaceFixture";

function needsYouSection() {
  return screen.getByRole("region", { name: /Needs you/ });
}

function projectsSection() {
  return screen.getByRole("region", { name: "Projects" });
}

describe("WorkspacePage", () => {
  afterEach(() => vi.useRealTimers());

  it("reads the workspace, needs you and milestones from their endpoints", async () => {
    const { fetchImpl } = renderApp("/dashboard", createFakeFetch(workspaceRoutes()));
    await screen.findByText("FOR-14");
    await screen.findByRole("table", { name: "Recent milestones" });
    expect(fetchImpl.calls.map((call) => call.url).sort()).toEqual([
      "/api/v1/milestones?limit=10",
      "/api/v1/needs-you?limit=5&offset=0",
      "/api/v1/session",
      "/api/v1/workspace",
    ]);
  });

  it("renders Needs you, the projects and recent milestones", async () => {
    renderApp("/dashboard", createFakeFetch(workspaceRoutes()));

    const needsYou = await waitFor(() => {
      const section = needsYouSection();
      within(section).getByText("FOR-14");
      return section;
    });
    expect(within(needsYou).getByRole("heading", { name: /Needs you\s*2/ })).toBeInTheDocument();
    const approval = within(needsYou).getByText("FOR-14").closest("tr");
    expect(within(approval).getByText("Foreman")).toBeInTheDocument();
    expect(within(approval).getByText("Approve merge")).toBeInTheDocument();
    // The same words as the sprint list: a word alone, in green, passed.
    expect(approval).toHaveTextContent("tests · review · b232eb1");
    expect(within(approval).getByText("tests")).toHaveClass("checks__passed");
    expect(within(approval).getByText("b232eb1")).toBeInTheDocument();
    expect(within(approval).getByRole("link", { name: "Make the test step report what happened" })).toHaveAttribute(
      "href",
      "/dashboard/tasks/task-merge",
    );
    const unblock = within(needsYou).getByText("FOR-15").closest("tr");
    expect(within(unblock).getByText("Unblock")).toBeInTheDocument();
    expect(within(unblock).getByText("Sprint 56: engine truthfulness")).toBeInTheDocument();
    expect(within(unblock).queryByRole("button")).toBeNull();

    const projects = await waitFor(() => {
      const section = projectsSection();
      within(section).getByRole("link", { name: "Foreman" });
      return section;
    });
    const foremanRow = within(projects).getByRole("link", { name: "Foreman" }).closest("tr");
    expect(within(projects).getByRole("link", { name: "Foreman" })).toHaveAttribute("href", "/dashboard/projects/foreman");
    expect(within(foremanRow).getByText("/srv/foreman · main")).toBeInTheDocument();
    expect(within(foremanRow).getByText("Running")).toBeInTheDocument();
    expect(within(foremanRow).getByText("FOR-13")).toBeInTheDocument();
    expect(within(foremanRow).getByRole("link", { name: "Sprint 56: engine truthfulness" })).toHaveAttribute(
      "href",
      "/dashboard/sprints/sprint-56",
    );
    expect(foremanRow).toHaveTextContent("2 need you · 1 to do · 1 done");
    expect(within(foremanRow).getByText("2 need you")).toHaveClass("attention");
    expect(within(foremanRow).getByText("$1.31")).toBeInTheDocument();
    expect(within(foremanRow).getByText("2")).toHaveClass("attention");
    expect(within(foremanRow).getByRole("link", { name: "Foreman backlog, 4" })).toHaveAttribute(
      "href",
      "/dashboard/projects/foreman/backlog",
    );
    expect(within(foremanRow).getByRole("link", { name: "Sprint 56 started" })).toHaveAttribute(
      "href",
      "/dashboard/sprints/sprint-56",
    );
    expect(within(foremanRow).getByText("11 Nov")).toBeInTheDocument();

    const otherRow = within(projects).getByRole("link", { name: "Other project" }).closest("tr");
    expect(within(otherRow).getByText("Not running")).toBeInTheDocument();
    // An idle engine says so once; there is no second line repeating it.
    expect(within(otherRow).queryByText(/working on/)).toBeNull();
    expect(within(otherRow).getByText("None")).toBeInTheDocument();
    expect(within(otherRow).getByText("nothing yet")).toBeInTheDocument();

    const recent = await screen.findByRole("table", { name: "Recent milestones" });
    const rows = within(recent).getAllByRole("row").slice(1);
    expect(rows.map((row) => row.textContent)).toEqual([
      "11 NovForemanSprintSprint 56 started: engine truthfulness",
      "10 NovForemanSprintSprint 55 finished: baseline and host safety",
      "9 NovOther projectEngineEngine paused by ana",
    ]);
  });

  it("says nothing needs you when nothing does", async () => {
    renderApp("/dashboard", createFakeFetch(workspaceRoutes({ withGateTask: false })));
    expect(await screen.findByText(/^Nothing needs you\./)).toBeInTheDocument();
    expect(within(needsYouSection()).queryByRole("table")).toBeNull();
  });

  it("says when nothing has happened yet", async () => {
    const routes = workspaceRoutes();
    routes["GET /api/v1/milestones?limit=10"] = { milestones: [], total: 0 };
    renderApp("/dashboard", createFakeFetch(routes));
    expect(await screen.findByText(/^Nothing has happened yet\./)).toBeInTheDocument();
  });

  it("approves a merge through the approve endpoint and reloads", async () => {
    const routes = workspaceRoutes();
    routes["POST /api/v1/tasks/task-merge/approve"] = () => {
      // After approval the task no longer waits.
      Object.assign(routes, workspaceRoutes({ withGateTask: false }));
      return { status: "approved", message: "Decision recorded. The engine continues from `merge`." };
    };
    const fetchImpl = createFakeFetch(routes);
    renderApp("/dashboard", fetchImpl);

    const button = await screen.findByRole("button", { name: "Approve FOR-14" });
    fireEvent.click(button);

    expect(await screen.findByText(/^Nothing needs you\./)).toBeInTheDocument();
    expect(fetchImpl.calls.some((call) => call.method === "POST" && call.url === "/api/v1/tasks/task-merge/approve")).toBe(true);
    // The projects table's counts are reloaded too.
    await waitFor(() => expect(fetchImpl.calls.filter((call) => call.url === "/api/v1/workspace")).toHaveLength(2));
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
    // (A 401 is not shown in the page: it brings up the sign-in page. See App.test.)
    routes["GET /api/v1/workspace"] = reply(500, { error: "The database is locked", code: "internal_error" });
    renderApp("/dashboard", createFakeFetch(routes));
    expect(await within(await screen.findByRole("region", { name: "Projects" })).findByRole("alert")).toHaveTextContent(
      "The database is locked.",
    );
  });

  it("shows placeholder rows only after 200 ms of loading", async () => {
    vi.useFakeTimers();
    const routes = workspaceRoutes();
    routes["GET /api/v1/workspace"] = () => new Promise(() => {});
    const { container } = renderApp("/dashboard", createFakeFetch(routes));
    expect(container.querySelectorAll(".table__placeholder")).toHaveLength(0);
    act(() => vi.advanceTimersByTime(200));
    expect(container.querySelectorAll(".table__placeholder").length).toBeGreaterThan(0);
  });

  it("caps Needs you at five and loads the rest from the server on Show all", async () => {
    const routes = workspaceRoutes({ withGateTask: false });
    const items = Array.from({ length: 7 }, (_, index) => ({
      ...UNBLOCK_ITEM,
      task_id: `t${index}`,
      task_key: `FOR-${100 + index}`,
      task_title: `Stuck ${index}`,
    }));
    routes["GET /api/v1/needs-you?limit=5&offset=0"] = { items: items.slice(0, 5), total: 7 };
    routes["GET /api/v1/needs-you?limit=2&offset=5"] = { items: items.slice(5), total: 7 };
    renderApp("/dashboard", createFakeFetch(routes));

    await screen.findByText("FOR-100");
    expect(screen.queryByText("FOR-105")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show all 7" }));
    expect(await screen.findByText("FOR-106")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show fewer" }));
    expect(screen.queryByText("FOR-106")).toBeNull();
  });
});

describe("adding a project", () => {
  it("registers a repository and opens the new project", async () => {
    const routes = workspaceRoutes();
    routes["GET /api/v1/workflows"] = { workflows: [{ id: "development", name: "Standard Development" }, { id: "light", name: "Light" }] };
    routes["POST /api/v1/projects"] = { id: "shop", name: "Shop", repo_path: "/srv/shop", workflow_id: "light" };
    const fetchImpl = createFakeFetch(routes);
    renderApp("/dashboard", fetchImpl);

    fireEvent.click(await screen.findByRole("button", { name: "Add project" }));
    const dialog = await screen.findByRole("dialog", { name: "Add a project" });
    // Nothing is sent until both the name and the folder are given.
    fireEvent.click(within(dialog).getByRole("button", { name: "Add project" }));
    expect(within(dialog).getByText("A project needs a name.")).toBeInTheDocument();
    expect(within(dialog).getByText("Say where the repository is.")).toBeInTheDocument();
    expect(fetchImpl.calls.some((call) => call.method === "POST")).toBe(false);

    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: " Shop " } });
    fireEvent.change(within(dialog).getByLabelText(/^Repository folder/), { target: { value: "/srv/shop" } });
    await within(dialog).findByRole("option", { name: "Light" });
    fireEvent.change(within(dialog).getByLabelText("Workflow"), { target: { value: "light" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add project" }));

    await waitFor(() => expect(window.location.pathname).toBe("/dashboard/projects/shop"));
    const sent = fetchImpl.calls.find((call) => call.method === "POST" && call.url === "/api/v1/projects");
    expect(sent.body).toEqual({ name: "Shop", repo_path: "/srv/shop", workflow_id: "light" });
  });

  it("keeps the dialog open with the API's sentence when the folder is refused", async () => {
    const routes = workspaceRoutes();
    routes["GET /api/v1/workflows"] = { workflows: [{ id: "development", name: "Standard Development" }] };
    routes["POST /api/v1/projects"] = reply(400, { error: "Repo path does not exist: /nowhere", code: "invalid_request" });
    renderApp("/dashboard", createFakeFetch(routes));
    fireEvent.click(await screen.findByRole("button", { name: "Add project" }));
    const dialog = await screen.findByRole("dialog", { name: "Add a project" });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: "Shop" } });
    fireEvent.change(within(dialog).getByLabelText(/^Repository folder/), { target: { value: "/nowhere" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add project" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Repo path does not exist: /nowhere");
  });
});
