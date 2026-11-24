import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp, reply } from "../../testing/fakeApi";
import {
  ACTIVE,
  finishedUrl,
  FINISHED,
  milestonesUrl,
  PLANNED,
  PROJECT_NEEDS_YOU_URL,
  projectRoutes,
  QUEUE_URL,
  sprint,
} from "../../testing/projectFixture";
import { engine, milestone, on, ORDER_ITEM, UNBLOCK_ITEM, workspacePayload } from "../../testing/workspaceFixture";

// An activity row says the day and the clock time; the clock depends on the
// machine's time zone, so rows are compared without it.
const CLOCK = /, \d{2}:\d{2}/;


function withEngine(routes, state, task = null) {
  const payload = workspacePayload();
  payload.projects[0].engine = engine(state, task);
  routes["GET /api/v1/workspace"] = payload;
  return routes;
}

function engineSection() {
  return screen.getByRole("region", { name: "Engine" });
}

function calls(fetchImpl, method, url) {
  return fetchImpl.calls.filter((call) => call.method === method && call.url === url);
}

async function renderProject(path = "/dashboard/projects/foreman", routes = projectRoutes()) {
  const fetchImpl = createFakeFetch(routes);
  const utils = renderApp(path, fetchImpl);
  await screen.findByRole("heading", { level: 1, name: "Foreman" });
  return { ...utils, fetchImpl };
}

describe("the project page head", () => {
  it.each([
    ["/dashboard/projects/foreman", "Sprints"],
    ["/dashboard/projects/foreman/activity", "Activity"],
  ])("is the same above the tabs at %s", async (path, currentTab) => {
    await renderProject(path);
    expect(document.querySelector(".facts")).toHaveTextContent("/srv/foreman · main · development workflow");
    expect(screen.getByRole("link", { name: "Project settings" })).toHaveAttribute("href", "/dashboard/projects/foreman/settings");
    // Other pages of the project are buttons at the top right, never tabs.
    const pages = screen.getByRole("navigation", { name: "Project pages" });
    const backlog = within(pages).getByRole("link", { name: "Backlog 4" });
    expect(backlog).toHaveAttribute("href", "/dashboard/projects/foreman/backlog");
    expect(backlog).toHaveClass("button");

    expect(within(engineSection()).getByText("Running")).toBeInTheDocument();
    expect(within(engineSection()).getByText(/Working on/)).toHaveTextContent("Working on FOR-13, develop.");
    expect(within(engineSection()).getByRole("link", { name: "FOR-13" })).toHaveAttribute("href", "/dashboard/tasks/task-x");

    const needsYou = screen.getByRole("region", { name: /Needs you/ });
    expect(await within(needsYou).findByText("FOR-14")).toBeInTheDocument();
    // One project: no project column.
    expect(within(needsYou).queryByText("Foreman")).toBeNull();

    const tabs = screen.getByRole("navigation", { name: "Project" });
    expect(within(tabs).getAllByRole("link").map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
      ["Sprints 2", "/dashboard/projects/foreman"],
      ["Activity", "/dashboard/projects/foreman/activity"],
    ]);
    expect(within(tabs).getByRole("link", { name: currentTab === "Sprints" ? "Sprints 2" : currentTab })).toHaveAttribute("aria-current", "page");
    expect(document.title).toBe(`Project, ${currentTab} · Foreman`);
  });

  it("says when there is no such project", async () => {
    renderApp("/dashboard/projects/nope", createFakeFetch(projectRoutes()));
    expect(await screen.findByRole("heading", { name: "There is no project nope" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the workspace" })).toHaveAttribute("href", "/dashboard");
  });
});

describe("the engine row", () => {
  it("says the active sprint has no tasks when the engine runs with nothing to pick up", async () => {
    const routes = projectRoutes();
    const payload = workspacePayload();
    payload.projects[0].engine = engine("running", null);
    payload.projects[0].active_sprint.task_counts = { triage: 0, todo: 0, in_progress: 0, blocked: 0, done: 0, cancelled: 0 };
    routes["GET /api/v1/workspace"] = payload;
    await renderProject("/dashboard/projects/foreman", routes);
    expect(within(engineSection()).getByText(/the active sprint has no tasks/)).toBeInTheDocument();
  });

  it("says to activate a sprint when the engine runs with none active", async () => {
    const routes = projectRoutes();
    const payload = structuredClone(routes["GET /api/v1/workspace"]);
    payload.projects[0].active_sprint = null;
    payload.projects[0].engine = { ...payload.projects[0].engine, state: "running", task_id: null };
    routes["GET /api/v1/workspace"] = payload;
    await renderProject("/dashboard/projects/foreman", routes);
    expect(await screen.findByText("Nothing to work on: no sprint is active. Activate one under Sprints.")).toBeInTheDocument();
  });

  it("offers Pause and Stop while running, and sends them to the engine endpoints", async () => {
    const routes = projectRoutes();
    routes["POST /api/v1/projects/foreman/agent/stop"] = { command: { command: "pause", status: "pending" } };
    routes["POST /api/v1/projects/foreman/engine/commands"] = { command: { command: "shutdown", status: "pending" } };
    const { fetchImpl } = await renderProject("/dashboard/projects/foreman", routes);
    const row = engineSection();
    expect(within(row).getByRole("button", { name: "Start" })).toBeDisabled();
    expect(within(row).getByRole("button", { name: "Pause" })).toBeEnabled();
    expect(within(row).getByRole("button", { name: "Stop" })).toBeEnabled();

    fireEvent.click(within(row).getByRole("button", { name: "Pause" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/^Pause requested\./);
    expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/agent/stop")).toHaveLength(1);
    // The head reloads to show what the engine does next.
    await waitFor(() => expect(calls(fetchImpl, "GET", "/api/v1/workspace").length).toBeGreaterThanOrEqual(3));

    fireEvent.click(within(row).getByRole("button", { name: "Stop" }));
    expect(await screen.findByText(/^Stop requested\./)).toBeInTheDocument();
    expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/engine/commands").map((call) => call.body)).toEqual([
      { command: "shutdown" },
    ]);
  });

  it("offers only Start when not running, and shows a refused start's sentence", async () => {
    const routes = withEngine(projectRoutes(), "not_running");
    routes["POST /api/v1/projects/foreman/agent/start"] = reply(400, {
      error: "No active or planned sprint. Add a sprint to the queue before running.",
      code: "invalid_request",
    });
    const { fetchImpl } = await renderProject("/dashboard/projects/foreman", routes);
    const row = engineSection();
    expect(within(row).getByText("Not running")).toBeInTheDocument();
    expect(
      within(row).getByText("Nothing is being worked on."),
    ).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Pause" })).toBeDisabled();
    expect(within(row).getByRole("button", { name: "Stop" })).toBeDisabled();

    fireEvent.click(within(row).getByRole("button", { name: "Start" }));
    expect(await within(row).findByRole("alert")).toHaveTextContent(
      "No active or planned sprint. Add a sprint to the queue before running.",
    );
    expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/agent/start")).toHaveLength(1);
  });

  it("offers Resume in place of Pause while paused", async () => {
    const routes = withEngine(projectRoutes(), "paused", { id: "task-x", task_key: "FOR-13", title: "x", step: "develop" });
    routes["POST /api/v1/projects/foreman/agent/start"] = { started: true };
    const { fetchImpl } = await renderProject("/dashboard/projects/foreman", routes);
    const row = engineSection();
    expect(within(row).getByText("Paused")).toBeInTheDocument();
    expect(within(row).getByText(/^Paused\. Nothing new starts/)).toHaveTextContent(
      "Paused. Nothing new starts until it is resumed; FOR-13 resumes from develop.",
    );
    expect(within(row).queryByRole("button", { name: "Pause" })).toBeNull();
    expect(within(row).getByRole("button", { name: "Start" })).toBeDisabled();
    expect(within(row).getByRole("button", { name: "Stop" })).toBeEnabled();
    fireEvent.click(within(row).getByRole("button", { name: "Resume" }));
    expect(await screen.findByText(/^Resume requested\./)).toBeInTheDocument();
    expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/agent/start")).toHaveLength(1);
  });

  it("shows a refused stop's sentence", async () => {
    const routes = projectRoutes();
    routes["POST /api/v1/projects/foreman/engine/commands"] = reply(400, {
      error: "The engine for foreman is not running, so there is nothing to stop.",
      code: "invalid_request",
    });
    await renderProject("/dashboard/projects/foreman", routes);
    fireEvent.click(within(engineSection()).getByRole("button", { name: "Stop" }));
    expect(await within(engineSection()).findByRole("alert")).toHaveTextContent(
      "The engine for foreman is not running, so there is nothing to stop.",
    );
  });
});

describe("Needs you on the project page", () => {
  it("caps at five with Show all, which loads the rest from the server", async () => {
    const items = Array.from({ length: 8 }, (_, index) => ({
      ...UNBLOCK_ITEM,
      task_id: `t${index}`,
      task_key: `FOR-${200 + index}`,
    }));
    const routes = projectRoutes();
    routes[PROJECT_NEEDS_YOU_URL] = { items: items.slice(0, 5), total: 8 };
    routes["GET /api/v1/projects/foreman/needs-you?limit=3&offset=5"] = { items: items.slice(5), total: 8 };
    await renderProject("/dashboard/projects/foreman", routes);
    const needsYou = screen.getByRole("region", { name: /Needs you/ });
    expect(await within(needsYou).findByText("FOR-204")).toBeInTheDocument();
    expect(within(needsYou).getByRole("heading", { name: /Needs you\s*8/ })).toBeInTheDocument();
    expect(within(needsYou).queryByText("FOR-205")).toBeNull();
    fireEvent.click(within(needsYou).getByRole("button", { name: "Show all 8" }));
    expect(await within(needsYou).findByText("FOR-207")).toBeInTheDocument();
  });

  it("unblocks a blocked task from its row, and says a refusal", async () => {
    const routes = projectRoutes();
    let refuse = true;
    routes["POST /api/v1/tasks/task-stuck/unblock"] = () => {
      if (refuse) return reply(400, { error: "Task task-stuck is not blocked", code: "invalid_request" });
      routes[PROJECT_NEEDS_YOU_URL] = { items: [], total: 0 };
      return { id: "task-stuck", status: "todo" };
    };
    const { fetchImpl } = await renderProject("/dashboard/projects/foreman", routes);
    const needsYou = screen.getByRole("region", { name: /Needs you/ });
    const row = (await within(needsYou).findByText("FOR-15")).closest("tr");
    expect(row).toHaveTextContent("Tests failed three times · at Test");
    fireEvent.click(within(row).getByRole("button", { name: "Unblock FOR-15" }));
    expect(await within(needsYou).findByRole("alert")).toHaveTextContent("Task task-stuck is not blocked.");
    refuse = false;
    fireEvent.click(within(row).getByRole("button", { name: "Unblock FOR-15" }));
    await waitFor(() => expect(within(needsYou).queryByText("FOR-15")).toBeNull());
    expect(screen.getByRole("status")).toHaveTextContent("Unblocked FOR-15. It is back in the queue.");
    // Said in the toast, not above the box.
    expect(within(needsYou).queryByRole("status")).toBeNull();
    const sent = calls(fetchImpl, "POST", "/api/v1/tasks/task-stuck/unblock");
    expect(sent).toHaveLength(2);
    expect(sent[1].body).toEqual({ note: null });
  });

  it("lists a sprint ready to finish, and finishes it from its row", async () => {
    // Owner, 2026-11-24: the sprint page said "Ready to finish" and nothing led there.
    const routes = projectRoutes();
    const item = {
      kind: "finish_sprint",
      project_id: "foreman",
      project_name: "Foreman",
      sprint_id: "sprint-62",
      sprint_title: "Sprint 62: finish what's there",
      task_id: null,
      task_key: null,
      task_title: null,
      since: "2026-11-24T20:29:46Z",
      task_counts: { done: 10, cancelled: 0 },
    };
    routes[PROJECT_NEEDS_YOU_URL] = { items: [item], total: 1 };
    routes["PATCH /api/v1/sprints/sprint-62"] = () => {
      routes[PROJECT_NEEDS_YOU_URL] = { items: [], total: 0 };
      return { id: "sprint-62", status: "completed" };
    };
    const { fetchImpl } = await renderProject("/dashboard/projects/foreman", routes);
    const needsYou = screen.getByRole("region", { name: /Needs you/ });
    const row = (await within(needsYou).findByText("Sprint 62: finish what's there")).closest("tr");
    expect(row).toHaveTextContent("Finish sprint");
    expect(row).toHaveTextContent("10 done");
    expect(within(row).getByRole("link", { name: "Sprint 62: finish what's there" })).toHaveAttribute(
      "href",
      "/dashboard/sprints/sprint-62",
    );
    fireEvent.click(within(row).getByRole("button", { name: "Finish Sprint 62: finish what's there" }));
    await waitFor(() => expect(within(needsYou).queryByText("Sprint 62: finish what's there")).toBeNull());
    expect(screen.getByRole("status")).toHaveTextContent("Finished Sprint 62: finish what's there.");
    expect(calls(fetchImpl, "PATCH", "/api/v1/sprints/sprint-62")[0].body).toEqual({ status: "completed" });
  });

  it("a blocked task with no reason recorded says so", async () => {
    const routes = projectRoutes();
    routes[PROJECT_NEEDS_YOU_URL] = { items: [{ ...UNBLOCK_ITEM, blocked: { reason: null, step: null } }], total: 1 };
    await renderProject("/dashboard/projects/foreman", routes);
    const needsYou = screen.getByRole("region", { name: /Needs you/ });
    expect((await within(needsYou).findByText("FOR-15")).closest("tr")).toHaveTextContent("No reason recorded");
  });

  it("approves a merge and reloads", async () => {
    const routes = projectRoutes();
    routes["POST /api/v1/tasks/task-merge/approve"] = () => {
      routes[PROJECT_NEEDS_YOU_URL] = { items: [UNBLOCK_ITEM], total: 1 };
      return { status: "approved", next_step: "merge", engine_resident: true, message: "Decision recorded." };
    };
    const { fetchImpl } = await renderProject("/dashboard/projects/foreman", routes);
    const needsYou = screen.getByRole("region", { name: /Needs you/ });
    const unblock = (await within(needsYou).findByText("FOR-15")).closest("tr");
    expect(within(unblock).getByRole("link", { name: UNBLOCK_ITEM.task_title })).toHaveAttribute(
      "href",
      "/dashboard/tasks/task-stuck",
    );

    const approve = within(needsYou).getByRole("button", { name: "Approve FOR-14" });
    expect(approve).toHaveClass("button--gold-outline");
    fireEvent.click(approve);
    await waitFor(() => expect(within(needsYou).queryByText("FOR-14")).toBeNull());
    expect(calls(fetchImpl, "POST", "/api/v1/tasks/task-merge/approve")).toHaveLength(1);
    expect(calls(fetchImpl, "GET", PROJECT_NEEDS_YOU_URL.slice(4))).toHaveLength(2);
    expect(screen.getByRole("status")).toHaveTextContent("Approved FOR-14. Foreman goes on with Merge.");
    expect(within(needsYou).queryByRole("status")).toBeNull();
  });
});

describe("a proposed sprint order", () => {
  it("is listed with its proposal and settled by accepting or rejecting it", async () => {
    for (const [name, resolution] of [["Accept", "accepted"], ["Reject", "rejected"]]) {
      cleanup();
      const routes = projectRoutes();
      routes[PROJECT_NEEDS_YOU_URL] = { items: [ORDER_ITEM], total: 1 };
      routes["PATCH /api/v1/gates/gate-1"] = () => {
        routes[PROJECT_NEEDS_YOU_URL] = { items: [], total: 0 };
        return { id: "gate-1", status: resolution };
      };
      const { fetchImpl } = await renderProject("/dashboard/projects/foreman", routes);
      const needsYou = screen.getByRole("region", { name: /Needs you/ });
      const row = (await within(needsYou).findByText("Settle sprint order")).closest("tr");
      expect(within(row).getByRole("link", { name: ORDER_ITEM.gate.conflict_description })).toHaveAttribute(
        "href",
        "/dashboard/sprints/sprint-56",
      );
      expect(
        within(row).getByText(
          "Proposed: Sprint 56: engine truthfulness → Sprint 57: panels · Schema first.",
        ),
      ).toBeInTheDocument();

      fireEvent.click(within(row).getByRole("button", { name: `${name} the proposed sprint order` }));
      await waitFor(() => expect(within(needsYou).queryByText("Settle sprint order")).toBeNull());
      const sent = calls(fetchImpl, "PATCH", "/api/v1/gates/gate-1");
      expect(sent).toHaveLength(1);
      expect(sent[0].body).toEqual({ resolution });
      expect(screen.getByRole("status")).toHaveTextContent(
        name === "Accept" ? "Sprint order accepted" : "Sprint order rejected",
      );
    }
  });
});

describe("the Sprints tab", () => {
  it("shows the queue only: active first, then planned, one line each with counts, dates and spend", async () => {
    const { fetchImpl } = await renderProject();
    const queue = await screen.findByRole("table", { name: "Sprint queue" });
    const rows = within(queue).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Active")).toBeInTheDocument();
    expect(within(rows[0]).getByRole("link", { name: ACTIVE.title })).toHaveAttribute("href", "/dashboard/sprints/sprint-56");
    // The goal is on the sprint's own page, not under the title in the list.
    expect(within(rows[0]).queryByText(ACTIVE.goal)).toBeNull();
    expect(rows[0]).toHaveTextContent("3 need you · 1 done");
    // What waits for a user is gold wherever the counts appear.
    expect(within(rows[0]).getByText("3 need you")).toHaveClass("attention");
    expect(within(rows[0]).getByText("since 11 Nov")).toBeInTheDocument();
    expect(within(rows[0]).getByText("$1.31")).toHaveClass("mono");
    expect(within(rows[1]).getByText("Planned")).toBeInTheDocument();
    expect(within(rows[1]).getByRole("link", { name: PLANNED.title })).toBeInTheDocument();
    expect(within(queue).queryByText(FINISHED[0].title)).toBeNull();
    expect(calls(fetchImpl, "GET", QUEUE_URL.slice(4))).toHaveLength(1);
  });

  it("shows only the active sprint when nothing is planned, with no placeholder line", async () => {
    await renderProject("/dashboard/projects/foreman", projectRoutes({ queue: [ACTIVE] }));
    expect(await screen.findByRole("link", { name: ACTIVE.title })).toBeInTheDocument();
    expect(screen.queryByText(/Foreman stops until a sprint is planned/)).toBeNull();
    expect(screen.queryByText("Planned")).toBeNull();
  });

  it("caps planned sprints at five with a way to see the rest", async () => {
    const planned = Array.from({ length: 7 }, (_, index) => sprint(`p${index}`, `Planned ${index}`, "planned"));
    await renderProject("/dashboard/projects/foreman", projectRoutes({ queue: [ACTIVE, ...planned] }));
    await screen.findByText("Planned 4");
    expect(screen.queryByText("Planned 5")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show all 7 planned" }));
    expect(screen.getByText("Planned 6")).toBeInTheDocument();
  });

  it("keeps finished sprints behind a closed line that pages and filters on the server", async () => {
    const routes = projectRoutes();
    routes[finishedUrl({ q: "55" })] = { sprints: [FINISHED[0]], total: 1 };
    routes[finishedUrl({ q: "nothing" })] = { sprints: [], total: 0 };
    const { fetchImpl } = await renderProject("/dashboard/projects/foreman", routes);

    const line = await screen.findByRole("button", { name: /^Finished 12/ });
    expect(line).toHaveTextContent("Finished 12 latest: Sprint 55, 28 Oct");
    expect(line).toHaveAttribute("aria-expanded", "false");
    expect(calls(fetchImpl, "GET", finishedUrl().slice(4))).toHaveLength(0);

    fireEvent.click(line);
    const table = await screen.findByRole("table", { name: "Finished sprints" });
    expect(within(table).getAllByRole("row")).toHaveLength(11);
    expect(within(table).getByRole("link", { name: FINISHED[0].title })).toHaveAttribute("href", "/dashboard/sprints/sprint-55");
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("1 done28 Oct$0.55");
    expect(within(within(table).getAllByRole("row")[1]).getByText("$0.55")).toHaveClass("mono");
    expect(screen.getByText("Showing 10 of 12, newest first")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show 2 more" }));
    await waitFor(() => expect(within(table).getAllByRole("row")).toHaveLength(13));
    expect(screen.getByText("Showing all 12, newest first")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Show .* more/ })).toBeNull();
    expect(calls(fetchImpl, "GET", finishedUrl({ offset: 10 }).slice(4))).toHaveLength(1);

    const filter = screen.getByRole("searchbox", { name: "Filter finished sprints" });
    fireEvent.change(filter, { target: { value: "55" } });
    await waitFor(() =>
      expect(within(screen.getByRole("table", { name: "Finished sprints" })).getAllByRole("row")).toHaveLength(2),
    );
    expect(calls(fetchImpl, "GET", finishedUrl({ q: "55" }).slice(4))).toHaveLength(1);

    fireEvent.change(filter, { target: { value: "nothing" } });
    expect(await screen.findByText("No finished sprint matches “nothing”.")).toBeInTheDocument();
  });

  it("has two headings of one kind: Active and planned, open, and Finished, folded until opened", async () => {
    await renderProject();
    const open = await screen.findByRole("heading", { level: 2, name: "Active and planned" });
    const fold = await screen.findByRole("button", { name: /^Finished 12/ });
    const folded = fold.closest("h2");
    expect(folded).toHaveClass("section-heading__title");
    expect(open).toHaveClass("section-heading__title");
    expect(fold).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("table", { name: "Finished sprints" })).toBeNull();
    fireEvent.click(fold);
    expect(fold).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("table", { name: "Finished sprints" })).toBeInTheDocument();
    fireEvent.click(fold);
    expect(screen.queryByRole("table", { name: "Finished sprints" })).toBeNull();
  });

  it("puts New sprint on the tab row, only while Sprints is open", async () => {
    await renderProject();
    const tabs = (await screen.findByRole("navigation", { name: "Project" })).closest(".tabs");
    expect(within(tabs).getByRole("button", { name: "New sprint" })).toBeInTheDocument();
    expect(within(tabs).queryByRole("group", { name: "Show" })).toBeNull();
    expect(screen.getAllByRole("button", { name: "New sprint" })).toHaveLength(1);
  });

  it("counts the active and planned sprints on its tab", async () => {
    await renderProject();
    expect(await screen.findByRole("link", { name: "Sprints 2" })).toBeInTheDocument();
  });

  it("says so when no sprint has finished", async () => {
    await renderProject("/dashboard/projects/foreman", projectRoutes({ finished: [] }));
    expect(await screen.findByText("No sprint has finished yet.")).toBeInTheDocument();
  });

  it("creates a sprint through a keyboard-operable dialog", async () => {
    const routes = projectRoutes();
    routes["POST /api/v1/projects/foreman/sprints"] = () => {
      const created = sprint("sprint-59", "Sprint 59: more", "planned", { goal: "It works." });
      routes[QUEUE_URL] = { sprints: [ACTIVE, PLANNED, created], total: 3 };
      return created;
    };
    const { fetchImpl } = await renderProject("/dashboard/projects/foreman", routes);
    const opener = screen.getByRole("button", { name: "New sprint" });

    opener.focus();
    fireEvent.click(opener);
    let dialog = screen.getByRole("dialog", { name: "New sprint" });
    expect(within(dialog).getByRole("textbox", { name: "Title" })).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();

    fireEvent.click(opener);
    dialog = screen.getByRole("dialog", { name: "New sprint" });
    // Focus stays inside: Tab from the last control returns to the first.
    const create = within(dialog).getByRole("button", { name: "Create sprint" });
    create.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(within(dialog).getByRole("textbox", { name: "Title" })).toHaveFocus();

    fireEvent.click(create);
    expect(within(dialog).getByText("A sprint needs a title.")).toBeInTheDocument();
    expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/sprints")).toHaveLength(0);

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Title" }), { target: { value: "Sprint 59: more" } });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Goal" }), { target: { value: "It works." } });
    fireEvent.click(create);
    expect(await screen.findByRole("status")).toHaveTextContent("Sprint 59: more is planned, last in the queue.");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/sprints")[0].body).toEqual({
      title: "Sprint 59: more",
      goal: "It works.",
    });
    expect(await screen.findByRole("link", { name: "Sprint 59: more" })).toBeInTheDocument();
  });

  it("keeps the dialog open with the API's sentence when creating fails", async () => {
    const routes = projectRoutes();
    routes["POST /api/v1/projects/foreman/sprints"] = reply(400, { error: "Sprint title is required.", code: "invalid_request" });
    await renderProject("/dashboard/projects/foreman", routes);
    fireEvent.click(screen.getByRole("button", { name: "New sprint" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Title" }), { target: { value: "x" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create sprint" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Sprint title is required.");
  });
});

describe("the Activity tab", () => {
  const sprintKinds = ["sprint_started", "sprint_finished", "plan_confirmed"];
  const cells = (row) => within(row).getAllByRole("cell").map((cell) => cell.textContent.replace(CLOCK, ""));

  it("is one line per row: when, the sprint or the engine, what happened, who", async () => {
    const routes = projectRoutes();
    routes[milestonesUrl()] = {
      milestones: [
        milestone("engine_lost", {}),
        milestone("engine_stopped", { actor: "ana" }),
        milestone("sprint_finished", { sprint_id: "sprint-55", sprint_title: "Sprint 55: baseline", merged_count: 3 }),
        milestone("plan_confirmed", { sprint_id: "sprint-57", sprint_title: "Sprint 57: structure", actor: "masis", detail: "Eight tasks reach the goal." }),
        milestone("sprint_started", { sprint_id: "sprint-54", sprint_title: "Sprint 54" }),
        // Started from the dashboard: Foreman recorded the channel, not a name.
        milestone("engine_started", { actor: "dashboard" }),
      ],
      total: 6,
    };
    await renderProject("/dashboard/projects/foreman/activity", routes);
    const table = await screen.findByRole("table", { name: "Activity" });
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "When",
      "About",
      "Title",
      "What happened",
      "By",
    ]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map(cells)).toEqual([
      ["11 Nov", "Engine", "", "Died", ""],
      ["11 Nov", "Engine", "", "Stopped", "ana"],
      ["11 Nov", "Sprint 55", "baseline", "Finished", ""],
      ["11 Nov", "Sprint 57", "structure", "Plan confirmed", "masis"],
      ["11 Nov", "Sprint 54", "", "Started", ""],
      ["11 Nov", "Engine", "", "Started", "a user"],
    ]);
    // Why is on hover, never under the row.
    expect(within(rows[2]).getByText("Finished")).toHaveAttribute("title", "3 tasks merged");
    expect(within(rows[3]).getByText("Plan confirmed")).toHaveAttribute("title", "Eight tasks reach the goal.");
    expect(within(rows[0]).getByText("Died")).toHaveClass("tone-failed");
    // A sprint's row leads to the sprint; the engine's leads nowhere.
    expect(rows[2]).toHaveClass("table__row--pickable");
    expect(rows[1]).not.toHaveClass("table__row--pickable");
    fireEvent.click(within(rows[2]).getByText("Finished"));
    expect(window.location.pathname).toBe("/dashboard/sprints/sprint-55");
  });

  it("says a finished sprint's tag on hover, and when it is not tagged", async () => {
    const routes = projectRoutes();
    routes[milestonesUrl()] = {
      milestones: [
        milestone("sprint_finished", {
          sprint_id: "sprint-56",
          sprint_title: "Sprint 56",
          merged_count: 2,
          checkpoint: { tag: null, sha: null, problem: "the repository has no commits" },
        }),
        milestone("sprint_finished", {
          sprint_id: "sprint-55",
          sprint_title: "Sprint 55",
          merged_count: 3,
          checkpoint: { tag: "checkpoint-20261111-sprint-55", sha: "6f79f4a0123456789", problem: null },
        }),
      ],
      total: 2,
    };
    await renderProject("/dashboard/projects/foreman/activity", routes);
    const table = await screen.findByRole("table", { name: "Activity" });
    const rows = within(table).getAllByRole("row").slice(1);
    const failed = within(rows[0]).getByText("Finished, not tagged");
    expect(failed).toHaveClass("tone-failed");
    expect(failed).toHaveAttribute("title", "2 tasks merged, not tagged: the repository has no commits");
    expect(within(rows[1]).getByText("Finished")).toHaveAttribute(
      "title",
      "3 tasks merged, tagged checkpoint-20261111-sprint-55 at 6f79f4a",
    );
  });

  it("shows the project's sprint and engine events newest first", async () => {
    await renderProject("/dashboard/projects/foreman/activity");
    const table = await screen.findByRole("table", { name: "Activity" });
    expect(within(table).getAllByRole("row").slice(1).map((row) => cells(row).slice(1, 5))).toEqual([
      ["Sprint 56", "engine truthfulness", "Started", ""],
      ["Engine", "", "Stopped", "ana"],
    ]);
    expect(within(table).getByRole("link", { name: "engine truthfulness" })).toHaveAttribute(
      "href",
      "/dashboard/sprints/sprint-56",
    );
    expect(screen.queryByRole("button", { name: "Earlier" })).toBeNull();
  });

  it("pages 25 at a time with Earlier", async () => {
    const all = Array.from({ length: 30 }, (_, index) =>
      milestone("engine_paused", { at: on(`10-${String(30 - index).padStart(2, "0")}`), actor: `person ${index}` }),
    );
    const routes = projectRoutes();
    routes[milestonesUrl()] = { milestones: all.slice(0, 25), total: 30 };
    routes[milestonesUrl({ offset: 25 })] = { milestones: all.slice(25), total: 30 };
    const { fetchImpl } = await renderProject("/dashboard/projects/foreman/activity", routes);
    const table = await screen.findByRole("table", { name: "Activity" });
    expect(within(table).getAllByRole("row")).toHaveLength(26);
    fireEvent.click(screen.getByRole("button", { name: "Earlier" }));
    await waitFor(() => expect(within(table).getAllByRole("row")).toHaveLength(31));
    expect(screen.getByText("person 29")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Earlier" })).toBeNull();
    expect(calls(fetchImpl, "GET", milestonesUrl({ offset: 25 }).slice(4))).toHaveLength(1);
  });

  it("filters by kind on the server", async () => {
    const routes = projectRoutes();
    routes[milestonesUrl({ kinds: sprintKinds })] = {
      milestones: [milestone("sprint_finished", { sprint_id: "sprint-55", sprint_title: "Sprint 55: baseline" })],
      total: 1,
    };
    routes[milestonesUrl({ kinds: ["engine_started", "engine_stopped", "engine_paused", "engine_resumed", "engine_lost"] })] = {
      milestones: [],
      total: 0,
    };
    const { fetchImpl } = await renderProject("/dashboard/projects/foreman/activity", routes);
    const filters = screen.getByRole("group", { name: "Show" });
    // The filter is on the tab row, and nothing is a heading row under it.
    expect(filters.closest(".tabs")).toContainElement(screen.getByRole("navigation", { name: "Project" }));
    expect(screen.queryByRole("heading", { level: 2, name: "Sprints and engine" })).toBeNull();
    expect(screen.queryByRole("button", { name: "New sprint" })).toBeNull();
    expect(within(filters).getAllByRole("button").map((button) => button.textContent)).toEqual(["All", "Sprints", "Engine"]);
    expect(within(filters).getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(within(filters).getByRole("button", { name: "Sprints" }));
    expect(await screen.findByText("baseline")).toBeInTheDocument();
    expect(within(filters).getByRole("button", { name: "Sprints" })).toHaveAttribute("aria-pressed", "true");
    expect(calls(fetchImpl, "GET", milestonesUrl({ kinds: sprintKinds }).slice(4))).toHaveLength(1);

    fireEvent.click(within(filters).getByRole("button", { name: "Engine" }));
    expect(await screen.findByText("The engine has not started yet.")).toBeInTheDocument();
  });
});

describe("the order of planned sprints", () => {
  const first = sprint("p0", "Planned first", "planned");
  const second = sprint("p1", "Planned second", "planned");

  it("moves a planned sprint earlier or later and reads the queue again", async () => {
    const routes = projectRoutes({ queue: [ACTIVE, first, second] });
    routes["POST /api/v1/sprints/p1/move"] = () => {
      routes[QUEUE_URL] = { sprints: [ACTIVE, second, first], total: 3 };
      return { id: "p1", order_index: 2, planned_order: ["p1", "p0"] };
    };
    const { fetchImpl } = await renderProject("/dashboard/projects/foreman", routes);
    await screen.findByText("Planned second");
    // The ends of the queue cannot move past it; the active sprint has no order to change.
    expect(screen.getByRole("button", { name: "Move Planned first earlier" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move Planned second later" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: `Move ${ACTIVE.title} later` })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Move Planned second earlier" }));
    await waitFor(() => expect(calls(fetchImpl, "POST", "/api/v1/sprints/p1/move")[0].body).toEqual({ direction: "up" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Move Planned second earlier" })).toBeDisabled());
  });

  it("offers no order controls with one planned sprint, and shows a refusal as a sentence", async () => {
    await renderProject();
    await screen.findByText(PLANNED.title);
    expect(screen.queryByRole("columnheader", { name: "Order" })).toBeNull();
    cleanup();

    const routes = projectRoutes({ queue: [ACTIVE, first, second] });
    routes["POST /api/v1/sprints/p0/move"] = reply(400, { error: "Sprint 'Planned first' is active; only a planned sprint can be moved in the queue.", code: "invalid_request" });
    await renderProject("/dashboard/projects/foreman", routes);
    fireEvent.click(await screen.findByRole("button", { name: "Move Planned first later" }));
    expect(await screen.findByText(/only a planned sprint can be moved/)).toHaveAttribute("role", "alert");
  });
});

describe("requests in Needs you", () => {
  it("are one line that counts them and leads to the backlog", async () => {
    const routes = projectRoutes();
    routes[PROJECT_NEEDS_YOU_URL] = {
      items: [
        {
          kind: "answer_requests",
          project_id: "foreman",
          project_name: "Foreman",
          sprint_id: "foreman-backlog",
          sprint_title: "Backlog",
          task_id: null,
          task_key: null,
          task_title: null,
          since: "2026-11-16T10:00:00Z",
          count: 3,
        },
      ],
      total: 1,
    };
    renderApp("/dashboard/projects/foreman", createFakeFetch(routes));
    const link = await screen.findByRole("link", { name: "3 requests from agents and other systems" });
    expect(link).toHaveAttribute("href", "/dashboard/projects/foreman/backlog");
    expect(link.closest("tr")).toHaveTextContent("Answer requests");
  });
});

describe("the Needs you surface", () => {
  it("runs the line between rows from edge to edge: the room at the sides is the cells'", () => {
    const css = readFileSync(join(process.cwd(), "src", "styles", "lists.css"), "utf8");
    expect(css).toMatch(/\.surface\.needs-you__surface\s*\{\s*padding: 0;[^}]*overflow: hidden;/);
    expect(css).toMatch(/\.needs-you \.table td:first-child\s*\{\s*padding-left: var\(--space-4\);/);
    expect(css).toMatch(/\.needs-you \.table td:last-child\s*\{\s*padding-right: var\(--space-4\);/);
  });
});
