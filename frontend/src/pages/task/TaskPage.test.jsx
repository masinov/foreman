import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp, reply } from "../../testing/fakeApi";
import {
  BUILTINS_DIFF,
  CHANGES_URL,
  changesPayload,
  CHECKS_URL,
  checksPayload,
  COMMIT,
  diffPayload,
  diffUrl,
  outputPayload,
  outputUrl,
  post,
  run,
  runItem,
  RUNS_URL,
  TASK_ID,
  TASK_URL,
  taskDetail,
  taskRoutes,
} from "../../testing/taskFixture";
import { engine, on, workspacePayload } from "../../testing/workspaceFixture";
import { actionsFor } from "./TaskActions";

/** The More menu depends on the engine, which arrives with the workspace. */
const engineKnown = () => screen.findByRole("button", { name: /^Engine/ });

const TITLE = "Make the test step report what happened";
const BASE = `/dashboard/tasks/${TASK_ID}`;

async function renderTask(path = BASE, routes = taskRoutes()) {
  const fetchImpl = createFakeFetch(routes);
  const utils = renderApp(path, fetchImpl);
  await screen.findByRole("heading", { level: 1, name: TITLE });
  return { ...utils, fetchImpl };
}

function calls(fetchImpl, method, url) {
  return fetchImpl.calls.filter((call) => call.method === method && `${call.method} ${call.url}` === `${method} ${url}`);
}

const postCalls = (fetchImpl, action) => fetchImpl.calls.filter((call) => `${call.method} ${call.url}` === post(action));
const taskReads = (fetchImpl) => calls(fetchImpl, "GET", TASK_URL.slice(4)).length;

function decision() {
  return screen.queryByRole("region", { name: /\?$|^Blocked/ });
}

describe("the task page header", () => {
  it("stays in place when the tab changes: nothing above the tab is drawn or read again", async () => {
    const { fetchImpl } = await renderTask();
    const title = screen.getByRole("heading", { level: 1, name: TITLE });
    const before = taskReads(fetchImpl);
    for (const [tab, path] of [["Activity", `${BASE}/activity`], ["Checks", `${BASE}/checks`], ["Overview", BASE]]) {
      fireEvent.click(within(screen.getByRole("navigation", { name: "Task" })).getByRole("link", { name: tab }));
      await waitFor(() => expect(window.location.pathname).toBe(path));
      // The same element, not a new one that looks the same.
      expect(screen.getByRole("heading", { level: 1, name: TITLE })).toBe(title);
    }
    expect(taskReads(fetchImpl)).toBe(before);
  });


  it.each([BASE, `${BASE}/changes`, `${BASE}/checks`, `${BASE}/activity`])("is the same at %s", async (path) => {
    await renderTask(path);
    expect(await screen.findByText("FOR-14 · fix · foreman/for-14 · b232eb1 · +118 −7")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More" })).toHaveAttribute("aria-haspopup", "menu");
    const tabs = screen.getByRole("navigation", { name: "Task" });
    expect(within(tabs).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
      BASE,
      `${BASE}/changes`,
      `${BASE}/checks`,
      `${BASE}/activity`,
    ]);
    expect(within(tabs).getByRole("link", { current: "page" })).toHaveAttribute("href", path);
    // The tab is only its name; the figures are inside it.
    expect(within(tabs).getByRole("link", { name: /Changes/ })).toHaveTextContent(/^Changes$/);
  });

  it("puts the project, the sprint and the task key in the breadcrumb", async () => {
    await renderTask();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(await within(crumbs).findByRole("link", { name: /Foreman/ })).toHaveAttribute("href", "/dashboard/projects/foreman");
    expect(await within(crumbs).findByRole("link", { name: "Sprint 56: engine truthfulness" })).toHaveAttribute(
      "href",
      "/dashboard/sprints/sprint-56",
    );
    expect(await within(crumbs).findByText("FOR-14")).toHaveAttribute("aria-current", "page");
  });

  it("names the backlog in the breadcrumb for a task that is in it", async () => {
    await renderTask(BASE, taskRoutes({ task: taskDetail({ status: "todo", in_backlog: true, blocked_kind: null, awaiting_human_gate: false }) }));
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(await within(crumbs).findByRole("link", { name: "Backlog" })).toHaveAttribute("href", "/dashboard/projects/foreman/backlog");
  });

  it("says why a task cannot be shown", async () => {
    const routes = taskRoutes();
    routes[TASK_URL] = reply(404, { error: "Task not found: task-merge", code: "not_found" });
    renderApp(BASE, createFakeFetch(routes));
    expect(await screen.findByRole("heading", { name: "This task could not be shown" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Task not found: task-merge.");
  });

  it("edits the task through PATCH and reads it again", async () => {
    const routes = taskRoutes();
    routes[`PATCH /api/v1/tasks/${TASK_ID}`] = { ok: true };
    const { fetchImpl } = await renderTask(BASE, routes);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = screen.getByRole("dialog", { name: "Edit task" });
    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: "A sharper title" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(calls(fetchImpl, "PATCH", `/api/v1/tasks/${TASK_ID}`)[0].body).toEqual({
      title: "A sharper title",
      task_type: "fix",
      description: taskDetail().description,
      acceptance_criteria: taskDetail().acceptance_criteria,
      complexity: taskDetail().complexity ?? null,
      priority: taskDetail().priority ?? 0,
    });
    await waitFor(() => expect(taskReads(fetchImpl)).toBeGreaterThan(1));
  });

  it("changes a queued task's size, priority and what it waits for", async () => {
    const task = taskDetail({
      status: "todo",
      blocked_kind: null,
      awaiting_human_gate: false,
      workflow_current_step: null,
      complexity: null,
      priority: 0,
      depends_on_task_ids: [],
      dependencies: [],
    });
    const routes = taskRoutes({ task });
    routes[`PATCH /api/v1/tasks/${TASK_ID}`] = { ok: true };
    const { fetchImpl } = await renderTask(BASE, routes);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = screen.getByRole("dialog", { name: "Edit task" });
    fireEvent.change(within(dialog).getByLabelText("Size"), { target: { value: "large" } });
    fireEvent.change(within(dialog).getByLabelText("Priority"), { target: { value: "2" } });
    fireEvent.click(await within(dialog).findByRole("button", { name: "Make it wait for other tasks" }));
    const boxes = within(dialog).getAllByRole("checkbox");
    // The task itself is not offered, and finished tasks are not either.
    expect(within(dialog).queryByRole("checkbox", { name: new RegExp(task.title) })).toBeNull();
    fireEvent.click(boxes[0]);
    expect(within(dialog).getByRole("button", { name: "Waits for 1 task" })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const body = calls(fetchImpl, "PATCH", `/api/v1/tasks/${TASK_ID}`)[0].body;
    expect(body.complexity).toBe("large");
    expect(body.priority).toBe(2);
    expect(body.depends_on_task_ids).toHaveLength(1);
    expect(body.depends_on_task_ids[0]).not.toBe(TASK_ID);
  });

  it("does not offer what a started task waits for, and refuses a priority that is not a number", async () => {
    const routes = taskRoutes();
    routes[`PATCH /api/v1/tasks/${TASK_ID}`] = { ok: true };
    const { fetchImpl } = await renderTask(BASE, routes);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = screen.getByRole("dialog", { name: "Edit task" });
    expect(within(dialog).queryByRole("button", { name: /wait/i })).toBeNull();
    fireEvent.change(within(dialog).getByLabelText("Priority"), { target: { value: "soon" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText("A whole number. Lower runs first.")).toBeInTheDocument();
    expect(calls(fetchImpl, "PATCH", `/api/v1/tasks/${TASK_ID}`)).toHaveLength(0);
  });
});

describe("the decision", () => {
  it("asks to approve the merge with the facts, and approving calls approve and reloads", async () => {
    const routes = taskRoutes();
    routes[post("approve")] = { status: "approved", message: "Decision recorded. The engine continues from `merge`." };
    const { fetchImpl } = await renderTask(BASE, routes);
    const region = await screen.findByRole("region", { name: "Approve the merge into main?" });
    await waitFor(() => expect(region).toHaveTextContent("Tests passed in 1 min 54 s at b232eb1"));
    expect(region).toHaveTextContent("Review approved by sonnet-5-5, same commit");
    expect(region).toHaveTextContent("Branch is up to date with main");
    const before = taskReads(fetchImpl);
    const approve = within(region).getByRole("button", { name: "Approve merge" });
    expect(approve).toHaveClass("button--gold");
    fireEvent.click(approve);
    expect(await screen.findByText("Decision recorded. The engine continues from `merge`.")).toBeInTheDocument();
    expect(postCalls(fetchImpl, "approve")).toHaveLength(1);
    await waitFor(() => expect(taskReads(fetchImpl)).toBeGreaterThan(before));
  });

  it("sends back with guidance through deny, and needs the guidance", async () => {
    const routes = taskRoutes();
    routes[post("deny")] = { status: "denied", message: "Decision recorded." };
    const { fetchImpl } = await renderTask(BASE, routes);
    const region = await screen.findByRole("region", { name: "Approve the merge into main?" });
    fireEvent.click(within(region).getByRole("button", { name: "Send back" }));
    const dialog = screen.getByRole("dialog", { name: "Send back" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Send back" }));
    expect(within(dialog).getByText("Guidance for the agent is needed.")).toBeInTheDocument();
    expect(postCalls(fetchImpl, "deny")).toHaveLength(0);
    fireEvent.change(within(dialog).getByLabelText("Guidance for the agent"), { target: { value: "Count skipped tests." } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Send back" }));
    expect(await screen.findByText("Decision recorded.")).toBeInTheDocument();
    expect(postCalls(fetchImpl, "deny")[0].body).toEqual({ note: "Count skipped tests." });
  });

  it("shows a refusal as the API's sentence", async () => {
    const routes = taskRoutes();
    routes[post("approve")] = reply(409, { error: "Failed to approve: the task is not at a gate", code: "conflict" });
    await renderTask(BASE, routes);
    const region = await screen.findByRole("region", { name: "Approve the merge into main?" });
    fireEvent.click(within(region).getByRole("button", { name: "Approve merge" }));
    expect(await within(region).findByRole("alert")).toHaveTextContent("Failed to approve: the task is not at a gate.");
  });

  it("asks to approve a plan, and approving calls approve", async () => {
    const task = taskDetail({
      workflow_current_step: "plan_approval",
      gate_policy: "plan_approval",
      runs: [run("run-1", "plan", { outcome: "done", duration_ms: 12000 })],
    });
    const routes = taskRoutes({ task });
    routes[post("approve")] = { status: "approved", message: "Decision recorded." };
    const { fetchImpl } = await renderTask(BASE, routes);
    const region = await screen.findByRole("region", { name: "Approve this plan?" });
    expect(region).toHaveTextContent("Plan: done by sonnet-5-5 in 12 s");
    expect(within(region).getByRole("link", { name: "Read its output under Activity" })).toHaveAttribute("href", `${BASE}/activity`);
    fireEvent.click(within(region).getByRole("button", { name: "Approve plan" }));
    await screen.findByText("Decision recorded.");
    expect(postCalls(fetchImpl, "approve")).toHaveLength(1);
  });

  const request = (fields = {}) =>
    taskDetail({
      status: "triage",
      in_backlog: true,
      awaiting_human_gate: false,
      gate_policy: null,
      blocked_kind: null,
      workflow_current_step: null,
      source: { system: "github", external_ref: "#42", url: "https://example.test/42", reporter: "ana" },
      runs: [],
      ...fields,
    });
  const SPRINTS_URL = "GET /api/v1/projects/foreman/sprints?status=active&status=planned&order=queue";
  const PLAN = "/api/v1/projects/foreman/backlog/plan";

  function backlogTaskRoutes(task) {
    const routes = taskRoutes({ task });
    routes[SPRINTS_URL] = {
      sprints: [
        { id: "sprint-56", title: "Sprint 56: engine truthfulness", status: "active" },
        { id: "sprint-57", title: "Sprint 57: next", status: "planned" },
      ],
      total: 2,
    };
    return routes;
  }

  it("a backlog task is planned into a sprint from its own page, or declined with a reason", async () => {
    const task = request();
    const routes = backlogTaskRoutes(task);
    routes[`POST ${PLAN}`] = { sprint: { id: "sprint-57", title: "Sprint 57: next" }, created_sprint: false, task_ids: [TASK_ID] };
    routes[post("decline")] = task;
    const { fetchImpl } = await renderTask(BASE, routes);
    const region = await screen.findByRole("region", { name: "A request: plan it into a sprint?" });
    expect(region).toHaveTextContent("Filed by ana via github on 10 Nov");
    expect(within(region).getByRole("link", { name: "#42" })).toHaveAttribute("href", "https://example.test/42");
    // Where a user plans everything there is nothing to accept.
    expect(within(region).queryByRole("button", { name: /Accept/ })).toBeNull();

    const sprint = within(region).getByRole("combobox", { name: "Sprint to plan it into" });
    await within(sprint).findByRole("option", { name: "Sprint 57: next (planned)" });
    // The sprint that is running is the one offered first.
    expect(sprint).toHaveValue("sprint-56");
    fireEvent.change(sprint, { target: { value: "sprint-57" } });
    fireEvent.click(within(region).getByRole("button", { name: "Plan" }));
    expect(await screen.findByText("Planned into Sprint 57: next.")).toBeInTheDocument();
    expect(calls(fetchImpl, "POST", PLAN)[0].body).toEqual({ task_ids: [TASK_ID], sprint_id: "sprint-57" });

    fireEvent.click(within(region).getByRole("button", { name: "Decline" }));
    const dialog = screen.getByRole("dialog", { name: "Decline this task" });
    fireEvent.change(within(dialog).getByLabelText("Why it is declined"), { target: { value: "Out of scope." } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Decline" }));
    expect(await screen.findByText("Declined.")).toBeInTheDocument();
    expect(postCalls(fetchImpl, "decline")[0].body).toEqual({ reason: "Out of scope." });
  });

  it("a request can be accepted where Foreman starts backlog work on its own", async () => {
    const task = request({ foreman_starts_backlog_work: true });
    const routes = backlogTaskRoutes(task);
    routes[post("accept")] = task;
    const { fetchImpl } = await renderTask(BASE, routes);
    const region = await screen.findByRole("region", { name: "A request: plan it into a sprint?" });
    fireEvent.click(within(region).getByRole("button", { name: "Accept: Foreman may start it" }));
    expect(await screen.findByText("Accepted. Foreman may start it.")).toBeInTheDocument();
    expect(postCalls(fetchImpl, "accept")).toHaveLength(1);
  });

  it("backlog work that is not a request is planned the same way, with no Accept", async () => {
    const task = request({ status: "todo", foreman_starts_backlog_work: true, source: null });
    await renderTask(BASE, backlogTaskRoutes(task));
    const region = await screen.findByRole("region", { name: "Plan this into a sprint?" });
    expect(within(region).queryByRole("button", { name: /Accept/ })).toBeNull();
    expect(within(region).getByRole("button", { name: "Plan" })).toBeInTheDocument();
  });

  it("a request another system filed straight into a sprint is still accepted there", async () => {
    const task = request({ in_backlog: false });
    const routes = taskRoutes({ task });
    routes[post("accept")] = task;
    const { fetchImpl } = await renderTask(BASE, routes);
    const region = await screen.findByRole("region", { name: "Accept this task?" });
    fireEvent.click(within(region).getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(postCalls(fetchImpl, "accept")).toHaveLength(1));
  });

  it("says why a task is blocked; Unblock and Send back call unblock", async () => {
    const task = taskDetail({
      awaiting_human_gate: false,
      gate_policy: null,
      blocked_kind: "engine",
      workflow_current_step: "test",
      blocked_reason: "Tests failed three times.",
      runs: [run("run-1", "test", { outcome: "failed" })],
    });
    const routes = taskRoutes({ task });
    routes[post("unblock")] = task;
    const { fetchImpl } = await renderTask(BASE, routes);
    const region = await screen.findByRole("region", { name: "Blocked: Tests failed three times." });
    expect(region).toHaveTextContent("Stopped at Test");
    expect(region).toHaveTextContent("Last run: Test, failed by Foreman");
    fireEvent.click(within(region).getByRole("button", { name: "Unblock" }));
    expect(await screen.findByText("Unblocked. The task is back in the queue.")).toBeInTheDocument();
    expect(postCalls(fetchImpl, "unblock")[0].body).toEqual({ note: null });

    fireEvent.click(within(region).getByRole("button", { name: "Send back" }));
    const dialog = screen.getByRole("dialog", { name: "Send back with guidance" });
    fireEvent.change(within(dialog).getByLabelText("Guidance for the agent"), { target: { value: "Run the slow suite." } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Send back" }));
    expect(await screen.findByText("Unblocked with guidance. The task is back in the queue.")).toBeInTheDocument();
    expect(postCalls(fetchImpl, "unblock")[1].body).toEqual({ note: "Run the slow suite." });
  });

  it.each([
    ["running", { status: "in_progress", workflow_current_step: "develop" }],
    ["queued", { status: "todo", workflow_current_step: null }],
    ["done", { status: "done", workflow_current_step: "done" }],
  ])("is not there when the task is %s", async (_, fields) => {
    await renderTask(BASE, taskRoutes({ task: taskDetail({ awaiting_human_gate: false, gate_policy: null, blocked_kind: null, ...fields }) }));
    await screen.findByRole("heading", { name: "Steps" });
    expect(decision()).toBeNull();
    expect(document.querySelector(".surface")).toBeNull();
  });
});

describe("a task left part-way", () => {
  const stepWords = async (state, onIt) => {
    const routes = taskRoutes({ task: taskDetail({ status: "in_progress", workflow_current_step: "develop" }) });
    const workspace = workspacePayload();
    workspace.projects[0].engine = engine(state, onIt ? { id: TASK_ID, task_key: "FOR-14", title: "x", step: "develop" } : null);
    routes["GET /api/v1/workspace"] = workspace;
    const view = await renderTask(BASE, routes);
    await engineKnown();
    const row = within(await screen.findByRole("table", { name: "Steps" })).getByText("Develop").closest("tr");
    const words = row.querySelectorAll("td")[1].textContent;
    view.unmount();
    return words;
  };

  it("reads Running at its step only while the engine is on it", async () => {
    expect(await stepWords("running", true)).toBe("Running");
    expect(await stepWords("paused", true)).toBe("Paused here");
    expect(await stepWords("not_running", false)).toBe("Stopped here");
  });
});

describe("a task closed by hand", () => {
  it("says so in Details, with the reason", async () => {
    const task = taskDetail({
      status: "done",
      closed_by_hand: { reason: "Merged by hand in 96bee0d.", by: "alice", at: "2026-11-13T09:00:00Z" },
    });
    await renderTask(BASE, taskRoutes({ task }));
    const details = await screen.findByRole("region", { name: "Details" });
    expect(details).toHaveTextContent(/Marked done\s*By hand by alice on 13 Nov, not checked by Foreman\. Merged by hand in 96bee0d\./);
  });

  it("says nothing for a task the engine finished", async () => {
    await renderTask(BASE, taskRoutes({ task: taskDetail({ status: "done", closed_by_hand: null }) }));
    expect(await screen.findByRole("region", { name: "Details" })).not.toHaveTextContent("Marked done");
  });
});

describe("the task's actions beside its title", () => {
  function openMore() {
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    return screen.getByRole("menu", { name: "Task actions" });
  }

  /** The words of the buttons beside the title, in order, with the menu closed. */
  const inPlainSight = () =>
    [...document.querySelector(".task__actions").querySelectorAll("button")].map((button) => button.textContent);

  /** Press an action where it is: a button beside the title, else an item of More. */
  function choose(label) {
    const button = within(document.querySelector(".task__actions")).queryByRole("button", { name: label });
    if (button) fireEvent.click(button);
    else fireEvent.click(within(openMore()).getByRole("menuitem", { name: label }));
  }

  /** The task's routes with the project's engine in `state`, on this task or on none. */
  function withEngine(routes, state, onThisTask = true) {
    const workspace = workspacePayload();
    workspace.projects[0].engine = engine(state, onThisTask ? { id: TASK_ID, task_key: "FOR-14", title: "x", step: "develop" } : null);
    routes["GET /api/v1/workspace"] = workspace;
    return routes;
  }

  // What depends on the task's state, and closing it, are buttons; More holds what is rare.
  // A task the engine is running can be neither closed nor deleted: the API refuses both.
  it.each([
    ["running", { status: "in_progress", workflow_current_step: "develop" }, "running", ["Stop"], []],
    ["left part-way with no engine", { status: "in_progress", workflow_current_step: "merge" }, "not_running", ["Run next", "Close"], ["Delete"]],
    ["queued", { status: "todo" }, "not_running", ["Run next", "Close"], ["Block", "Split into smaller tasks", "Delete"]],
    ["blocked by the engine", { status: "blocked", blocked_kind: "engine" }, "not_running", ["Close"], ["Delete"]],
    ["at a gate", {}, "not_running", ["Close"], ["Delete"]],
    ["in the backlog", { status: "todo", in_backlog: true }, "not_running", [], ["Split into smaller tasks", "Decline", "Delete"]],
    ["done", { status: "done" }, "not_running", ["Reopen"], ["Delete"]],
    ["cancelled", { status: "cancelled" }, "not_running", ["Reopen"], ["Delete"]],
  ])("shows what exists for a task that is %s", async (_, fields, state, buttons, more) => {
    await renderTask(BASE, withEngine(taskRoutes({ task: taskDetail(fields) }), state, state === "running"));
    await engineKnown();
    await waitFor(() => expect(inPlainSight()).toEqual(["Edit", ...buttons, ...(more.length ? ["More"] : [])]));
    if (more.length) expect(within(openMore()).getAllByRole("menuitem").map((item) => item.textContent)).toEqual(more);
  });

  it("offers neither Run next nor Stop for a task in progress until the engine is known", () => {
    expect(actionsFor({ status: "in_progress", in_backlog: false }, null)).toEqual({ buttons: [], more: [] });
  });

  it("answers a blocked task's question in its decision only, not in More as well", async () => {
    await renderTask(BASE, taskRoutes({ task: taskDetail({ status: "blocked", blocked_kind: "engine", awaiting_human_gate: false }) }));
    expect(within(decision()).getByRole("button", { name: "Unblock" })).toBeInTheDocument();
    expect(within(openMore()).queryByRole("menuitem", { name: "Unblock" })).toBeNull();
  });

  it.each([
    ["Stop", "stop", { status: "in_progress" }, null, {}, "Stop requested. The task is blocked when the engine acts on it."],
    ["Block", "block", { status: "todo" }, "Why it is blocked", { reason: "Waiting for a key." }, "Blocked."],
    ["Reopen", "reopen", { status: "done" }, null, {}, "Reopened. The task is back in the queue."],
    ["Decline", "decline", { status: "todo", in_backlog: true }, "Why it is declined", { reason: "Waiting for a key." }, "Declined."],
  ])("%s is confirmed, calls its endpoint, and shows a refusal", async (label, action, fields, ask, body, done) => {
    const routes = withEngine(taskRoutes({ task: taskDetail(fields) }), "running");
    let refuse = true;
    routes[post(action)] = () => (refuse ? reply(400, { error: `Cannot ${action} this task`, code: "invalid_request" }) : { ok: true });
    const { fetchImpl } = await renderTask(BASE, routes);
    await engineKnown();
    if (label === "Stop") await screen.findByRole("button", { name: "Stop" });
    choose(label);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAccessibleDescription(/./);
    expect(postCalls(fetchImpl, action)).toHaveLength(0);
    if (ask) fireEvent.change(within(dialog).getByLabelText(ask), { target: { value: "Waiting for a key." } });
    const confirm = within(dialog).getByRole("button", { name: new RegExp(`^${label}( task)?$`) });
    fireEvent.click(confirm);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(`Cannot ${action} this task.`);
    refuse = false;
    fireEvent.click(confirm);
    expect(await screen.findByText(done)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    const sent = postCalls(fetchImpl, action);
    expect(sent).toHaveLength(2);
    expect(sent[1].body).toEqual(body);
  });

  it("Run next asks the project's engine to run this task", async () => {
    const routes = taskRoutes({ task: taskDetail({ status: "todo" }) });
    const url = "POST /api/v1/projects/foreman/agent/start";
    routes[url] = { started: true };
    const { fetchImpl } = await renderTask(BASE, routes);
    choose("Run next");
    fireEvent.click(within(screen.getByRole("dialog", { name: "Run this task next" })).getByRole("button", { name: "Run next" }));
    expect(await screen.findByText("Requested. The task starts when the engine picks the request up.")).toBeInTheDocument();
    expect(fetchImpl.calls.filter((call) => `${call.method} ${call.url}` === url)[0].body).toEqual({ task_id: TASK_ID });
  });

  describe("Close", () => {
    async function openClose(routes = taskRoutes({ task: taskDetail({ status: "todo" }) })) {
      const rendered = await renderTask(BASE, routes);
      choose("Close");
      return { ...rendered, dialog: screen.getByRole("dialog", { name: "Close this task" }) };
    }

    it("asks how the task ends, and calls nothing until that is said", async () => {
      const { fetchImpl, dialog } = await openClose();
      expect(dialog).toHaveAccessibleDescription(/./);
      expect(within(dialog).getAllByRole("radio").map((radio) => radio.checked)).toEqual([false, false]);
      expect(within(dialog).queryByLabelText("Why it is done")).toBeNull();
      fireEvent.click(within(dialog).getByRole("button", { name: "Close task" }));
      expect(within(dialog).getByRole("alert")).toHaveTextContent("Say how it ends.");
      expect(postCalls(fetchImpl, "cancel")).toHaveLength(0);
      expect(postCalls(fetchImpl, "complete")).toHaveLength(0);
    });

    it("as not needed, cancels the task, and shows a refusal", async () => {
      const routes = taskRoutes({ task: taskDetail({ status: "todo" }) });
      let refuse = true;
      routes[post("cancel")] = () => (refuse ? reply(400, { error: "Cannot cancel this task", code: "invalid_request" }) : { ok: true });
      const { fetchImpl, dialog } = await openClose(routes);
      fireEvent.click(within(dialog).getByRole("radio", { name: /^Not needed/ }));
      expect(within(dialog).queryByLabelText("Why it is done")).toBeNull();
      const confirm = within(dialog).getByRole("button", { name: "Cancel task" });
      fireEvent.click(confirm);
      expect(await within(dialog).findByRole("alert")).toHaveTextContent("Cannot cancel this task.");
      refuse = false;
      fireEvent.click(confirm);
      expect(await screen.findByText("Cancelled.")).toBeInTheDocument();
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(postCalls(fetchImpl, "cancel")).toHaveLength(2);
      expect(postCalls(fetchImpl, "complete")).toHaveLength(0);
    });

    it("as already done, needs the reason, then marks the task done with it", async () => {
      const routes = taskRoutes({ task: taskDetail({ status: "blocked", blocked_kind: "engine", awaiting_human_gate: false }) });
      routes[post("complete")] = { ok: true };
      const { fetchImpl, dialog } = await openClose(routes);
      fireEvent.click(within(dialog).getByRole("radio", { name: /^Already done/ }));
      const confirm = within(dialog).getByRole("button", { name: "Mark done" });
      fireEvent.click(confirm);
      expect(within(dialog).getByText("Why it is done is needed.")).toBeInTheDocument();
      expect(postCalls(fetchImpl, "complete")).toHaveLength(0);
      fireEvent.change(within(dialog).getByLabelText("Why it is done"), { target: { value: " Merged by hand in 721d877. " } });
      fireEvent.click(confirm);
      expect(await screen.findByText("Marked done.")).toBeInTheDocument();
      expect(postCalls(fetchImpl, "complete")[0].body).toEqual({ reason: "Merged by hand in 721d877." });
      expect(postCalls(fetchImpl, "cancel")).toHaveLength(0);
    });
  });

  it("Block needs a reason before it calls anything", async () => {
    const { fetchImpl } = await renderTask(BASE, taskRoutes({ task: taskDetail({ status: "todo" }) }));
    fireEvent.click(within(openMore()).getByRole("menuitem", { name: "Block" }));
    const dialog = screen.getByRole("dialog", { name: "Block this task" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Block task" }));
    expect(within(dialog).getByText("Why it is blocked is needed.")).toBeInTheDocument();
    expect(postCalls(fetchImpl, "block")).toHaveLength(0);
  });

  it("Delete is confirmed, shows a refusal, then goes to the sprint", async () => {
    const routes = taskRoutes({ task: taskDetail({ status: "todo" }) });
    const url = `DELETE /api/v1/tasks/${TASK_ID}`;
    let refuse = true;
    routes[url] = () => (refuse ? reply(400, { error: "A running agent step protects this task", code: "invalid_request" }) : { ok: "deleted" });
    const { fetchImpl } = await renderTask(BASE, routes);
    fireEvent.click(within(openMore()).getByRole("menuitem", { name: "Delete" }));
    const dialog = screen.getByRole("dialog", { name: "Delete this task" });
    expect(dialog).toHaveTextContent("This cannot be undone.");
    expect(within(dialog).getByRole("button", { name: "Keep it as it is" })).toHaveFocus();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete task" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("A running agent step protects this task.");
    refuse = false;
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete task" }));
    await waitFor(() => expect(window.location.pathname).toBe("/dashboard/sprints/sprint-56"));
    expect(fetchImpl.calls.filter((call) => `${call.method} ${call.url}` === url)).toHaveLength(2);
  });
});

describe("Overview", () => {
  it("shows the steps with result, by and runs", async () => {
    await renderTask();
    const table = await screen.findByRole("table", { name: "Steps" });
    const rows = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell").map((cell) => cell.textContent));
    expect(rows).toEqual([
      ["Develop", "Committed b232eb1", "Developer", "1"],
      ["Test", "Passed in 1 min 54 s", "Foreman", "1"],
      ["Review", "Approved in 7 s", "Code reviewer", "1"],
      ["Merge approval", "Waiting for you", "a user", ""],
      ["Merge", "Not reached", "Foreman", ""],
    ]);
    // By names the role; the model is on hover.
    expect(within(table).getByText("Developer")).toHaveAttribute("title", "sonnet-5-5");
    // No note pointing at the Activity tab, which is beside Overview already.
    expect(screen.queryByText(/is under/)).toBeNull();
  });

  it("says how many tests the test step ran, as its Activity row does", async () => {
    const task = taskDetail();
    task.runs = task.runs.map((entry) =>
      entry.workflow_step === "test" ? { ...entry, tests: { tests: 1221, passed: 1221, failed: 0, skipped: 0, failed_tests: [] } } : entry,
    );
    await renderTask(BASE, taskRoutes({ task }));
    const table = await screen.findByRole("table", { name: "Steps" });
    const row = within(table).getByText("Test").closest("tr");
    expect(within(row).getAllByRole("cell")[1].textContent).toBe("Passed · 1,221 tests in 1 min 54 s");
  });

  it("has no checks summary: the Steps table and the Checks tab say it", async () => {
    await renderTask();
    await screen.findByRole("table", { name: "Steps" });
    expect(screen.queryByRole("heading", { name: "Checks" })).toBeNull();
    expect(screen.queryByText(/evidence files/i)).toBeNull();
  });

  it("shows the details and the task as filed", async () => {
    await renderTask();
    const details = await screen.findByRole("region", { name: "Details" });
    await waitFor(() => expect(details).toHaveTextContent(/Workflow\s*development/));
    expect(details).toHaveTextContent(/Status\s*Waiting for merge approval/);
    expect(within(details).getByRole("link", { name: "Sprint 56: engine truthfulness" })).toHaveAttribute("href", "/dashboard/sprints/sprint-56");
    expect(details).toHaveTextContent("A user approves merges (project setting)");
    expect(details).not.toHaveTextContent("plans");
    expect(details).toHaveTextContent(/Branch\s*foreman\/for-14/);
    // Spend is money; how many steps there were is on Activity.
    expect(details).toHaveTextContent(/Spend\s*\$0\.72Filed/);
    expect(details).toHaveTextContent(/Filed by\s*a user on 10 Nov/);
    // What was filed is prose for the wide column, not a fact beside it.
    expect(details).not.toHaveTextContent("It should say how long");
    expect(screen.getByRole("region", { name: "Description" })).toHaveTextContent("It should say how long and what the runner printed.");
    expect(screen.getByRole("region", { name: "Acceptance criteria" })).toHaveTextContent("The result line is reported");
    const beside = screen.getByRole("complementary", { name: "Details and overrides" });
    expect(beside).toContainElement(details);
    expect(beside).toContainElement(screen.getByRole("heading", { name: "Overrides for this task" }));
  });

  it("has no box for telling the agent something (that is in the side bar) and no overrides on a finished task", async () => {
    await renderTask(BASE, taskRoutes({ task: taskDetail({ status: "done", blocked_kind: null }) }));
    await screen.findByRole("region", { name: "Description" });
    expect(screen.queryByRole("form", { name: "Tell the agent" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Overrides for this task" })).toBeNull();
  });

  it("has no box for telling the agent something on a task that is not finished either", async () => {
    await renderTask(BASE);
    await screen.findByRole("region", { name: "Description" });
    expect(screen.queryByRole("form", { name: "Tell the agent" })).toBeNull();
    expect(screen.queryByText("Guidance for the next agent step")).toBeNull();
  });


  it("refreshes from the sprint stream while a step runs", async () => {
    const { fetchImpl } = await renderTask(BASE, taskRoutes({ task: taskDetail({ status: "in_progress", workflow_current_step: "develop", awaiting_human_gate: false, gate_policy: null, blocked_kind: null }) }));
    const source = fetchImpl.EventSource.sources.find((entry) => entry.url === "/api/v1/sprints/sprint-56/stream");
    expect(source).toBeDefined();
    const before = taskReads(fetchImpl);
    source.emit({ type: "event", event: { id: "e9", task_id: "another-task" } });
    source.emit({ type: "event", event: { id: "e10", task_id: TASK_ID } });
    source.emit({ type: "event", event: { id: "e11", task_id: TASK_ID } });
    await waitFor(() => expect(taskReads(fetchImpl)).toBe(before + 1));
  });

  it("follows only the project's stream when nothing runs", async () => {
    const { fetchImpl } = await renderTask();
    await waitFor(() => expect(fetchImpl.EventSource.sources.length).toBeGreaterThan(0));
    expect(fetchImpl.EventSource.sources.map((entry) => entry.url)).toEqual(["/api/v1/projects/foreman/stream"]);
  });
});

describe("a task an agent filed", () => {
  const filed = (from) =>
    taskRoutes({
      task: taskDetail({ created_by: "agent:developer", filed_from: from }),
    });

  it("names the task it came from, linked to that task's run", async () => {
    await renderTask(BASE, filed({ task_id: "task-12", task_key: "FOR-12", title: "Parent", run_id: "run-9", exists: true }));
    const details = await screen.findByRole("region", { name: "Details" });
    await waitFor(() => expect(details).toHaveTextContent(/Filed by\s*the developer while working on FOR-12 on 10 Nov/));
    expect(within(details).getByRole("link", { name: "FOR-12" })).toHaveAttribute(
      "href",
      "/dashboard/tasks/task-12/activity?run=run-9",
    );
  });

  it("says so when that task no longer exists", async () => {
    await renderTask(BASE, filed({ task_id: "gone", task_key: null, title: null, run_id: "run-9", exists: false }));
    const details = await screen.findByRole("region", { name: "Details" });
    await waitFor(() =>
      expect(details).toHaveTextContent(/Filed by\s*the developer while working on a task that no longer exists/),
    );
    expect(within(details).queryByRole("link", { name: /gone/ })).toBeNull();
  });
});

describe("a merged task", () => {
  it("says it is merged and as which commit, not how far the default branch has moved", async () => {
    const checks = checksPayload();
    checks.facts.branch = { name: "foreman/for-14", default_branch: "main", ahead: null, behind: null, state: "merged", merged_as: COMMIT };
    await renderTask(`${BASE}/checks`, taskRoutes({ task: taskDetail({ status: "done", blocked_kind: null }), checks }));
    const facts = (await screen.findByRole("heading", { name: "Measured by Foreman" })).closest("section");
    expect(facts).toHaveTextContent("Merged into main");
    expect(facts).toHaveTextContent(COMMIT.slice(0, 7));
    expect(facts).not.toHaveTextContent("behind");
  });

  it("heads its changes with the commit it landed as", async () => {
    const changes = changesPayload({ merged_as: COMMIT, head: { branch: "foreman/for-14", sha: COMMIT } });
    await renderTask(`${BASE}/changes`, taskRoutes({ task: taskDetail({ status: "done", blocked_kind: null }), changes }));
    expect(await screen.findByText(/Merged into main as/)).toBeInTheDocument();
  });
});

describe("Overrides for this task", () => {
  const PATCH = `/api/v1/tasks/${TASK_ID}`;

  async function overrides(task = taskDetail(), routes = taskRoutes({ task })) {
    routes[`PATCH ${PATCH}`] = routes[`PATCH ${PATCH}`] ?? { ok: true };
    const utils = await renderTask(BASE, routes);
    const section = (await screen.findByRole("heading", { name: "Overrides for this task" })).closest("section");
    await within(section).findByLabelText("Who decides merge approval");
    return { ...utils, section };
  }

  it("offers who decides for the workflow's gates and a model for each agent step", async () => {
    const { section } = await overrides();
    expect(within(section).queryByLabelText(/plan approval/i)).toBeNull();
    expect(within(section).getByLabelText("Who decides merge approval")).toHaveValue("");
    // A model is chosen from the ones the project has configured, not typed.
    const develop = within(section).getByLabelText("Model for develop");
    expect(develop.tagName).toBe("SELECT");
    expect(develop).toHaveValue("");
    await within(develop).findByRole("option", { name: "claude-opus-5-5" });
    expect(within(develop).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "No override",
      "claude-sonnet-5-5",
      "claude-opus-5-5",
    ]);
    expect(within(section).getByLabelText("Model for review")).toBeInTheDocument();
    expect(within(section).queryByLabelText("Model for test")).toBeNull();
  });

  it("sets who decides and a step's model with one PATCH, keeping what else the task carries", async () => {
    const task = taskDetail({ executor_overrides: { ladder_start: 1, policy: { notification: "all" } } });
    const { section, fetchImpl } = await overrides(task);
    fireEvent.change(within(section).getByLabelText("Who decides merge approval"), { target: { value: "auto" } });
    await within(within(section).getByLabelText("Model for develop")).findByRole("option", { name: "claude-opus-5-5" });
    fireEvent.change(within(section).getByLabelText("Model for develop"), { target: { value: "claude-opus-5-5" } });
    fireEvent.click(within(section).getByRole("button", { name: "Save overrides" }));
    await waitFor(() => expect(calls(fetchImpl, "PATCH", PATCH)).toHaveLength(1));
    expect(calls(fetchImpl, "PATCH", PATCH)[0].body).toEqual({
      executor_overrides: {
        ladder_start: 1,
        policy: { notification: "all", merge_approval: "auto" },
        models: { develop: "claude-opus-5-5" },
      },
    });
    await waitFor(() => expect(taskReads(fetchImpl)).toBeGreaterThan(1));
    expect(await within(section).findByRole("status")).toHaveTextContent("Saved.");
  });

  it("clears what was set, in the older gates form too", async () => {
    const task = taskDetail({
      executor_overrides: { gates: { merge_approval: "human" }, models: { develop: "opus-5-5" } },
    });
    const { section, fetchImpl } = await overrides(task);
    expect(within(section).getByLabelText("Who decides merge approval")).toHaveValue("human");
    expect(within(section).getByLabelText("Model for develop")).toHaveValue("opus-5-5");
    fireEvent.change(within(section).getByLabelText("Who decides merge approval"), { target: { value: "" } });
    fireEvent.change(within(section).getByLabelText("Model for develop"), { target: { value: "" } });
    fireEvent.click(within(section).getByRole("button", { name: "Save overrides" }));
    await waitFor(() => expect(calls(fetchImpl, "PATCH", PATCH)).toHaveLength(1));
    expect(calls(fetchImpl, "PATCH", PATCH)[0].body).toEqual({ executor_overrides: {} });
  });

  it("shows the refusal as the API's sentence", async () => {
    const routes = taskRoutes();
    routes[`PATCH ${PATCH}`] = reply(400, { error: "Unknown workflow step 'develop' in executor_overrides.models.", code: "validation_error" });
    const { section } = await overrides(taskDetail(), routes);
    await within(within(section).getByLabelText("Model for develop")).findByRole("option", { name: "claude-opus-5-5" });
    fireEvent.change(within(section).getByLabelText("Model for develop"), { target: { value: "claude-opus-5-5" } });
    fireEvent.click(within(section).getByRole("button", { name: "Save overrides" }));
    expect(await within(section).findByRole("alert")).toHaveTextContent("Unknown workflow step 'develop' in executor_overrides.models.");
  });

  it("names this task as the source in Details once the task says so", async () => {
    const task = taskDetail({
      executor_overrides: { policy: { merge_approval: "auto" } },
      policy: { ...taskDetail().policy, merge_approval: { value: "auto", source: "task_override" } },
    });
    await overrides(task);
    const details = await screen.findByRole("region", { name: "Details" });
    await waitFor(() => expect(details).toHaveTextContent("Foreman approves merges (this task)"));
  });
});

describe("Changes", () => {
  it("lists the files and shows the first file's diff, marked by sign as well as colour", async () => {
    const { fetchImpl } = await renderTask(`${BASE}/changes`);
    expect(await screen.findByRole("heading", { name: /^Files\s*3$/ })).toBeInTheDocument();
    expect(screen.getByText(/compared with main/)).toBeInTheDocument();
    // The files sit beside the diff, in their own scrolling list.
    expect(document.querySelector(".task-changes__files .task-changes__list table")).not.toBeNull();
    expect(document.querySelector(".task-changes__diff")).not.toBeNull();
    const files = screen.getByRole("table", { name: "Files changed" });
    const picks = within(files).getAllByRole("button");
    expect(picks.map((button) => button.getAttribute("aria-pressed"))).toEqual(["true", "false", "false"]);
    expect(within(files).getAllByRole("row")[1]).toHaveTextContent("+12 −7");

    const diff = await screen.findByRole("table", { name: /Lines changed/ });
    const lines = diff.querySelectorAll("tbody tr");
    expect([...lines].map((line) => line.className)).toEqual([
      "diff__line diff__line--hunk",
      "diff__line diff__line--context",
      "diff__line diff__line--del",
      "diff__line diff__line--add",
    ]);
    expect(lines[2].querySelector(".diff__sign")).toHaveTextContent("−");
    expect(lines[2]).toHaveTextContent("old line");
    expect(lines[3].querySelector(".diff__sign")).toHaveTextContent("+");
    expect(calls(fetchImpl, "GET", diffUrl("foreman/builtins.py").slice(4))).toHaveLength(1);
  });

  it("shows another file when it is picked, and says when its diff was cut", async () => {
    const routes = taskRoutes();
    routes[diffUrl("tests/test_builtins.py")] = diffPayload("tests/test_builtins.py", BUILTINS_DIFF, { truncated: true, total_chars: 250000 });
    await renderTask(`${BASE}/changes`, routes);
    const files = await screen.findByRole("table", { name: "Files changed" });
    fireEvent.click(within(files).getByRole("button", { name: /tests\/test_builtins\.py/ }));
    expect(within(files).getByRole("button", { name: /tests\/test_builtins\.py/ })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("This diff is 250,000 characters long; the first 200,000 are shown.")).toBeInTheDocument();
  });

  it("says a binary file has no lines", async () => {
    const routes = taskRoutes();
    routes[diffUrl("docs/shot.png")] = diffPayload("docs/shot.png", "", { status: "added" });
    await renderTask(`${BASE}/changes`, routes);
    const files = await screen.findByRole("table", { name: "Files changed" });
    fireEvent.click(within(files).getByRole("button", { name: /docs\/shot\.png/ }));
    expect(await screen.findByText("A binary file. There are no lines to show.")).toBeInTheDocument();
  });

  it("says why there is nothing to show when the branch changed nothing", async () => {
    await renderTask(
      `${BASE}/changes`,
      taskRoutes({ changes: changesPayload({ files: [], totals: { files: 0, added: 0, deleted: 0 }, empty_reason: "The task has no branch yet." }) }),
    );
    expect(await screen.findByText("The task has no branch yet.")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Files changed" })).toBeNull();
    expect(screen.getByText("FOR-14 · fix · foreman/for-14 · b232eb1")).toBeInTheDocument();
  });
});

describe("Changes, a long list", () => {
  const many = [
    ...["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"].map((name) => `foreman/dashboard/${name}`),
    ...["g.py", "h.py"].map((name) => `foreman/engine/${name}`),
    ...["test_a.py", "test_b.py", "test_c.py"].map((name) => `tests/${name}`),
    "README.md",
  ].map((path) => ({ path, status: "modified", added: 2, deleted: 1, binary: false, old_path: null }));
  const routes = () => {
    const all = taskRoutes({ changes: changesPayload({ files: many, totals: { files: 12, added: 24, deleted: 12 } }) });
    for (const file of many) all[diffUrl(file.path)] = diffPayload(file.path, BUILTINS_DIFF);
    return all;
  };

  it("offers the folders, narrows to one, and widens again from the breadcrumb", async () => {
    await renderTask(`${BASE}/changes`, routes());
    const files = await screen.findByRole("table", { name: "Files changed" });
    expect(within(files).getAllByRole("row")).toHaveLength(13);
    const folders = screen.getByRole("list", { name: "Folders" });
    expect(within(folders).getAllByRole("button").map((button) => button.textContent)).toEqual([
      "foreman8 files+16 −8",
      "tests3 files+6 −3",
    ]);

    fireEvent.click(within(folders).getByRole("button", { name: /foreman/ }));
    expect(within(files).getAllByRole("row")).toHaveLength(9);
    // Inside a folder, names are shown from that folder down.
    expect(within(files).getByRole("button", { name: "dashboard/a.py" })).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole("list", { name: "Folders" })).getByRole("button", { name: /engine/ }));
    expect(within(files).getAllByRole("row")).toHaveLength(3);

    const crumbs = screen.getByRole("navigation", { name: "Folder" });
    expect(crumbs).toHaveTextContent("All filesforemanengine");
    fireEvent.click(within(crumbs).getByRole("button", { name: "foreman" }));
    expect(within(files).getAllByRole("row")).toHaveLength(9);
    fireEvent.click(within(crumbs).getByRole("button", { name: "All files" }));
    expect(within(files).getAllByRole("row")).toHaveLength(13);
  });

  it("keeps the picked file when the list is narrowed to another folder", async () => {
    await renderTask(`${BASE}/changes`, routes());
    const files = await screen.findByRole("table", { name: "Files changed" });
    fireEvent.click(within(files).getByRole("button", { name: "README.md" }));
    expect(await screen.findByRole("heading", { name: "README.md" })).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole("list", { name: "Folders" })).getByRole("button", { name: /tests/ }));
    expect(screen.getByRole("heading", { name: "README.md" })).toBeInTheDocument();
  });
});

describe("Checks", () => {
  it("keeps facts and claims in separate tables, then evidence files", async () => {
    await renderTask(`${BASE}/checks`);
    const facts = await screen.findByRole("table", { name: "Measured by Foreman" });
    const claims = screen.getByRole("table", { name: "Reported by an agent" });
    const firstCells = (table) =>
      within(table)
        .getAllByRole("row")
        .slice(1)
        .map((row) => within(row).getAllByRole("cell")[0].textContent);
    expect(firstCells(facts)).toEqual(["Tests", "Branch", "Size of change"]);
    expect(firstCells(claims)).toEqual(["Review", "Criterion 1", "Criterion 2"]);
    // The detail is the sentence the test step's log ends with; the output's last line ("OK") is not repeated.
    expect(facts).toHaveTextContent("Tests passed in 1 min 54 s at b232eb1");
    expect(facts).not.toHaveTextContent("Ran 1221 tests in 114.2s OK");
    expect(facts).toHaveTextContent("Up to date with main");
    expect(facts).toHaveTextContent("3 files, +118 −7");
    expect(facts).not.toHaveTextContent("Review");
    expect(claims).toHaveTextContent("Approved");
    expect(claims).toHaveTextContent("Clean change, tests cover it.");
    expect(claims).toHaveTextContent("Covered by review");
    // The review is named by its role; the commit it approved is said once, on its row.
    expect(claims).toHaveTextContent(/by Code reviewer/);
    expect(claims).not.toHaveTextContent("sonnet-5-5");
    expect(claims).not.toHaveTextContent("Code review approved");
    expect(claims).not.toHaveTextContent("Size of change");
    expect(screen.queryByText(/judged/i)).toBeNull();
    // A criterion's `code` is formatted as it is on the Overview.
    expect(claims).not.toHaveTextContent("`");
    // No evidence files: nothing to say about them.
    expect(screen.queryByRole("heading", { name: "Evidence files" })).toBeNull();
  });

  it("says how many tests ran when the command reported them", async () => {
    const checks = checksPayload();
    checks.facts.tests.counts = { tests: 1221, passed: 1220, failed: 0, skipped: 1, failed_tests: [] };
    await renderTask(`${BASE}/checks`, taskRoutes({ checks }));
    const facts = await screen.findByRole("table", { name: "Measured by Foreman" });
    const row = within(facts).getAllByRole("row")[1];
    expect(row).toHaveTextContent(/Passed\s*1,221 tests passed \(1 skipped\) in 1 min 54 s at b232eb1/);
    expect(within(row).queryByRole("list", { name: "Failed tests" })).toBeNull();
  });

  it("names the tests that failed", async () => {
    const checks = checksPayload();
    checks.facts.tests = {
      ...checks.facts.tests,
      status: "failed",
      exit_code: 1,
      duration_seconds: 12,
      counts: {
        tests: 186,
        passed: 183,
        failed: 53,
        skipped: 0,
        failed_tests: [
          { suite: "tests.test_api.ApiTests", name: "test_token_is_required" },
          { suite: "", name: "test_alone" },
        ],
      },
    };
    await renderTask(`${BASE}/checks`, taskRoutes({ checks }));
    const facts = await screen.findByRole("table", { name: "Measured by Foreman" });
    const row = within(facts).getAllByRole("row")[1];
    expect(row).toHaveTextContent(/Failed\s*53 of 186 tests failed \(exit code 1\) in 12 s at b232eb1/);
    const failed = within(row).getByRole("list", { name: "Failed tests" });
    const items = within(failed).getAllByRole("listitem").map((item) => item.textContent);
    expect(items).toEqual(["test_token_is_required tests.test_api.ApiTests", "test_alone ", "and 51 more"]);
  });

  it("says when nothing was claimed and the tests did not run", async () => {
    const checks = checksPayload();
    checks.facts.tests = { status: "not_run", exit_code: null, duration_seconds: null, command: null, result_line: null, commit: null, head_sha: null };
    checks.claims = { reviews: [], criteria: [] };
    await renderTask(`${BASE}/checks`, taskRoutes({ checks }));
    const facts = await screen.findByRole("table", { name: "Measured by Foreman" });
    expect(facts).toHaveTextContent("Not run");
    expect(screen.queryByRole("table", { name: "Reported by an agent" })).toBeNull();
    expect(screen.getByText("No agent has reported on this task yet, and it has no acceptance criteria to check.")).toBeInTheDocument();
  });
});

describe("Activity", () => {
  it("says how many tests a test step ran, in the table, its result and its story", async () => {
    const report = { tests: 1221, passed: 1220, failed: 0, skipped: 1 };
    const routes = taskRoutes({
      runs: [runItem("run-2", "test", { role_id: "_builtin:run_tests", backend: "builtin", model: null, outcome: "success", tests: report })],
    });
    routes[outputUrl("run-2")] = outputPayload("run-2", "", {
      prompt: null,
      transcript: [
        { at: on("11-11"), kind: "engine.test_started", text: "", data: { command: "make test" } },
        { at: on("11-11"), kind: "engine.test_run", text: "", data: { exit_code: 0, duration_seconds: 114.2, head_sha: COMMIT, report: { ...report, files: 2 } } },
      ],
    });
    await renderTask(`${BASE}/activity`, routes);
    const table = await screen.findByRole("table", { name: "Steps" });
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("Passed · 1,221 tests, 1 skipped");
    const facts = await screen.findByRole("complementary", { name: "About this step" });
    expect(facts).toHaveTextContent(/Result\s*Passed · 1,221 tests, 1 skipped/);
    const story = screen.getByRole("list", { name: "What happened" });
    expect(story).toHaveTextContent("1,221 tests passed (1 skipped) in 1 min 54 s at b232eb1");
  });

  it("lists runs newest first and shows the picked run: its story, beginning with its prompt, and its facts", async () => {
    const { fetchImpl } = await renderTask(`${BASE}/activity`);
    const table = await screen.findByRole("table", { name: "Steps" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[1].textContent)).toEqual(["Review", "Test"]);
    expect(rows[0]).toHaveTextContent("Approved");
    expect(rows[1]).toHaveTextContent("Foreman");
    // The commit the branch was at after each run; none for the engine's test run.
    expect(rows[0]).toHaveTextContent("b232eb1");
    expect(within(rows[1]).getAllByRole("cell")[4].textContent).toBe("");
    // The count is of the steps listed; the spend is the task's.
    const heading = screen.getByRole("heading", { name: /^Steps/ }).closest(".section-heading");
    expect(heading).toHaveTextContent(/^Steps\s*2\s*\$0\.72 in all$/);

    expect(await screen.findByText("Reviewed the change.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Review" })).toBeInTheDocument();
    // The story begins when Foreman sends the agent its prompt: a line like the others.
    const story = screen.getByRole("list", { name: "What happened" });
    const first = within(story).getAllByRole("listitem")[0];
    expect(first).toHaveTextContent("Sent the prompt · 1 line");
    expect(first).toHaveTextContent("The prompt of run-3");
    // Its facts beside it: how it ended, the commit it was about, who, the model, the time and cost, what came next.
    const facts = screen.getByRole("complementary", { name: "About this step" });
    expect(facts).toHaveTextContent(/Result\s*Approved/);
    expect(facts).toHaveTextContent(/Commit\s*b232eb1/);
    expect(facts).toHaveTextContent(/By\s*Developer/);
    expect(facts).toHaveTextContent(/Model\s*sonnet-5-5/);
    expect(facts).toHaveTextContent(/Took\s*7 s/);
    expect(facts).toHaveTextContent(/Spend\s*\$0\.12 · 1K tokens/);
    expect(within(facts).getByRole("button", { name: "Download the transcript" })).toBeInTheDocument();
    expect(screen.queryByText(/No prompt was recorded/)).toBeNull();

    // No caret on a row: what a run shows is under the list, not under its row.
    expect(table.querySelector(".caret")).toBeNull();
    expect(rows[0]).toHaveClass("table__row--selected");

    // Pressing anywhere on a run's row picks it, not only its time.
    fireEvent.click(within(rows[1]).getAllByRole("cell")[1]);
    expect(await screen.findByText("Ran 1221 tests")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Test" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "About this step" })).toHaveTextContent(/By\s*Foreman/);

    expect(within(rows[1]).getByRole("button")).toHaveAttribute("aria-pressed", "true");
    expect(rows[1]).toHaveClass("table__row--selected");
    expect(rows[0]).not.toHaveClass("table__row--selected");
    expect(calls(fetchImpl, "GET", outputUrl("run-2").slice(4))).toHaveLength(1);
    // The run after it is named among its facts, and picking it there shows it.
    fireEvent.click(within(screen.getByRole("complementary", { name: "About this step" })).getByRole("button", { name: "Review" }));
    expect(await screen.findByText("Reviewed the change.")).toBeInTheDocument();
    expect(rows[0]).toHaveClass("table__row--selected");

    fireEvent.click(within(rows[0]).getByRole("button"));
    expect(await screen.findByText("Reviewed the change.")).toBeInTheDocument();
  });

  it("opens at the run a link names, with a send-back's reason on hover, and the attempt after it names it", async () => {
    const routes = taskRoutes({
      runs: [
        runItem("run-3", "review", {
          role_id: "code_reviewer",
          outcome: "steer",
          outcome_detail: "The log can still contain the host and port.",
        }),
        runItem("run-2", "test", { role_id: "_builtin:run_tests", backend: "builtin", model: null, outcome: "success" }),
      ],
    });
    await renderTask(`${BASE}/activity?run=run-2`, routes);
    const table = await screen.findByRole("table", { name: "Steps" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[1]).toHaveClass("table__row--selected");
    expect(await screen.findByText("Ran 1221 tests")).toBeInTheDocument();
    // One line per row: the reason is on hover, not under the row.
    expect(within(rows[0]).getByText("Sent back")).toHaveAttribute("title", "The log can still contain the host and port.");
    expect(rows[0]).not.toHaveTextContent("The log can");
    expect(rows[1]).toHaveTextContent(/Foreman/);
    expect(within(rows[1]).getByText("Passed")).toBeInTheDocument();

    // Picking the send-back shows what the reviewer wrote, and that it sent the task back.
    fireEvent.click(within(rows[0]).getByText("Sent back"));
    expect(await screen.findByText("Reviewed the change.")).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "About this step" })).toHaveTextContent(/Result\s*Sent back/);
  });

  it("reads the list again in place when a step is registered: rows stay, the new one opens, the pick is kept", async () => {
    const routes = taskRoutes({
      task: taskDetail({ status: "in_progress", workflow_current_step: "merge", awaiting_human_gate: false, gate_policy: null, blocked_kind: null }),
    });
    const { fetchImpl } = await renderTask(`${BASE}/activity`, routes);
    const table = await screen.findByRole("table", { name: "Steps" });
    const firstRow = within(table).getAllByRole("row")[1];
    // The person goes back to the earlier run.
    fireEvent.click(within(table).getAllByRole("row")[2]);
    expect(await screen.findByText("Ran 1221 tests")).toBeInTheDocument();
    const shown = document.querySelector("#run-output");

    // A new step is registered while they read.
    const before = fetchImpl.routes[RUNS_URL];
    fetchImpl.routes[RUNS_URL] = { ...before, runs: [runItem("run-9", "merge", { backend: "builtin", model: null }), ...before.runs], total: before.total + 1 };
    fetchImpl.routes[outputUrl("run-9")] = outputPayload("run-9", "Merged.");
    const source = fetchImpl.EventSource.sources.find((entry) => entry.url === "/api/v1/sprints/sprint-56/stream");
    source.emit({ type: "event", event: { id: "e20", task_id: TASK_ID } });
    await waitFor(() => expect(within(screen.getByRole("table", { name: "Steps" })).getAllByRole("row")).toHaveLength(4), { timeout: 3000 });

    const rows = within(screen.getByRole("table", { name: "Steps" })).getAllByRole("row").slice(1);
    // The row that was there is the same element, the new one is marked as arrived, and nothing went blank.
    expect(rows[1]).toBe(firstRow);
    expect(rows[0]).toHaveClass("table__row--arrived");
    expect(rows[1]).not.toHaveClass("table__row--arrived");
    // What the person picked is still what is shown, untouched.
    expect(document.querySelector("#run-output")).toBe(shown);
    expect(screen.getByRole("heading", { name: "Test" })).toBeInTheDocument();
    expect(rows[2]).toHaveClass("table__row--selected");
  });

  it("pages 25 runs at a time with Earlier", async () => {
    const all = Array.from({ length: 30 }, (_, index) => runItem(`run-${index}`, index % 2 ? "test" : "develop"));
    const routes = taskRoutes();
    routes[RUNS_URL] = { runs: all.slice(0, 25), total: 30, limit: 25, offset: 0 };
    routes[`GET /api/v1/tasks/${TASK_ID}/runs?limit=25&offset=25`] = { runs: all.slice(25), total: 30, limit: 25, offset: 25 };
    routes[outputUrl("run-0")] = outputPayload("run-0", "First output", { prompt: null, transcript: [] });
    await renderTask(`${BASE}/activity`, routes);
    const table = await screen.findByRole("table", { name: "Steps" });
    expect(within(table).getAllByRole("row")).toHaveLength(26);
    expect(await screen.findByText("This run recorded nothing to read.")).toBeInTheDocument();
    expect(screen.queryByText(/No prompt was recorded/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Earlier" }));
    await waitFor(() => expect(within(screen.getByRole("table", { name: "Steps" })).getAllByRole("row")).toHaveLength(31));
    expect(screen.queryByRole("button", { name: "Earlier" })).toBeNull();
  });

  it("tells the run as one kind of line, with its facts beside it and the whole record to download", async () => {
    const at = "2026-11-12T18:27:39Z";
    const routes = taskRoutes({
      runs: [
        runItem("run-3", "review", { role_id: "code_reviewer", outcome: "approve", commit_sha: null, attempt: 2 }),
        runItem("run-2", "develop", { role_id: "developer", outcome: "done" }),
        runItem("run-1", "review", { role_id: "code_reviewer", outcome: "steer", outcome_detail: "Fix the log." }),
      ],
    });
    routes[outputUrl("run-3")] = outputPayload("run-3", "", {
      transcript: [
        { at, kind: "workflow.step_started", text: "", data: { step: "review", visit_count: 2 } },
        { at, kind: "workflow.model_selected", text: "", data: { model: "sonnet-5-5", source: "role" } },
        { at, kind: "engine.role_policy", text: "", data: { allowed_tools: ["Read", "Grep", "Glob"], disallowed_tools: [] } },
        { at, kind: "agent.started", text: "", data: { command: "claude --print" } },
        { at, kind: "agent.file_change", text: "", data: { tool: "Read", path: "/r/.foreman/worktrees/FOR-9/foreman/builtins.py" } },
        { at, kind: "agent.command", text: "", data: { command: "git diff main" } },
        { at, kind: "agent.tool_result", text: "", data: { is_error: true, preview: "Error: No such tool available: Bash." } },
        { at, kind: "agent.rate_limit", text: "", data: { rate_limit_type: "seven_day", status: "allowed_warning" } },
        { at, kind: "agent.message", text: "", data: { phase: "assistant", text: "APPROVE\n\nThe change does **what** the task asks." } },
        { at, kind: "engine.context_write", text: "", data: { path: ".foreman/context.md" } },
        { at, kind: "engine.review_recorded", text: "", data: { head_sha: "c248621ae45e", outcome: "approve" } },
        { at, kind: "engine.sprint_ready", text: "", data: { sprint_id: "s" } },
        { at, kind: "workflow.step_completed", text: "", data: { step: "review", outcome: "approve" } },
        { at, kind: "workflow.transition", text: "", data: { to_step: "merge_approval" } },
      ],
      raw_entries: 2,
    });
    routes[`${outputUrl("run-3")}?raw=true`] = outputPayload("run-3", "", {
      transcript: [
        { at, kind: "agent.raw_output", stream: "stdout", text: '{"type":"system"}', data: null },
        { at, kind: "agent.raw_output", stream: "stdout", text: '{"type":"result"}', data: null },
      ],
      raw_entries: 2,
      raw_included: true,
    });
    const { fetchImpl } = await renderTask(`${BASE}/activity`, routes);

    const story = await screen.findByRole("list", { name: "What happened" });
    const lines = within(story).getAllByRole("listitem").map((item) => item.textContent.replace(/^\d\d:\d\d:\d\d/, ""));
    expect(lines).toEqual([
      "Sent the prompt · 1 lineThe prompt of run-3",
      // These events are dated the day after the run began, and the story says so.
      "12 Nov",
      "Readforeman/builtins.py",
      "Rangit diff main",
      "Not run: this role may not use Bash",
      "The change does what the task asks.",
    ]);
    // No bookkeeping, no event names, no JSON, no decision word.
    expect(story).not.toHaveTextContent("{");
    expect(story).not.toHaveTextContent("APPROVE");
    expect(screen.getByText("what").tagName).toBe("STRONG");
    expect(screen.getByRole("heading", { name: "Review" }).closest(".section-heading")).toHaveTextContent("attempt 2");
    // Its row names the attempt after the step, as the heading does.
    const firstRow = within(screen.getByRole("table", { name: "Steps" })).getAllByRole("row")[1];
    expect(within(firstRow).getByText("attempt 2")).toHaveClass("activity-table__note");

    const facts = screen.getByRole("complementary", { name: "About this step" });
    expect(facts).not.toHaveTextContent("After");
    expect(facts).toHaveTextContent(/Reviewed\s*c248621/);
    expect(facts).toHaveTextContent(/By\s*Code reviewer/);
    expect(facts).toHaveTextContent(/Model\s*sonnet-5-5, set by the role/);
    expect(facts).toHaveTextContent(/May use\s*Read, Grep and Glob/);
    expect(facts).toHaveTextContent(/Next\s*Merge approval/);

    // The raw stream is read only to be downloaded, with everything else the run recorded.
    expect(calls(fetchImpl, "GET", `${outputUrl("run-3").slice(4)}?raw=true`)).toHaveLength(0);
    const saved = [];
    const created = vi.fn((blob) => {
      saved.push(blob);
      return "blob:transcript";
    });
    const revoked = vi.fn();
    vi.stubGlobal("URL", Object.assign(Object.create(URL), { createObjectURL: created, revokeObjectURL: revoked }));
    // jsdom cannot follow a download link; the click is where the browser saves the file.
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    try {
      fireEvent.click(within(facts).getByRole("button", { name: "Download the transcript" }));
      await waitFor(() => expect(saved).toHaveLength(1));
      expect(clicked).toHaveBeenCalledTimes(1);
      // The file's address is let go once the browser has it.
      await waitFor(() => expect(revoked).toHaveBeenCalledWith("blob:transcript"), { timeout: 2000 });
    } finally {
      vi.unstubAllGlobals();
      clicked.mockRestore();
    }
    const text = await new Promise((done) => {
      const reader = new FileReader();
      reader.onload = () => done(reader.result);
      reader.readAsText(saved[0]);
    });
    expect(text).toContain("The prompt of run-3");
    expect(text).toContain("engine.sprint_ready");
    expect(text).toContain('{"type":"result"}');

    // The step that answered a send-back names it, and picking it there shows it.
    const rows = within(screen.getByRole("table", { name: "Steps" })).getAllByRole("row").slice(1);
    fireEvent.click(within(rows[1]).getAllByRole("cell")[1]);
    const answered = await screen.findByRole("complementary", { name: "About this step" });
    await waitFor(() => expect(answered).toHaveTextContent(/After\s*Review, sent back/));
    fireEvent.click(within(answered).getByRole("button", { name: "Review, sent back" }));
    await waitFor(() => expect(rows[2]).toHaveClass("table__row--selected"));
  });

  const nineFiles = ["assay/serve.py", "tests/test_serve.py", "README.md", "assay/cli.py", "docs/a.md", "docs/b.md", "assay/__init__.py", "setup.cfg", "tests/conftest.py"].map(
    (path, index) => ({ path, added: 30 + index, removed: index, status: index === 1 ? "added" : "modified" }),
  );

  it("says a step's session and what it changed, in the Changes tab's words", async () => {
    const routes = taskRoutes({
      runs: [
        runItem("run-2", "develop", { role_id: "developer", outcome: "done", attempt: 2 }),
        runItem("run-1", "develop", { role_id: "developer", outcome: "done" }),
      ],
    });
    routes[outputUrl("run-2")] = outputPayload("run-2", "", {
      prompt: null,
      transcript: [{ at: on("11-11"), kind: "engine.step_changes", text: "", data: { from_sha: "c248621" } }],
      session: { continued_from: "run-1", continued_attempt: 1 },
      changes: {
        from_sha: "c248621ae45e",
        to_sha: "d0d0d0d",
        files: nineFiles,
        files_total: 9,
        added: 327,
        removed: 4,
        against: { kind: "attempt", sha: "c248621ae45e", run_id: "run-1", attempt: 1, branch: null },
      },
    });
    routes[outputUrl("run-1")] = outputPayload("run-1", "", {
      prompt: null,
      session: { continued_from: null, continued_attempt: null },
      changes: {
        from_sha: "0db4ca5aaaa",
        to_sha: "c248621ae45e",
        files: [{ path: "a.py", added: 1, removed: 0, status: "modified" }],
        files_total: 1,
        added: 1,
        removed: 0,
        against: { kind: "default_branch", sha: "0db4ca5aaaa", run_id: null, attempt: null, branch: "main" },
      },
    });
    routes[outputUrl("run-3")] = outputPayload("run-3", "", { prompt: null, session: null, changes: null, merge: null });
    await renderTask(`${BASE}/activity`, routes);

    const facts = await screen.findByRole("complementary", { name: "About this step" });
    expect(facts).toHaveTextContent(/Session\s*Continued from attempt 1/);
    expect(facts).toHaveTextContent(/Changed\s*9 files\s*\+327\s*−4/);
    expect(facts).toHaveTextContent("since attempt 1's commit c248621");
    // Five files, alphabetical, the new one marked, then the rest on request.
    const listed = () => Array.from(facts.querySelectorAll(".run-changes__file")).map((item) => item.textContent);
    expect(listed()).toEqual([
      "README.md+32 −2",
      "assay/__init__.py+36 −6",
      "assay/cli.py+33 −3",
      "assay/serve.py+30 −0",
      "docs/a.md+34 −4",
    ]);
    expect(within(facts).queryByRole("link", { name: /serve/ })).toBeNull();
    fireEvent.click(within(facts).getByRole("button", { name: "Show all 9" }));
    expect(listed()).toHaveLength(9);
    expect(listed()).toContain("tests/test_serve.py added+31 −1");
    expect(within(facts).getByRole("button", { name: "Show fewer" })).toBeInTheDocument();

    // The attempt it continued is a link that picks that run.
    fireEvent.click(within(facts).getByRole("button", { name: "attempt 1" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Develop" }).closest(".section-heading")).not.toHaveTextContent("attempt 2"));
    const first = await screen.findByRole("complementary", { name: "About this step" });
    await waitFor(() => expect(first).toHaveTextContent(/Session\s*New/));
    expect(first).toHaveTextContent("since main at 0db4ca5, where the branch began");
    expect(first).toHaveTextContent(/Changed\s*1 file\s*\+1\s*−0/);
    expect(first).not.toHaveTextContent("Show all");
  });

  it("shows no Changed row for a step that recorded none", async () => {
    const routes = taskRoutes({ runs: [runItem("run-1", "develop", { role_id: "developer", outcome: "done" })] });
    routes[outputUrl("run-1")] = outputPayload("run-1", "", { prompt: null, session: { continued_from: null, continued_attempt: null }, changes: null });
    await renderTask(`${BASE}/activity`, routes);
    const facts = await screen.findByRole("complementary", { name: "About this step" });
    await waitFor(() => expect(facts).toHaveTextContent(/Session\s*New/));
    expect(facts).not.toHaveTextContent("Changed");
    expect(facts).not.toHaveTextContent("Main before");
  });

  it("says what a merge brought in, and has no Branch row", async () => {
    const routes = taskRoutes({
      runs: [runItem("run-9", "merge", { role_id: "_builtin:merge", backend: "builtin", model: null, outcome: "success", cost_usd: 0, tokens: 0 })],
    });
    routes[outputUrl("run-9")] = outputPayload("run-9", "", {
      prompt: null,
      transcript: [{ at: on("11-11"), kind: "engine.merge", text: "", data: { branch: "feat/x", target: "main", sha: "c6aa057aaaa" } }],
      session: null,
      merge: {
        target_before: "0db4ca5bbbb",
        commits: [
          { sha: "c248621ae45e", subject: "feat: serve the dashboard from a single process" },
          { sha: "0a5b562ffff", subject: "fix: tests" },
        ],
        commits_total: 2,
        changes: { files: [], files_total: 9, added: 383, removed: 4 },
      },
    });
    await renderTask(`${BASE}/activity`, routes);

    const facts = await screen.findByRole("complementary", { name: "About this step" });
    expect(facts).toHaveTextContent(/Main before\s*0db4ca5/);
    expect(within(facts).getByText("0db4ca5")).toHaveAttribute("title", "0db4ca5bbbb");
    expect(facts).toHaveTextContent(/Merge commit\s*c6aa057/);
    expect(facts).toHaveTextContent(/Brought in\s*2 commits/);
    const commits = Array.from(facts.querySelectorAll(".run-changes__commit"));
    expect(commits.map((item) => item.textContent)).toEqual(["c248621feat: serve the dashboard from a single process", "0a5b562fix: tests"]);
    expect(commits[0]).toHaveAttribute("title", "feat: serve the dashboard from a single process");
    expect(facts).toHaveTextContent(/Changed\s*9 files\s*\+383\s*−4/);
    expect(within(facts).getByRole("link", { name: "9 files" })).toHaveAttribute("href", expect.stringMatching(/\/changes$/));
    expect(facts).not.toHaveTextContent("Branch");
    expect(facts).not.toHaveTextContent("Session");
  });

  it("says who decided a gate the project's setting decided, and that no one was asked", async () => {
    const routes = taskRoutes({
      runs: [runItem("run-5", "merge_approval", { role_id: "_builtin:human_gate", backend: "builtin", model: null, outcome: "approve", duration_ms: 10, cost_usd: 0, tokens: 0 })],
    });
    routes[outputUrl("run-5")] = outputPayload("run-5", "", {
      prompt: null,
      transcript: [
        { at: on("11-11"), kind: "workflow.step_started", text: "", data: { step: "merge_approval", visit_count: 1 } },
        { at: on("11-11"), kind: "workflow.gate_auto_approved", text: "", data: { policy: "merge_approval", step: "merge_approval" } },
        { at: on("11-11"), kind: "workflow.step_completed", text: "", data: { step: "merge_approval", outcome: "approve" } },
        { at: on("11-11"), kind: "workflow.transition", text: "", data: { to_step: "merge" } },
      ],
    });
    await renderTask(`${BASE}/activity`, routes);
    const story = await screen.findByRole("list", { name: "What happened" });
    expect(within(story).getAllByRole("listitem").map((item) => item.textContent.replace(/^\d\d:\d\d:\d\d/, ""))).toEqual([
      "Approved without asking anyone",
    ]);
    const facts = screen.getByRole("complementary", { name: "About this step" });
    expect(within(facts).getByText("Approved by setting")).toHaveClass("tone-idle");
    // Its row says the same, in no colour: no one looked.
    const row = within(screen.getByRole("table", { name: "Steps" })).getAllByRole("row")[1];
    expect(within(row).getByText("Approved by setting")).toHaveClass("tone-idle");
    // In the words of the task's Details. The fixture's setting is now "a user", so its source is not claimed.
    expect(facts).toHaveTextContent(/Decided by\s*Foreman approves merges/);
    expect(facts).toHaveTextContent(/Next\s*Merge/);
    expect(facts).not.toHaveTextContent("Took");
    expect(facts).not.toHaveTextContent("Spend");
  });

  it("says when nothing has run", async () => {
    await renderTask(`${BASE}/activity`, taskRoutes({ runs: [] }));
    expect(await screen.findByText("Nothing has run on this task yet.")).toBeInTheDocument();
  });
});

describe("the page keeps its parts apart", () => {
  it("gives every decision one shape: the question, then its facts on the line below", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles/task.css"), "utf8");
    const body = css.match(/\.decision__body\s*\{([^}]*)\}/)[1];
    expect(body).toMatch(/flex-direction: column;/);
    expect(body).not.toMatch(/flex-wrap/);
  });

  it("reads checks and changes once on load", async () => {
    const { fetchImpl } = await renderTask();
    await screen.findByRole("region", { name: "Approve the merge into main?" });
    expect(calls(fetchImpl, "GET", CHECKS_URL.slice(4))).toHaveLength(1);
    expect(calls(fetchImpl, "GET", CHANGES_URL.slice(4))).toHaveLength(1);
  });
});

describe("details beyond the usual", () => {
  it("names what the task waits for, its size and a priority that was set", async () => {
    const task = taskDetail({
      complexity: "small",
      priority: 2,
      dependencies: [
        { id: "task-a", task_key: "FOR-11", title: "Record the result line", status: "done" },
        { id: "task-b", task_key: "FOR-12", title: "Time the test step", status: "todo" },
        { id: "task-gone", task_key: null, title: null, status: null },
      ],
    });
    await renderTask(BASE, taskRoutes({ task }));
    const details = await screen.findByRole("region", { name: "Details" });
    expect(within(details).getByRole("link", { name: /FOR-11 Record the result line/ })).toHaveAttribute("href", "/dashboard/tasks/task-a");
    expect(details).toHaveTextContent(/Record the result line\s*done/);
    expect(details).toHaveTextContent(/Time the test step\s*queued/i);
    expect(details).toHaveTextContent("A task that no longer exists");
    expect(details).toHaveTextContent(/Size\s*Small/);
    expect(details).toHaveTextContent(/Priority\s*2/);
  });

  it("shows every detail at once, leaving out rows with nothing to say", async () => {
    const task = taskDetail({
      worktree_path: "/srv/foreman/.foreman/worktrees/FOR-14",
      step_visit_counts: { develop: 2, test: 1 },
      totals: { run_count: 4, total_cost_usd: 0.72, token_usage: { input: 1200, output: 34000, cache_read: 2500000 } },
    });
    await renderTask(BASE, taskRoutes({ task }));
    const details = await screen.findByRole("region", { name: "Details" });
    expect(details).not.toHaveTextContent("Depends on");
    expect(details).not.toHaveTextContent("Priority");
    // Nothing behind a control: the working copy and tokens are there at once.
    expect(within(details).queryByRole("button", { name: "More details" })).toBeNull();
    expect(details).toHaveTextContent("/srv/foreman/.foreman/worktrees/FOR-14");
    expect(details).toHaveTextContent("1.2K in · 34K out · 2.5M cached");
    // How often each step ran is the Steps table's Attempts column, not a detail.
    expect(details).not.toHaveTextContent("Times at each step");
    expect(details).not.toHaveTextContent("Develop 2 · Test 1");
  });
});

describe("The agent's side bar", () => {
  const working = () => [runItem("run-9", "develop", { status: "running", outcome: null, finished_at: null })];
  const IN_PROGRESS = { status: "in_progress", blocked_kind: null };
  const button = () => within(screen.getByRole("banner")).getByRole("button", { name: "Agent" });
  const bar = () => screen.findByRole("complementary", { name: "Agent" });
  const noBar = () => expect(screen.queryByRole("complementary", { name: "Agent" })).toBeNull();

  beforeEach(() => window.localStorage.clear());

  async function open(runs, task = IN_PROGRESS, path = BASE) {
    const routes = taskRoutes({ task: taskDetail(task), runs });
    routes[outputUrl("run-9")] = outputPayload("run-9", "Reading the parser.");
    const utils = await renderTask(path, routes);
    // Closed until the user opens it (owner, 2026-11-24).
    noBar();
    fireEvent.click(button());
    return { ...utils, panel: await bar() };
  }

  it("has the manager's place on a task page, closed until asked for when nothing runs", async () => {
    await renderTask();
    expect(within(screen.getByRole("banner")).queryByRole("button", { name: "Manager" })).toBeNull();
    expect(button()).toHaveAttribute("aria-pressed", "false");
    noBar();

    fireEvent.click(button());
    const panel = await bar();
    expect(within(panel).getByRole("heading", { name: "Agent" })).toBeInTheDocument();
    // Oldest first, and the last step an agent or the engine did is open.
    const steps = await within(panel).findAllByRole("button", { expanded: false });
    expect(steps.map((step) => step.textContent)).toEqual([expect.stringMatching(/^Test/)]);
    expect(within(panel).getByRole("button", { expanded: true })).toHaveTextContent(/^ReviewApprove/);
    expect(await within(panel).findByText("Reviewed the change.")).toBeInTheDocument();
    expect(within(panel).queryByText("Ran 1221 tests")).toBeNull();

    // Any step opens and closes.
    fireEvent.click(steps[0]);
    expect(await within(panel).findByText("Ran 1221 tests")).toBeInTheDocument();
    fireEvent.click(button());
    noBar();
  });

  it("is closed while a step is in progress until the user opens it, then on what that step is doing", async () => {
    const routes = taskRoutes({ task: taskDetail(IN_PROGRESS), runs: working() });
    // The step's own line says how it started; a user's words have their own place.
    routes[outputUrl("run-9")] = outputPayload("run-9", "Reading the parser.", {
      transcript: [
        { at: "2026-11-11T08:00:00Z", kind: "workflow.step_started", text: "", data: { step: "develop" } },
        { at: "2026-11-11T08:00:01Z", kind: "agent.started", text: "", data: { command: "claude --print" } },
        { at: "2026-11-11T08:00:02Z", kind: "human.message", text: "", data: { text: "Mind the cache." } },
        { at: "2026-11-11T08:00:03Z", kind: "agent.message", text: "", data: { phase: "assistant", text: "Reading the parser." } },
      ],
    });
    await renderTask(BASE, routes);
    // Nothing opens it on its own, not even a step at work.
    expect(button()).toHaveAttribute("aria-pressed", "false");
    noBar();
    fireEvent.click(button());
    const panel = await bar();
    expect(panel).toHaveTextContent("Develop is running");
    expect(await within(panel).findByText("Reading the parser.")).toBeInTheDocument();
    const story = within(panel).getByRole("list", { name: "What develop did" });
    expect(within(story).getAllByRole("listitem")).toHaveLength(1);
    expect(button()).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(button());
    noBar();
  });

  it("stays as the user left it, on every task and on the next visit, apart from the manager's", async () => {
    const view = await renderTask();
    noBar();
    fireEvent.click(button());
    await bar();
    expect(window.localStorage.getItem("foreman.dashboard.agent.open")).toBe("true");
    // The manager's side bar is remembered on its own.
    expect(window.localStorage.getItem("foreman.dashboard.manager.open")).toBeNull();
    view.unmount();

    // Opened, it is open on the next visit.
    const again = await renderTask();
    expect(await bar()).toBeInTheDocument();
    fireEvent.click(button());
    noBar();
    expect(window.localStorage.getItem("foreman.dashboard.agent.open")).toBe("false");
    again.unmount();

    // Closed, it stays closed, even on a task with a step at work.
    await renderTask(BASE, taskRoutes({ task: taskDetail(IN_PROGRESS), runs: working() }));
    expect(button()).toHaveAttribute("aria-pressed", "false");
    noBar();
  });

  it("reads a running step again as it prints", async () => {
    const { fetchImpl, panel } = await open(working());
    await within(panel).findByText("Reading the parser.");
    const reads = () => calls(fetchImpl, "GET", "/api/v1/runs/run-9/output").length;
    const before = reads();
    fetchImpl.routes[outputUrl("run-9")] = outputPayload("run-9", "Editing the parser.");
    const source = fetchImpl.EventSource.sources.find((entry) => entry.url === "/api/v1/projects/foreman/stream");
    source.emit({ type: "event", event: { id: "e1", event_type: "agent.message", task_id: "another-task" } });
    source.emit({ type: "event", event: { id: "e2", event_type: "agent.message", task_id: TASK_ID } });
    source.emit({ type: "event", event: { id: "e3", event_type: "agent.command", task_id: TASK_ID } });
    expect(await within(panel).findByText("Editing the parser.", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(reads()).toBe(before + 1);
  });

  it("offers to interrupt a step an agent is doing, or to leave the note for its next step", async () => {
    const { panel } = await open(working());
    const box = within(panel).getByRole("form", { name: "Tell the agent" });
    expect(within(box).getByLabelText("Tell the agent (Develop is running)")).toBeInTheDocument();
    expect(within(box).getByRole("button", { name: "Interrupt and tell it now" })).toBeInTheDocument();
    expect(within(box).getByRole("button", { name: "Save for the developer" })).toBeInTheDocument();
    // It is the only such box on the page, on every tab.
    expect(screen.getAllByRole("form", { name: "Tell the agent" })).toHaveLength(1);
  });

  it("is the only box for it on the Activity tab too", async () => {
    await open(working(), IN_PROGRESS, `${BASE}/activity`);
    await screen.findByRole("table", { name: "Steps" });
    expect(screen.getAllByRole("form", { name: "Tell the agent" })).toHaveLength(1);
    expect(screen.queryByRole("list", { name: "Told the agent" })).toBeNull();
  });

  it("with no step in progress, a note can only be saved for the next one", async () => {
    const { fetchImpl, panel } = await open([runItem("run-9", "develop")]);
    fetchImpl.routes[post("messages")] = { status: "recorded", message: "Recorded. The next agent step for this task will read it." };
    const box = within(panel).getByRole("form", { name: "Tell the agent" });
    expect(within(box).queryByRole("button", { name: "Interrupt and tell it now" })).toBeNull();
    fireEvent.click(within(box).getByRole("button", { name: "Save for the developer" }));
    expect(await within(box).findByRole("alert")).toHaveTextContent("Write what to tell it first.");
    fireEvent.change(within(box).getByRole("textbox", { name: "Tell the agent" }), { target: { value: "Count skipped tests." } });
    fireEvent.click(within(box).getByRole("button", { name: "Save for the developer" }));
    expect(await within(box).findByRole("status")).toHaveTextContent("The next agent step for this task will read it.");
    expect(calls(fetchImpl, "POST", `/api/v1/tasks/${TASK_ID}/messages`)[0].body).toEqual({ text: "Count skipped tests." });
  });

  it("takes a note before any agent has worked on the task", async () => {
    await renderTask(BASE, taskRoutes({ task: taskDetail({ status: "todo", blocked_kind: null }), runs: [] }));
    fireEvent.click(button());
    const panel = await bar();
    expect(await within(panel).findByText("No agent has worked on this task yet.")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Save for the developer" })).toBeInTheDocument();
  });

  it("leaves out the runs that only record that the task was filed or planned", async () => {
    const runs = [runItem("run-9", "develop"), runItem("run-file", "file", { backend: "engine", outcome: "file" })];
    const { panel } = await open(runs);
    const thread = within(panel).getByRole("list", { name: "Steps and what was said" });
    expect(Array.from(thread.children).map((item) => item.textContent)).toEqual([expect.stringMatching(/^DevelopDone/)]);
  });

  it("shows a finished task's steps and takes no more notes", async () => {
    const routes = taskRoutes({ task: taskDetail({ status: "done", blocked_kind: null }), runs: [runItem("run-9", "develop")] });
    routes[outputUrl("run-9")] = outputPayload("run-9", "Done.");
    await renderTask(BASE, routes);
    fireEvent.click(button());
    const panel = await bar();
    expect(await within(panel).findByText("Done.")).toBeInTheDocument();
    expect(within(panel).queryByRole("form", { name: "Tell the agent" })).toBeNull();
  });

  it("shows what a user said where it was said, and whether it was read", async () => {
    const { panel } = await open(
      [
        runItem("run-9", "develop", { status: "running", outcome: null, finished_at: null, started_at: "2026-11-11T08:00:00Z" }),
        runItem("run-8", "develop", { outcome: "error", started_at: "2026-11-10T09:30:00Z" }),
      ],
      {
        ...IN_PROGRESS,
        guidance: [
          { event_id: "e1", text: "Earlier advice.", recorded_at: "2026-11-10T09:00:00Z", delivered: true, delivered_at: "2026-11-10T10:00:00Z", delivered_role: "developer", delivered_step: "develop" },
          { event_id: "e2", text: "Newer advice.", recorded_at: "2026-11-11T09:00:00Z", delivered: false, delivered_at: null, delivered_role: null, delivered_step: null },
        ],
      },
    );
    const thread = within(panel).getByRole("list", { name: "Steps and what was said" });
    const order = Array.from(thread.children).map((item) => item.textContent);
    expect(order).toHaveLength(4);
    expect(order[0]).toMatch(/Earlier advice\.Read by the agent at develop on 10 Nov/);
    expect(order[1]).toMatch(/^DevelopFailed/);
    expect(order[2]).toMatch(/^DevelopRunning/);
    expect(order[3]).toMatch(/Newer advice\.Waiting for the developer.s next step/);
  });

  it("interrupts the step with the note and says what is happening", async () => {
    const { fetchImpl, panel } = await open(working());
    fetchImpl.routes[post("steer")] = { status: "interrupting", message: "Recorded. The develop step is being interrupted and starts again with this guidance." };
    const box = within(panel).getByRole("form", { name: "Tell the agent" });
    fireEvent.change(within(box).getByRole("textbox"), { target: { value: " Use the existing parser. " } });
    fireEvent.click(within(box).getByRole("button", { name: "Interrupt and tell it now" }));

    await waitFor(() => expect(calls(fetchImpl, "POST", `/api/v1/tasks/${TASK_ID}/steer`)).toHaveLength(1));
    expect(calls(fetchImpl, "POST", `/api/v1/tasks/${TASK_ID}/steer`)[0].body).toEqual({ text: "Use the existing parser." });
    expect(await within(box).findByRole("status")).toHaveTextContent("is being interrupted and starts again");
    expect(within(box).getByRole("textbox")).toHaveValue("");
  });

  it("saves the note for the next step without interrupting", async () => {
    const { fetchImpl, panel } = await open(working());
    fetchImpl.routes[post("messages")] = { status: "recorded", message: "Recorded. The next agent step for this task will read it." };
    const box = within(panel).getByRole("form", { name: "Tell the agent" });
    fireEvent.change(within(box).getByRole("textbox"), { target: { value: "Later is fine." } });
    fireEvent.click(within(box).getByRole("button", { name: "Save for the developer" }));

    await waitFor(() => expect(calls(fetchImpl, "POST", `/api/v1/tasks/${TASK_ID}/messages`)).toHaveLength(1));
    expect(calls(fetchImpl, "POST", `/api/v1/tasks/${TASK_ID}/steer`)).toHaveLength(0);
  });

  it("shows the refusal when there is nothing to interrupt, and asks for words first", async () => {
    const { fetchImpl, panel } = await open(working());
    fetchImpl.routes[post("steer")] = reply(400, { error: "No agent is running on this task, so there is nothing to interrupt.", code: "validation_error" });
    const box = within(panel).getByRole("form", { name: "Tell the agent" });
    fireEvent.click(within(box).getByRole("button", { name: "Interrupt and tell it now" }));
    expect(await within(box).findByRole("alert")).toHaveTextContent("Write what to tell it first.");
    fireEvent.change(within(box).getByRole("textbox"), { target: { value: "Stop." } });
    fireEvent.click(within(box).getByRole("button", { name: "Interrupt and tell it now" }));
    expect(await within(box).findByRole("alert")).toHaveTextContent("nothing to interrupt");
  });
});
