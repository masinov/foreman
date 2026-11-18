import { readFileSync } from "node:fs";
import { join } from "node:path";

import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp, reply } from "../../testing/fakeApi";
import { backlogTask } from "../../testing/projectFixture";
import {
  ACCEPTED_URL,
  SPRINT_URL,
  sprintPayload,
  sprintRoutes,
  STEPS_URL,
  stepEvent,
  TASKS,
  taskPayload,
} from "../../testing/sprintFixture";
import { engine, workspacePayload } from "../../testing/workspaceFixture";

async function renderSprint(path = "/dashboard/sprints/sprint-56", routes = sprintRoutes()) {
  const fetchImpl = createFakeFetch(routes);
  const utils = renderApp(path, fetchImpl);
  await screen.findByRole("heading", { level: 1, name: "Sprint 56: engine truthfulness" });
  return { ...utils, fetchImpl };
}

function calls(fetchImpl, method, url) {
  return fetchImpl.calls.filter((call) => call.method === method && call.url === url);
}

function rowKeys() {
  return within(screen.getByRole("table", { name: "Tasks" }))
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[1].textContent);
}

describe("the sprint page head", () => {
  it("shows title, goal, state, counts and spend", async () => {
    await renderSprint();
    expect(screen.getByText("What the engine records is what happened.")).toBeInTheDocument();
    const summary = screen.getByText("State").closest("dl");
    expect(summary).toHaveTextContent(/State\s*Active since 11 Nov/);
    expect(summary).toHaveTextContent("1 need you · 1 in progress · 2 to do · 1 done");
    expect(summary).toHaveTextContent("$1.31 · 28.5K tokens");
    // Nothing about Foreman starting tasks where a person plans them all.
    expect(summary).not.toHaveTextContent(/Foreman/);
  });

  it("says how many tasks Foreman started itself where the project lets it", async () => {
    await renderSprint(
      "/dashboard/sprints/sprint-56",
      sprintRoutes({ sprint: sprintPayload({ picks_own_tasks: true, started_by_foreman: 2, foreman_limit: 5 }) }),
    );
    expect(screen.getByText("Started by Foreman").closest("div")).toHaveTextContent("2 of 5");
  });

  it("puts the project, with what needs you, in the breadcrumb", async () => {
    await renderSprint();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    const project = await within(crumbs).findByRole("link", { name: /Foreman/ });
    expect(project).toHaveAttribute("href", "/dashboard/projects/foreman");
    expect(project).toHaveTextContent("2");
    expect(within(crumbs).getByText("Sprint 56: engine truthfulness")).toHaveAttribute("aria-current", "page");
  });
});

describe("the view toggle", () => {
  it("is two links, and the rest of the page is the same in both views", async () => {
    const { unmount } = await renderSprint();
    const toggle = screen.getByRole("group", { name: "View" });
    expect(within(toggle).getByRole("link", { name: "List" })).toHaveAttribute("href", "/dashboard/sprints/sprint-56");
    expect(within(toggle).getByRole("link", { name: "List" })).toHaveAttribute("aria-current", "true");
    expect(within(toggle).getByRole("link", { name: "Board" })).toHaveAttribute("href", "/dashboard/sprints/sprint-56/board");
    const listHead = screen.getByText("State").closest("dl").textContent;
    unmount();

    await renderSprint("/dashboard/sprints/sprint-56/board");
    expect(screen.getByRole("link", { name: "Board" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByText("State").closest("dl").textContent).toBe(listHead);
    expect(screen.getByRole("button", { name: "Add from backlog" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Activity" })).toBeInTheDocument();
  });

  it("switches by clicking, without leaving the page", async () => {
    await renderSprint();
    fireEvent.click(screen.getByRole("link", { name: "Board" }));
    expect(await screen.findByRole("region", { name: "Queued" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/dashboard/sprints/sprint-56/board");
  });
});

describe("the list", () => {
  it("orders waiting for a person, running, queued in run order, then done", async () => {
    await renderSprint();
    expect(rowKeys()).toEqual(["FOR-14", "FOR-13", "FOR-17", "FOR-18", "FOR-10"]);
  });

  it("names the stage, the checks, runs and spend", async () => {
    await renderSprint();
    const row = screen.getByText("FOR-14").closest("tr");
    expect(within(row).getByText("Waiting for merge approval")).toBeInTheDocument();
    expect(row).toHaveTextContent("tests · review · b232eb1");
    expect(within(row).getByText("12")).toBeInTheDocument();
    expect(within(row).getByText("$0.72")).toBeInTheDocument();
    // The fixture's engine is on another task, so FOR-13 is not running.
    expect(await within(screen.getByText("FOR-13").closest("tr")).findByText("Stopped at test")).toBeInTheDocument();
    expect(within(screen.getByText("FOR-17").closest("tr")).getByText("Queued")).toBeInTheDocument();
    expect(within(screen.getByText("FOR-10").closest("tr")).getByText("Done")).toBeInTheDocument();
    expect(within(screen.getByText("FOR-17").closest("tr")).getByText("Not checked yet")).toBeInTheDocument();
  });

  it("says a task is running only while the engine is on it", async () => {
    const expectStage = async (state, task, words) => {
      const routes = sprintRoutes();
      const workspace = workspacePayload();
      workspace.projects[0].engine = engine(state, task);
      routes["GET /api/v1/workspace"] = workspace;
      const view = await renderSprint("/dashboard/sprints/sprint-56", routes);
      expect(await within(screen.getByText("FOR-13").closest("tr")).findByText(words)).toBeInTheDocument();
      view.unmount();
    };
    const onIt = { id: "t-run", task_key: "FOR-13", title: "x", step: "test" };
    await expectStage("running", onIt, "Running, test");
    await expectStage("paused", onIt, "Paused at test");
    await expectStage("not_running", null, "Stopped at test");
  });

  it("offers Approve only where a merge approval waits, and approving reloads", async () => {
    const routes = sprintRoutes();
    routes["POST /api/v1/tasks/t-merge/approve"] = { ok: true };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    expect(screen.getAllByRole("button", { name: /^Approve/ })).toHaveLength(1);
    const before = calls(fetchImpl, "GET", "/api/v1/sprints/sprint-56").length;
    fireEvent.click(screen.getByRole("button", { name: "Approve FOR-14" }));
    await waitFor(() => expect(calls(fetchImpl, "POST", "/api/v1/tasks/t-merge/approve")).toHaveLength(1));
    await waitFor(() => expect(calls(fetchImpl, "GET", "/api/v1/sprints/sprint-56").length).toBeGreaterThan(before));
    expect(await screen.findByRole("status")).toHaveTextContent("Approved FOR-14.");
  });

  it("shows the API's sentence when an approval is refused", async () => {
    const routes = sprintRoutes();
    routes["POST /api/v1/tasks/t-merge/approve"] = reply(409, { error: "Tests are stale; run them again.", code: "conflict" });
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    fireEvent.click(screen.getByRole("button", { name: "Approve FOR-14" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Tests are stale; run them again.");
  });
});

describe("the board", () => {
  beforeEach(() => window.localStorage.clear());

  async function renderBoard(routes) {
    await renderSprint("/dashboard/sprints/sprint-56/board", routes);
  }
  const columnNames = () => screen.getAllByRole("region").map((region) => region.getAttribute("aria-label")).filter(Boolean);

  it("has Queued first, one column per workflow step, and Done last", async () => {
    await renderBoard();
    expect(await screen.findByRole("region", { name: "Queued" })).toBeInTheDocument();
    expect(columnNames()).toEqual(["Queued", "Develop", "Test", "Review", "Merge approval", "Merge", "Done"]);
  });

  it("builds its columns from the project's workflow, not from names in the page", async () => {
    const other = {
      id: "research",
      name: "Research",
      steps: [
        { id: "gather", role: "researcher", policy: null },
        { id: "write_up", role: "writer", policy: null },
        { id: "finish", role: "_builtin:mark_done", policy: null },
      ],
    };
    await renderBoard(sprintRoutes({ workflow: other, tasks: [taskPayload("t1", "FOR-1", "in_progress", { workflow_current_step: "write_up" })] }));
    await screen.findByRole("region", { name: "Gather" });
    expect(columnNames()).toEqual(["Queued", "Gather", "Write up", "Done"]);
    expect(within(screen.getByRole("region", { name: "Write up" })).getByText("FOR-1")).toBeInTheDocument();
  });

  it("puts each task in its column with a count, and folds an empty one to its name and count", async () => {
    await renderBoard();
    const queued = await screen.findByRole("region", { name: "Queued" });
    expect(within(queued).getByText("2")).toBeInTheDocument();
    expect(within(queued).getByText("FOR-17")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Test" })).getByText("FOR-13")).toBeInTheDocument();
    const merge = screen.getByRole("region", { name: "Merge approval" });
    expect(within(merge).getByText("FOR-14")).toBeInTheDocument();
    expect(merge).toHaveTextContent("tests · review · b232eb1");
    expect(within(screen.getByRole("region", { name: "Done" })).getByText("FOR-10")).toBeInTheDocument();
    const develop = screen.getByRole("region", { name: "Develop" });
    expect(within(develop).getByRole("button", { name: "Show Develop" })).toHaveAttribute("aria-expanded", "false");
    expect(develop).toHaveTextContent("0");
  });

  it("folds and opens a column, and remembers the choice for the project", async () => {
    await renderBoard();
    const queued = await screen.findByRole("region", { name: "Queued" });
    fireEvent.click(within(queued).getByRole("button", { name: "Fold Queued" }));
    const folded = screen.getByRole("region", { name: "Queued" });
    expect(within(folded).queryByText("FOR-17")).toBeNull();
    expect(folded).toHaveTextContent("2");
    expect(JSON.parse(window.localStorage.getItem("foreman.dashboard.board.folded.foreman"))).toEqual({ queued: true });

    // An empty column opens on request, and stays open while it is empty.
    fireEvent.click(screen.getByRole("button", { name: "Show Develop" }));
    expect(within(screen.getByRole("region", { name: "Develop" })).getByRole("button", { name: "Fold Develop" })).toBeInTheDocument();
    fireEvent.click(within(folded).getByRole("button", { name: "Show Queued" }));
    expect(within(screen.getByRole("region", { name: "Queued" })).getByText("FOR-17")).toBeInTheDocument();
  });

  it("shows on a folded column that a task in it needs you", async () => {
    window.localStorage.setItem("foreman.dashboard.board.folded.foreman", JSON.stringify({ "step:merge_approval": true }));
    await renderBoard();
    const merge = await screen.findByRole("region", { name: "Merge approval" });
    expect(within(merge).queryByText("FOR-14")).toBeNull();
    expect(merge.querySelector(".board__count--attention")).toHaveTextContent("1");
  });

  it("approves from a card and reloads", async () => {
    const routes = sprintRoutes();
    routes["POST /api/v1/tasks/t-merge/approve"] = { ok: true };
    await renderBoard(routes);
    const merge = await screen.findByRole("region", { name: "Merge approval" });
    expect(screen.getAllByRole("button", { name: /^Approve/ })).toHaveLength(1);
    fireEvent.click(within(merge).getByRole("button", { name: "Approve FOR-14" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Approved FOR-14."));
  });

  it("fits in the window: a long column scrolls its cards under its heading", async () => {
    await renderBoard();
    await screen.findByRole("region", { name: "Queued" });
    // The board sets its height limit from where it starts in the window.
    expect(document.querySelector(".board-frame").style.getPropertyValue("--board-height")).toMatch(/px$/);
    const css = readFileSync(join(process.cwd(), "src", "styles", "sprint.css"), "utf8");
    const rule = (selector) => css.match(new RegExp(`\\n${selector.replace(/[.-]/g, "\\$&")} \\{([^}]*)\\}`))?.[1] ?? "";
    expect(rule(".board__column")).toContain("max-height: var(--board-height, none)");
    expect(rule(".board__cards")).toContain("overflow-y: auto");
    expect(rule(".board")).toContain("overflow-y: hidden");
  });

  it("has nothing to drag", async () => {
    await renderBoard();
    await screen.findByRole("region", { name: "Queued" });
    expect(document.querySelector("[draggable]")).toBeNull();
  });
});

describe("edit and the state action", () => {
  it("edits the title and goal through the sprint endpoint", async () => {
    const routes = sprintRoutes();
    routes["PATCH /api/v1/sprints/sprint-56"] = { id: "sprint-56" };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = screen.getByRole("dialog", { name: "Edit sprint" });
    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: "Sprint 56: honest engine" } });
    fireEvent.change(within(dialog).getByLabelText("Goal"), { target: { value: "New goal." } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(calls(fetchImpl, "PATCH", "/api/v1/sprints/sprint-56")[0].body).toEqual({ title: "Sprint 56: honest engine", goal: "New goal." }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("shows a refusal to an edit inside the dialog", async () => {
    const routes = sprintRoutes();
    routes["PATCH /api/v1/sprints/sprint-56"] = reply(422, { error: "Sprint title cannot be empty.", code: "invalid_request" });
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("Sprint title cannot be empty.");
  });

  it("finishes an active sprint", async () => {
    const routes = sprintRoutes();
    routes["PATCH /api/v1/sprints/sprint-56"] = { id: "sprint-56", status: "completed" };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    expect(screen.queryByRole("button", { name: "Activate sprint" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Finish sprint" }));
    await waitFor(() => expect(calls(fetchImpl, "PATCH", "/api/v1/sprints/sprint-56")[0].body).toEqual({ status: "completed" }));
  });

  it("shows the API's sentence when finishing is refused", async () => {
    const routes = sprintRoutes();
    routes["PATCH /api/v1/sprints/sprint-56"] = reply(422, {
      error: "Sprint cannot be completed while unresolved tasks remain: FOR-14. Finish or cancel them, or cancel the sprint.",
      code: "invalid_request",
    });
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    fireEvent.click(screen.getByRole("button", { name: "Finish sprint" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sprint cannot be completed while unresolved tasks remain: FOR-14.");
  });

  it("activates a planned sprint and offers no Finish", async () => {
    const routes = sprintRoutes({ sprint: sprintPayload({ status: "planned", started_at: null }) });
    routes["PATCH /api/v1/sprints/sprint-56"] = { id: "sprint-56", status: "active" };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    expect(screen.getByText("Planned, not started")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finish sprint" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Activate sprint" }));
    await waitFor(() => expect(calls(fetchImpl, "PATCH", "/api/v1/sprints/sprint-56")[0].body).toEqual({ status: "active" }));
  });

  it("shows a finished sprint with no state action and no Add from backlog", async () => {
    await renderSprint(
      "/dashboard/sprints/sprint-56",
      sprintRoutes({ sprint: sprintPayload({ status: "completed", completed_at: "2025-01-02T10:00:00Z" }) }),
    );
    expect(screen.queryByRole("button", { name: /sprint$/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add from backlog" })).toBeNull();
    expect(screen.getByText(/Finished 2 Jan 2025/)).toBeInTheDocument();
  });
});

describe("new task in the sprint", () => {
  it("writes a task straight into this sprint and reloads", async () => {
    const routes = sprintRoutes();
    routes["POST /api/v1/sprints/sprint-56/tasks"] = { id: "task-new", task_key: "FOR-99", title: "Tighten the retry" };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    fireEvent.click(screen.getByRole("button", { name: "New task" }));
    const dialog = await screen.findByRole("dialog", { name: "New task" });
    expect(dialog).toHaveTextContent("It goes straight into Sprint 56: engine truthfulness and runs with it.");
    fireEvent.change(within(dialog).getByLabelText(/Title/), { target: { value: "Tighten the retry" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /^(Create|File|Add)/ }));
    await waitFor(() =>
      expect(calls(fetchImpl, "POST", "/api/v1/sprints/sprint-56/tasks")[0].body).toMatchObject({
        title: "Tighten the retry",
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("status")).toHaveTextContent("FOR-99 added to Sprint 56: engine truthfulness.");
    expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/backlog")).toHaveLength(0);
  });

  it("can make the new task wait for unfinished tasks of the sprint", async () => {
    const routes = sprintRoutes();
    routes["POST /api/v1/sprints/sprint-56/tasks"] = { id: "task-new", task_key: "FOR-99", title: "Tighten the retry" };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    const open = TASKS.filter((task) => ["todo", "in_progress", "blocked"].includes(task.status));
    const finished = TASKS.find((task) => task.status === "done");
    fireEvent.click(screen.getByRole("button", { name: "New task" }));
    const dialog = await screen.findByRole("dialog", { name: "New task" });
    fireEvent.change(within(dialog).getByLabelText(/Title/), { target: { value: "Tighten the retry" } });
    fireEvent.click(await within(dialog).findByRole("button", { name: "Make it wait for other tasks" }));
    // A finished task is nothing to wait for.
    expect(within(dialog).getAllByRole("checkbox")).toHaveLength(open.length);
    if (finished) expect(within(dialog).queryByRole("checkbox", { name: new RegExp(finished.title) })).toBeNull();
    fireEvent.click(within(dialog).getAllByRole("checkbox")[0]);
    expect(within(dialog).getByRole("button", { name: "Waits for 1 task" })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Add task" }));
    await waitFor(() =>
      expect(calls(fetchImpl, "POST", "/api/v1/sprints/sprint-56/tasks")[0].body).toMatchObject({
        title: "Tighten the retry",
        complexity: null,
        depends_on: [open[0].id],
      }),
    );
  });

  it("is not offered on a finished sprint", async () => {
    const routes = sprintRoutes();
    routes[SPRINT_URL] = sprintPayload({ status: "completed", completed_at: "2026-11-11T10:00:00Z" });
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    expect(screen.queryByRole("button", { name: "New task" })).toBeNull();
  });
});

describe("add from backlog", () => {
  const accepted = [
    backlogTask("task-a", "Resume a stale agent step in place", "accepted"),
    backlogTask("task-b", "Check the lease fencing token", "accepted"),
  ];
  const withAccepted = () => {
    const routes = sprintRoutes();
    routes[ACCEPTED_URL] = { tasks: accepted, total: 2, counts: { accepted: 2 }, triage: "human" };
    return routes;
  };

  it("lists accepted work and plans the chosen tasks into this sprint", async () => {
    const routes = withAccepted();
    routes["POST /api/v1/projects/foreman/backlog/plan"] = { planned: 1 };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    fireEvent.click(screen.getByRole("button", { name: "Add from backlog" }));
    const dialog = await screen.findByRole("dialog", { name: "Add from backlog" });
    expect(await within(dialog).findByText("Resume a stale agent step in place")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Plan" })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Check the lease fencing token/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Plan 1 task" }));
    await waitFor(() =>
      expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/backlog/plan")[0].body).toEqual({
        task_ids: ["task-b"],
        sprint_id: "sprint-56",
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("status")).toHaveTextContent("1 task planned into Sprint 56: engine truthfulness.");
  });

  it("shows the API's sentence when planning is refused, and keeps the dialog open", async () => {
    const routes = withAccepted();
    routes["POST /api/v1/projects/foreman/backlog/plan"] = reply(422, { error: "Sprint is completed; plan into an open sprint.", code: "invalid_request" });
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    fireEvent.click(screen.getByRole("button", { name: "Add from backlog" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("checkbox", { name: /Resume a stale/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Plan 1 task" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Sprint is completed; plan into an open sprint.");
  });

  it("says so when no accepted work is waiting", async () => {
    await renderSprint();
    fireEvent.click(screen.getByRole("button", { name: "Add from backlog" }));
    expect(await screen.findByText(/Nothing is waiting to be planned/)).toBeInTheDocument();
  });
});

describe("activity", () => {
  const events = Array.from({ length: 3 }, (_, index) => stepEvent(`e${index}`, "t-merge", index === 0 ? "review" : "test", "success", `2025-11-11T1${index}:00:00Z`));

  it("lists finished steps newest first with the task key", async () => {
    // The API sends them oldest first within the page; the page shows newest first.
    await renderSprint("/dashboard/sprints/sprint-56", sprintRoutes({ events }));
    const table = await screen.findByRole("table", { name: "Finished steps" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("FOR-14");
    expect(rows[0]).toHaveTextContent("Test");
    expect(rows[2]).toHaveTextContent("Review");
    expect(screen.queryByRole("button", { name: "Earlier steps" })).toBeNull();
  });

  it("loads earlier steps from the oldest one shown", async () => {
    const routes = sprintRoutes({ events });
    routes[STEPS_URL] = { events, has_more: true };
    routes["GET /api/v1/sprints/sprint-56/events?type=workflow.step_completed&limit=25&before=e0"] = {
      events: [stepEvent("e-old", "t-run", "develop", "success", "2025-11-10T09:00:00Z")],
      has_more: false,
    };
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    fireEvent.click(await screen.findByRole("button", { name: "Earlier steps" }));
    await waitFor(() => expect(within(screen.getByRole("table", { name: "Finished steps" })).getAllByRole("row")).toHaveLength(5));
    expect(screen.queryByRole("button", { name: "Earlier steps" })).toBeNull();
  });

  it("goes back to the newest page with Show fewer, from the middle and from the end", async () => {
    const page = (prefix, count) =>
      Array.from({ length: count }, (_, index) => stepEvent(`${prefix}${index}`, "t-merge", "test", "success", "2025-11-11T10:00:00Z"));
    const routes = sprintRoutes({ events });
    routes[STEPS_URL] = { events: page("a", 25), has_more: true };
    routes["GET /api/v1/sprints/sprint-56/events?type=workflow.step_completed&limit=25&before=a0"] = { events: page("b", 25), has_more: true };
    routes["GET /api/v1/sprints/sprint-56/events?type=workflow.step_completed&limit=25&before=b0"] = { events: page("c", 4), has_more: false };
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    const rowCount = () => within(screen.getByRole("table", { name: "Finished steps" })).getAllByRole("row").length - 1;
    await waitFor(() => expect(rowCount()).toBe(25));
    // Nothing to go back from on the first page.
    expect(screen.queryByRole("button", { name: "Show fewer" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Earlier steps" }));
    await waitFor(() => expect(rowCount()).toBe(50));
    // In the middle: more, and the way back.
    expect(screen.getByRole("button", { name: "Earlier steps" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show fewer" }));
    expect(rowCount()).toBe(25);
    expect(screen.queryByRole("button", { name: "Show fewer" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Earlier steps" }));
    await waitFor(() => expect(rowCount()).toBe(50));
    fireEvent.click(screen.getByRole("button", { name: "Earlier steps" }));
    await waitFor(() => expect(rowCount()).toBe(54));
    // At the end: only the way back.
    expect(screen.queryByRole("button", { name: "Earlier steps" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show fewer" }));
    expect(rowCount()).toBe(25);
    expect(screen.getByRole("button", { name: "Earlier steps" })).toBeInTheDocument();
  });

  it("says when no step has finished", async () => {
    await renderSprint();
    expect(await screen.findByText("No step has finished in this sprint yet.")).toBeInTheDocument();
  });
});

describe("the engine menu in the top bar", () => {
  function routesWithEngine(state) {
    const routes = sprintRoutes();
    const payload = workspacePayload();
    payload.projects[0].engine = engine(state);
    routes["GET /api/v1/workspace"] = payload;
    return routes;
  }

  it("holds Pause and Stop while the engine runs, and sends the same commands as the project page", async () => {
    const routes = routesWithEngine("running");
    routes["POST /api/v1/projects/foreman/agent/stop"] = { command: {} };
    routes["POST /api/v1/projects/foreman/engine/commands"] = { command: {} };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    const trigger = await screen.findByRole("button", { name: /^Engine: running/ });
    fireEvent.click(trigger);
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Pause", "Stop"]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Pause" }));
    await waitFor(() => expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/agent/stop")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: /^Engine: running/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Stop" }));
    await waitFor(() => expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/engine/commands")[0].body).toEqual({ command: "shutdown" }));
  });

  it("holds only Start when the engine is not running", async () => {
    await renderSprint("/dashboard/sprints/sprint-56", routesWithEngine("not_running"));
    fireEvent.click(await screen.findByRole("button", { name: /^Engine: not running/ }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Start"]);
  });

  it("holds Resume and Stop when the engine is paused", async () => {
    await renderSprint("/dashboard/sprints/sprint-56", routesWithEngine("paused"));
    fireEvent.click(await screen.findByRole("button", { name: /^Engine: paused/ }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Resume", "Stop"]);
  });

  it("shows the API's sentence when a command is refused", async () => {
    const routes = routesWithEngine("not_running");
    routes["POST /api/v1/projects/foreman/agent/start"] = reply(409, { error: "Another engine holds the lock.", code: "conflict" });
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    fireEvent.click(await screen.findByRole("button", { name: /^Engine: not running/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Start" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Another engine holds the lock.");
  });
});

describe("when the sprint cannot be read", () => {
  it("shows the API's sentence and a way out", async () => {
    const fetchImpl = createFakeFetch({ ...sprintRoutes(), [SPRINT_URL]: reply(404, { error: "Sprint not found: sprint-56", code: "not_found" }) });
    renderApp("/dashboard/sprints/sprint-56", fetchImpl);
    expect(await screen.findByText("This sprint could not be shown")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Sprint not found: sprint-56");
  });
});

describe("More on the sprint page", () => {
  async function choose(item) {
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: item }));
    return screen.findByRole("dialog");
  }

  it("cancels an open sprint after saying what that means", async () => {
    const routes = sprintRoutes();
    routes["PATCH /api/v1/sprints/sprint-56"] = { id: "sprint-56", status: "cancelled" };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    const dialog = await choose("Cancel sprint");
    expect(dialog).toHaveTextContent("nothing in it runs again");
    expect(calls(fetchImpl, "PATCH", "/api/v1/sprints/sprint-56")).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel sprint" }));
    await waitFor(() => expect(calls(fetchImpl, "PATCH", "/api/v1/sprints/sprint-56")[0].body).toEqual({ status: "cancelled" }));
  });

  it("deletes a sprint and goes to its project; a refusal stays in the dialog", async () => {
    const routes = sprintRoutes();
    routes["DELETE /api/v1/sprints/sprint-56"] = reply(400, { error: "FOR-14 is running; stop it before deleting.", code: "invalid_request" });
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    const dialog = await choose("Delete sprint");
    expect(dialog).toHaveTextContent("This cannot be undone.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete sprint" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("FOR-14 is running");

    routes["DELETE /api/v1/sprints/sprint-56"] = { ok: "deleted", sprint_id: "sprint-56", project_id: "foreman" };
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete sprint" }));
    await waitFor(() => expect(window.location.pathname).toBe("/dashboard/projects/foreman"));
    expect(calls(fetchImpl, "DELETE", "/api/v1/sprints/sprint-56")).toHaveLength(2);
  });

  it("offers only Delete once a sprint is finished", async () => {
    await renderSprint(
      "/dashboard/sprints/sprint-56",
      sprintRoutes({ sprint: sprintPayload({ status: "completed", completed_at: "2025-01-02T10:00:00Z" }) }),
    );
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(await screen.findByRole("menuitem", { name: "Delete sprint" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Cancel sprint" })).toBeNull();
  });
});
