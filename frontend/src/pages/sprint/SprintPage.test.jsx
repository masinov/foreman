import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup as cleanupApp, fireEvent, screen, waitFor, within } from "@testing-library/react";

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
import { engine, work, workspacePayload } from "../../testing/workspaceFixture";

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
    // The goal beside the details, each under its heading, as on a task's Overview.
    expect(screen.getByRole("heading", { name: "Goal" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Details" })).toBeInTheDocument();
    expect(screen.getByText("What the engine records is what happened.")).toBeInTheDocument();
    const summary = screen.getByText("State").closest("dl");
    expect(summary).toHaveTextContent(/State\s*Active since 11 Nov/);
    expect(summary).toHaveTextContent("1 need you · 1 in progress · 2 to do · 1 done");
    expect(summary).toHaveTextContent("$1.31 · 28.5K tokens");
    expect(within(summary).getByText("$1.31 · 28.5K tokens")).toHaveClass("mono");
    // Nothing about Foreman starting tasks where a user plans them all.
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
    // Tasks is the current tab in both views; the activity is a tab of its own.
    const tabs = screen.getByRole("navigation", { name: "Sprint" });
    expect(within(tabs).getByRole("link", { name: /^Tasks/ })).toHaveAttribute("aria-current", "page");
    expect(within(tabs).getByRole("link", { name: "Activity" })).toHaveAttribute("href", "/dashboard/sprints/sprint-56/activity");
    expect(screen.queryByRole("table", { name: "Activity" })).toBeNull();
  });

  it("switches by clicking, without leaving the page", async () => {
    await renderSprint();
    fireEvent.click(screen.getByRole("link", { name: "Board" }));
    expect(await screen.findByRole("region", { name: "Queued" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/dashboard/sprints/sprint-56/board");
  });
});

describe("the list", () => {
  it("orders waiting for a user, running, queued in run order, then done", async () => {
    await renderSprint();
    expect(rowKeys()).toEqual(["FOR-14", "FOR-13", "FOR-17", "FOR-18", "FOR-10"]);
  });

  it("names the stage, the checks, runs and spend", async () => {
    await renderSprint();
    const row = screen.getByText("FOR-14").closest("tr");
    expect(within(row).getByText("Waiting for merge approval")).toBeInTheDocument();
    expect(row).toHaveTextContent("tests · review · b232eb1");
    expect(within(row).getByText("12")).toBeInTheDocument();
    expect(within(row).getByText("$0.72")).toHaveClass("mono");
    // No step of FOR-13 runs: it waits its turn.
    expect(await within(screen.getByText("FOR-13").closest("tr")).findByText("Waiting · Test")).toBeInTheDocument();
    expect(within(screen.getByText("FOR-17").closest("tr")).getByText("Queued")).toBeInTheDocument();
    expect(within(screen.getByText("FOR-10").closest("tr")).getByText("Done")).toBeInTheDocument();
    expect(within(screen.getByText("FOR-17").closest("tr")).getByText("Not checked yet")).toBeInTheDocument();
  });

  it("heads the column Status, and says the step a blocked task stopped at", async () => {
    await renderSprint(
      "/dashboard/sprints/sprint-56",
      sprintRoutes({
        tasks: [
          taskPayload("t1", "FOR-1", "blocked", { workflow_current_step: "test" }),
          taskPayload("t2", "FOR-2", "blocked", { workflow_current_step: null }),
        ],
      }),
    );
    const table = screen.getByText("FOR-1").closest("table");
    expect(within(table).getAllByRole("columnheader")[0]).toHaveTextContent("Status");
    expect(within(screen.getByText("FOR-1").closest("tr")).getByText("Blocked · Test")).toBeInTheDocument();
    // At no step, the status alone.
    expect(within(screen.getByText("FOR-2").closest("tr")).getByText("Blocked")).toBeInTheDocument();
  });

  it("says a task is running while a step of it runs, and what a user's hold makes of it", async () => {
    const at = "2026-11-02T14:02:00Z";
    const routes = sprintRoutes({
      tasks: [
        taskPayload("t1", "FOR-1", "in_progress", { workflow_current_step: "develop", step_running: true }),
        taskPayload("t2", "FOR-2", "in_progress", {
          workflow_current_step: "develop", step_running: true, hold: { scope: "task", kind: "pause", mode: "finish_step", by: "ana", at },
        }),
        taskPayload("t3", "FOR-3", "in_progress", {
          workflow_current_step: "test", hold: { scope: "task", kind: "pause", mode: "now", by: "ana", at },
        }),
        taskPayload("t4", "FOR-4", "todo", { hold: { scope: "sprint", kind: "block", mode: "finish_step", by: "ana", at, reason: "design review" } }),
        taskPayload("t5", "FOR-5", "todo", { waits_for: ["FOR-1"] }),
      ],
    });
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    const stage = (key) => within(screen.getByText(key).closest("tr"));
    expect(await stage("FOR-1").findByText("Running · Develop")).toBeInTheDocument();
    expect(stage("FOR-2").getByText("Pausing · Develop")).toBeInTheDocument();
    expect(stage("FOR-3").getByText("Stopped · Test").closest("[title]")).toHaveAttribute(
      "title",
      "Stopped by ana at 2 Nov; the cut step runs again on Resume.",
    );
    expect(stage("FOR-4").getByText("Blocked").closest("[title]")).toHaveAttribute(
      "title",
      "The sprint is blocked: design review",
    );
    expect(stage("FOR-5").getByText("Waiting · FOR-1")).toBeInTheDocument();
  });

  it("says Waiting with another task running, Runs next when asked, and that no worker runs", async () => {
    const routes = sprintRoutes({
      tasks: [
        taskPayload("t1", "FOR-1", "in_progress", { workflow_current_step: "develop" }),
        taskPayload("t2", "FOR-2", "in_progress", { workflow_current_step: "develop", run_next: true }),
        taskPayload("t3", "FOR-3", "todo", { run_next: true }),
      ],
    });
    const workspace = workspacePayload();
    workspace.projects[0].engine = engine("running", { id: "t-x", task_key: "FOR-53", title: "x", step: "test" });
    routes["GET /api/v1/workspace"] = workspace;
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    const waiting = await screen.findByText("Waiting · Develop");
    expect(waiting.closest("[title]")).toHaveAttribute("title", "Foreman runs it after FOR-53");
    expect(within(screen.getByText("FOR-2").closest("tr")).getByText("Runs next · Develop")).toBeInTheDocument();
    expect(within(screen.getByText("FOR-3").closest("tr")).getByText("Runs next")).toBeInTheDocument();
  });

  it("offers Approve only where a merge approval waits, and approving reloads", async () => {
    const routes = sprintRoutes();
    routes["POST /api/v1/tasks/t-merge/approve"] = { status: "approved", next_step: "merge", engine_resident: false };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    expect(screen.getAllByRole("button", { name: /^Approve/ })).toHaveLength(1);
    const before = calls(fetchImpl, "GET", "/api/v1/sprints/sprint-56").length;
    fireEvent.click(screen.getByRole("button", { name: "Approve FOR-14" }));
    await waitFor(() => expect(calls(fetchImpl, "POST", "/api/v1/tasks/t-merge/approve")).toHaveLength(1));
    await waitFor(() => expect(calls(fetchImpl, "GET", "/api/v1/sprints/sprint-56").length).toBeGreaterThan(before));
    const toast = await screen.findByRole("status");
    expect(toast).toHaveTextContent("Approved FOR-14. It waits at Merge until a worker runs.");
    // A passing note in the corner: nothing is added between the tabs and the table.
    const table = screen.getByText("FOR-14").closest("table");
    const tab = table.closest(".sprint__tab");
    expect(tab.querySelector("[role=status]")).toBeNull();
    expect(tab.querySelector(".notice")).toBeNull();
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
    expect(screen.queryByRole("button", { name: "Start sprint" })).toBeNull();
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

  it("starts a planned sprint and offers no Finish", async () => {
    const routes = sprintRoutes({ sprint: sprintPayload({ status: "planned", started_at: null }) });
    routes["PATCH /api/v1/sprints/sprint-56"] = { id: "sprint-56", status: "active" };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    expect(screen.getByText("Planned, not started")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finish sprint" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Start sprint" }));
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

describe("an active sprint whose every task is finished", () => {
  it("says in State that it is ready to finish, with Finish sprint beside the title", async () => {
    await renderSprint("/dashboard/sprints/sprint-56", sprintRoutes({ sprint: sprintPayload({ ready_to_finish: true }) }));
    const details = screen.getByRole("region", { name: "Details" });
    expect(details).toHaveTextContent(/State\s*Ready to finish(?!,)/);
    expect(within(details).getByTitle("Every task is done or cancelled.")).toHaveTextContent("Ready to finish");
    expect(screen.getByRole("button", { name: "Finish sprint" })).toBeInTheDocument();
  });
});

describe("a finished sprint's checkpoint", () => {
  const finished = (checkpoint) =>
    sprintRoutes({ sprint: sprintPayload({ status: "completed", completed_at: "2025-01-02T10:00:00Z", checkpoint }) });
  const stateRow = () => within(screen.getByRole("region", { name: "Details" })).getByText("State").closest(".details-list__row");

  it("says in State which commit the sprint's tag marks, and the tag on hover", async () => {
    await renderSprint(
      "/dashboard/sprints/sprint-56",
      finished({ tag: "checkpoint-20250102-engine-truthfulness", sha: "6332732aa0c0ffee", note_path: "docs/checkpoints/checkpoint-20250102-engine-truthfulness.md", problem: null }),
    );
    expect(stateRow()).toHaveTextContent(/State\s*Finished 2 Jan 2025 at 6332732$/);
    expect(within(stateRow()).getByTitle("Tagged checkpoint-20250102-engine-truthfulness")).toBeInTheDocument();
    // Neither the tag's name nor the note's path is a row of its own.
    const details = screen.getByRole("region", { name: "Details" });
    expect(details).not.toHaveTextContent("checkpoint-20250102");
    expect(details).not.toHaveTextContent("docs/checkpoints");
  });

  it("says when a finished sprint was not tagged, and why on hover", async () => {
    await renderSprint("/dashboard/sprints/sprint-56", finished({ tag: null, sha: null, note_path: null, problem: "The repository has no branch 'main' to tag." }));
    expect(stateRow()).toHaveTextContent(/State\s*Finished 2 Jan 2025, not tagged$/);
    expect(within(stateRow()).getByTitle("The repository has no branch 'main' to tag.")).toBeInTheDocument();
  });

  it("says nothing about a tag on a sprint finished before sprints were tagged", async () => {
    await renderSprint("/dashboard/sprints/sprint-56", finished(null));
    expect(stateRow()).toHaveTextContent(/State\s*Finished 2 Jan 2025$/);
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

describe("the tabs", () => {
  it("are Tasks, with its count, and Activity, with each tab's controls on the tab line", async () => {
    await renderSprint();
    const tabs = screen.getByRole("navigation", { name: "Sprint" });
    expect(within(tabs).getByRole("link", { name: /^Tasks/ })).toHaveTextContent("Tasks 5");
    const line = tabs.parentElement;
    expect(within(line).getByRole("button", { name: "Add from backlog" })).toBeInTheDocument();
    expect(within(line).getByRole("group", { name: "View" })).toBeInTheDocument();

    fireEvent.click(within(tabs).getByRole("link", { name: "Activity" }));
    expect(await screen.findByText("Nothing has happened to this sprint's tasks yet.")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/dashboard/sprints/sprint-56/activity");
    const activityLine = screen.getByRole("navigation", { name: "Sprint" }).parentElement;
    expect(within(activityLine).getByLabelText("By")).toBeInTheDocument();
    expect(within(activityLine).getByRole("button", { name: "Problems" })).toBeInTheDocument();
    expect(within(activityLine).queryByRole("button", { name: "Add from backlog" })).toBeNull();
    expect(screen.queryByRole("table", { name: "Tasks" })).toBeNull();
    // The head stays.
    expect(screen.getByRole("heading", { name: "Goal" })).toBeInTheDocument();
  });
});

describe("activity", () => {
  const ACTIVITY = "/dashboard/sprints/sprint-56/activity";
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
    await renderSprint(ACTIVITY, sprintRoutes({ runs }));
    const table = await screen.findByRole("table", { name: "Activity" });
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "When",
      "Key",
      "Task",
      "What happened",
      "By",
      "Took",
      "Spend",
    ]);
    const rows = within(table).getAllByRole("row").slice(1);
    // The key has its own column, as in the task list above.
    expect(cells(rows[0]).slice(1)).toEqual(["FOR-14", "Title of FOR-14", "Sent back", "Code reviewer", "7 s", "$0.12"]);
    expect(within(rows[0]).getByText("$0.12")).toHaveClass("mono");
    // By names the role; the model is on hover.
    expect(within(rows[0]).getByText("Code reviewer")).toHaveAttribute("title", "sonnet-5-5");
    // Why is on hover, not under the row.
    expect(within(rows[0]).getByText("Sent back")).toHaveAttribute("title", "The log can still contain the host and port.");
    expect(rows[0]).not.toHaveTextContent("The log can");
    expect(cells(rows[1]).slice(3)).toEqual(["Tests passed", "Foreman", "7 s", ""]);
    expect(cells(rows[2]).slice(3)).toEqual(["Developed", "Developer", "4 min 22 s", "$0.12"]);
    // A step that took under a second says nothing about it.
    expect(cells(rows[3]).slice(3)).toEqual(["Merged", "Foreman", "", ""]);
    expect(cells(rows[4]).slice(3)).toEqual(["Cancelled", "ana", "", ""]);
    // The whole title is on hover; the cell cuts it.
    expect(within(rows[0]).getByRole("link")).toHaveAttribute("title", "FOR-14 · Title of FOR-14");
    expect(screen.queryByRole("button", { name: "Earlier" })).toBeNull();
  });

  it("leads a run's row to that run on the task's Activity, and a user's act to the task", async () => {
    const runs = [
      sprintRun("run-9", "t-merge", "develop"),
      sprintRun("ev-1", "t-run", null, { source: "event", outcome: "closed", actor: "ana" }),
    ];
    await renderSprint(ACTIVITY, sprintRoutes({ runs }));
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
    const { fetchImpl } = await renderSprint(ACTIVITY, routes);
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
    await renderSprint(ACTIVITY, routes);
    const rowCount = () => within(screen.getByRole("table", { name: "Activity" })).getAllByRole("row").length - 1;
    await waitFor(() => expect(rowCount()).toBe(25));
    fireEvent.click(screen.getByRole("button", { name: "Earlier" }));
    await waitFor(() => expect(rowCount()).toBe(29));
    expect(screen.queryByRole("button", { name: "Earlier" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show fewer" }));
    expect(rowCount()).toBe(25);
  });

  it("keeps what one role, Foreman or users did, offering who appears in the sprint", async () => {
    const routes = sprintRoutes({ runs: [sprintRun("run-9", "t-merge", "review", { role_id: "code_reviewer" })] });
    routes[STEPS_URL].who = ["code_reviewer", "developer", "foreman", "user"];
    routes["GET /api/v1/sprints/sprint-56/activity?by=developer&limit=25&offset=0"] = page([sprintRun("run-7", "t-merge", "develop")]);
    routes["GET /api/v1/sprints/sprint-56/activity?only=problems&by=developer&limit=25&offset=0"] = page([]);
    await renderSprint(ACTIVITY, routes);
    await screen.findByRole("table", { name: "Activity" });
    const by = screen.getByLabelText("By");
    expect(within(by).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Everyone",
      "Code reviewer",
      "Developer",
      "Foreman",
      "Users",
    ]);
    fireEvent.change(by, { target: { value: "developer" } });
    expect(await screen.findByText("Developed")).toBeInTheDocument();
    expect(screen.queryByText("Sent back")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Problems" }));
    expect(await screen.findByText("Nothing in this sprint matches these filters.")).toBeInTheDocument();
  });

  it("says when nothing has happened yet", async () => {
    await renderSprint(ACTIVITY);
    expect(await screen.findByText("Nothing has happened to this sprint's tasks yet.")).toBeInTheDocument();
  });
});

describe("the work menu in the top bar", () => {
  function routesWithWork(state, fields = {}) {
    const routes = sprintRoutes();
    const payload = workspacePayload();
    payload.projects[0].work = work(state, fields);
    routes["GET /api/v1/workspace"] = payload;
    return routes;
  }

  it("holds Pause and Stop while a step runs, for the active sprint", async () => {
    const routes = routesWithWork("working", { task_key: "FOR-13", step: "develop", unfinished: 3, step_running: true });
    routes["POST /api/v1/sprints/sprint-56/pause"] = { task_keys: ["FOR-13"] };
    routes["POST /api/v1/sprints/sprint-56/stop"] = { task_keys: ["FOR-13"] };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    const trigger = await screen.findByRole("button", { name: /^Work: Working · FOR-13 Develop/ });
    fireEvent.click(trigger);
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Pause", "Stop"]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Pause" }));
    await waitFor(() => expect(calls(fetchImpl, "POST", "/api/v1/sprints/sprint-56/pause")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: /^Work: / }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Stop" }));
    await waitFor(() => expect(calls(fetchImpl, "POST", "/api/v1/sprints/sprint-56/stop")).toHaveLength(1));
  });

  it("offers nothing when no sprint is active", async () => {
    const routes = routesWithWork("not_started");
    routes["GET /api/v1/workspace"].projects[0].active_sprint = null;
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    expect(await screen.findByRole("button", { name: /^Work: Not started/ })).toBeDisabled();
  });

  it("holds Resume when everything is paused, and Start worker when none runs", async () => {
    await renderSprint(
      "/dashboard/sprints/sprint-56",
      routesWithWork("paused", { paused: 3, unfinished: 3, at: "2026-11-02T14:02:00Z", no_worker: false }),
    );
    fireEvent.click(await screen.findByRole("button", { name: /^Work: Paused/ }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Resume"]);
  });

  it("holds Unblock for a blocked sprint", async () => {
    await renderSprint(
      "/dashboard/sprints/sprint-56",
      routesWithWork("blocked", { scope: "sprint", reason: "design review", at: "2026-11-02T14:02:00Z", unfinished: 2 }),
    );
    fireEvent.click(await screen.findByRole("button", { name: /^Work: Blocked/ }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Unblock"]);
  });

  it("shows the API's sentence when an action is refused", async () => {
    const routes = routesWithWork("waiting", { unfinished: 2, no_worker: true });
    routes["POST /api/v1/projects/foreman/agent/start"] = reply(409, { error: "Another engine holds the lock.", code: "conflict" });
    await renderSprint("/dashboard/sprints/sprint-56", routes);
    fireEvent.click(await screen.findByRole("button", { name: /^Work: Waiting · no worker/ }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Pause", "Start worker"]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Start worker" }));
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

describe("the sprint's own holds (ADR-0043)", () => {
  it("shows its work in Details and Pause and Stop beside its title", async () => {
    const routes = sprintRoutes({
      sprint: sprintPayload({ work: work("working", { task_key: "FOR-13", step: "test", unfinished: 4, step_running: true }) }),
    });
    routes["POST /api/v1/sprints/sprint-56/pause"] = { task_keys: ["FOR-13"] };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    const details = screen.getByRole("region", { name: "Details" });
    expect(within(details).getByText("Working · FOR-13 Test")).toBeInTheDocument();
    const actions = document.querySelector(".sprint__actions");
    expect([...actions.querySelectorAll(":scope > .hold-controls > button")].map((button) => button.textContent)).toEqual([
      "Pause",
      "Stop",
    ]);
    fireEvent.click(within(actions).getByRole("button", { name: "Pause" }));
    expect(await screen.findByText("Paused FOR-13.")).toBeInTheDocument();
    expect(calls(fetchImpl, "POST", "/api/v1/sprints/sprint-56/pause")).toHaveLength(1);
  });

  it("is blocked from More, with a reason, and unblocked beside its title", async () => {
    const routes = sprintRoutes({ sprint: sprintPayload({ work: work("waiting", { unfinished: 4 }) }) });
    routes["POST /api/v1/sprints/sprint-56/block"] = { block: { reason: "design review" } };
    const { fetchImpl } = await renderSprint("/dashboard/sprints/sprint-56", routes);
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Block sprint" }));
    const dialog = screen.getByRole("dialog", { name: "Block this sprint" });
    expect(dialog).toHaveTextContent("the next sprint does not start");
    fireEvent.change(within(dialog).getByLabelText("Why it is blocked"), { target: { value: "design review" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Block sprint" }));
    await waitFor(() => expect(calls(fetchImpl, "POST", "/api/v1/sprints/sprint-56/block")[0].body).toEqual({ reason: "design review" }));

    const blocked = sprintRoutes({
      sprint: sprintPayload({
        block: { scope: "sprint", reason: "design review", by: "ana", at: "2026-11-02T14:02:00Z" },
        work: work("blocked", { scope: "sprint", reason: "design review", by: "ana", at: "2026-11-02T14:02:00Z", unfinished: 4 }),
      }),
    });
    blocked["POST /api/v1/sprints/sprint-56/unblock"] = { unblocked: { reason: "design review" } };
    cleanupApp();
    const second = await renderSprint("/dashboard/sprints/sprint-56", blocked);
    const actions = document.querySelector(".sprint__actions");
    fireEvent.click(within(actions).getByRole("button", { name: "Unblock" }));
    await waitFor(() => expect(calls(second.fetchImpl, "POST", "/api/v1/sprints/sprint-56/unblock")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(screen.queryByRole("menuitem", { name: "Block sprint" })).toBeNull();
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
