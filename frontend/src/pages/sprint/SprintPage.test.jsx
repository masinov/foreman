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
  PROBLEM_STEPS_URL,
  sprintRun,
  STEPS_URL,
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

  it("offers to reopen a finished sprint, and no Add from backlog", async () => {
    await renderSprint(
      "/dashboard/sprints/sprint-56",
      sprintRoutes({ sprint: sprintPayload({ status: "completed", completed_at: "2025-01-02T10:00:00Z" }) }),
    );
    expect(screen.getAllByRole("button", { name: /sprint$/ }).map((button) => button.textContent)).toEqual(["Reopen sprint"]);
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
  const page = (items, total = items.length, offset = 0) => ({ items, total, limit: 25, offset });
  const cells = (row) => within(row).getAllByRole("cell").map((cell) => cell.textContent);

  it("is one line per row: when, the task, what happened naming its step, who, how long, what it cost", async () => {
    const runs = [
      sprintRun("run-9", "t-merge", "review", {
        role_id: "code_reviewer",
        outcome: "steer",
        outcome_detail: "The log can still contain the host and port.",
      }),
      sprintRun("run-8", "t-merge", "test", { role_id: "_builtin:run_tests", backend: "builtin", model: null, outcome: "success", cost_usd: 0 }),
      sprintRun("run-7", "t-merge", "develop", { duration_ms: 261900 }),
      sprintRun("run-6", "t-merge", "merge", { role_id: "_builtin:merge", backend: "builtin", model: null, outcome: "success", duration_ms: 100, cost_usd: 0 }),
      sprintRun("ev-1", "t-run", null, { source: "event", outcome: "cancelled", actor: "ana", outcome_detail: "Not needed.", duration_ms: null, cost_usd: 0 }),
    ];
    await renderSprint("/dashboard/sprints/sprint-56", sprintRoutes({ runs }));
    const table = await screen.findByRole("table", { name: "Activity" });
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "When",
      "Task",
      "What happened",
      "By",
      "Took",
      "Spend",
    ]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(cells(rows[0]).slice(1)).toEqual(["FOR-14 · Title of FOR-14", "Sent back", "sonnet-5-5", "7 s", "$0.12"]);
    // Why is on hover, not under the row.
    expect(within(rows[0]).getByText("Sent back")).toHaveAttribute("title", "The log can still contain the host and port.");
    expect(rows[0]).not.toHaveTextContent("The log can");
    expect(cells(rows[1]).slice(2)).toEqual(["Tests passed", "Foreman", "7 s", ""]);
    expect(cells(rows[2]).slice(2)).toEqual(["Developed", "sonnet-5-5", "4 min 22 s", "$0.12"]);
    // A step that took under a second says nothing about it.
    expect(cells(rows[3]).slice(2)).toEqual(["Merged", "Foreman", "", ""]);
    expect(cells(rows[4]).slice(2)).toEqual(["Cancelled", "ana", "", ""]);
    // The whole title is on hover; the cell cuts it.
    expect(within(rows[0]).getByRole("link")).toHaveAttribute("title", "FOR-14 · Title of FOR-14");
    expect(screen.queryByRole("button", { name: "Earlier" })).toBeNull();
  });

  it("leads a run's row to that run on the task's Activity, and a person's act to the task", async () => {
    const runs = [
      sprintRun("run-9", "t-merge", "develop"),
      sprintRun("ev-1", "t-run", null, { source: "event", outcome: "closed", actor: "ana" }),
    ];
    await renderSprint("/dashboard/sprints/sprint-56", sprintRoutes({ runs }));
    const rows = within(await screen.findByRole("table", { name: "Activity" })).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByRole("link")).toHaveAttribute("href", "/dashboard/tasks/t-merge/activity?run=run-9");
    expect(within(rows[1]).getByRole("link")).toHaveAttribute("href", "/dashboard/tasks/t-run");
    // Anywhere on the row goes there, not only its link.
    fireEvent.click(within(rows[0]).getByText("Developed"));
    expect(window.location.pathname).toBe("/dashboard/tasks/t-merge/activity");
    expect(window.location.search).toBe("?run=run-9");
  });

  it("shows only problems when asked, and says when there were none", async () => {
    const routes = sprintRoutes({ runs: [sprintRun("run-9", "t-merge", "review")] });
    routes[PROBLEM_STEPS_URL] = page([]);
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    await screen.findByRole("table", { name: "Activity" });
    fireEvent.click(screen.getByRole("button", { name: "Problems" }));
    expect(await screen.findByText("Nothing was sent back, failed or was blocked in this sprint.")).toBeInTheDocument();
    expect(calls(fetchImpl, "GET", PROBLEM_STEPS_URL.slice(4))).toHaveLength(1);
  });

  it("loads earlier rows 25 at a time, and goes back with Show fewer", async () => {
    const many = (prefix, count) => Array.from({ length: count }, (_, index) => sprintRun(`${prefix}${index}`, "t-merge", "test"));
    const routes = sprintRoutes();
    routes[STEPS_URL] = page(many("a", 25), 29);
    routes["GET /api/v1/sprints/sprint-56/activity?limit=25&offset=25"] = page(many("b", 4), 29, 25);
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    const rowCount = () => within(screen.getByRole("table", { name: "Activity" })).getAllByRole("row").length - 1;
    await waitFor(() => expect(rowCount()).toBe(25));
    fireEvent.click(screen.getByRole("button", { name: "Earlier" }));
    await waitFor(() => expect(rowCount()).toBe(29));
    expect(screen.queryByRole("button", { name: "Earlier" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show fewer" }));
    expect(rowCount()).toBe(25);
  });

  it("says when nothing has happened yet", async () => {
    await renderSprint();
    expect(await screen.findByText("Nothing has happened to this sprint's tasks yet.")).toBeInTheDocument();
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
