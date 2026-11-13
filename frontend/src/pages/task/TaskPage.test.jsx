import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp, reply } from "../../testing/fakeApi";
import {
  BUILTINS_DIFF,
  CHANGES_URL,
  changesPayload,
  CHECKS_URL,
  checksPayload,
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
    });
    await waitFor(() => expect(taskReads(fetchImpl)).toBeGreaterThan(1));
  });
});

describe("the decision", () => {
  it("asks to approve the merge with the facts, and approving calls approve and reloads", async () => {
    const routes = taskRoutes();
    routes[post("approve")] = { status: "approved", message: "Decision recorded. The engine continues from `merge`." };
    const { fetchImpl } = await renderTask(BASE, routes);
    const region = await screen.findByRole("region", { name: "Approve the merge into main?" });
    await waitFor(() => expect(region).toHaveTextContent("Tests passed in 114.2 s at b232eb1"));
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

  it("asks to accept filed work; Accept calls accept and Decline calls decline with the reason", async () => {
    const task = taskDetail({
      status: "triage",
      in_backlog: true,
      awaiting_human_gate: false,
      gate_policy: null,
      blocked_kind: null,
      workflow_current_step: null,
      source: { system: "github", external_ref: "#42", url: "https://example.test/42", reporter: "ana" },
      runs: [],
    });
    const routes = taskRoutes({ task });
    routes[post("accept")] = task;
    routes[post("decline")] = task;
    const { fetchImpl } = await renderTask(BASE, routes);
    const region = await screen.findByRole("region", { name: "Accept this task?" });
    expect(region).toHaveTextContent("Filed by ana via github on 10 Nov");
    expect(within(region).getByRole("link", { name: "#42" })).toHaveAttribute("href", "https://example.test/42");
    fireEvent.click(within(region).getByRole("button", { name: "Accept" }));
    expect(await screen.findByText("Accepted. It can be planned into a sprint.")).toBeInTheDocument();
    expect(postCalls(fetchImpl, "accept")).toHaveLength(1);

    fireEvent.click(within(region).getByRole("button", { name: "Decline" }));
    const dialog = screen.getByRole("dialog", { name: "Decline this task" });
    fireEvent.change(within(dialog).getByLabelText("Why it is declined"), { target: { value: "Out of scope." } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Decline" }));
    expect(await screen.findByText("Declined.")).toBeInTheDocument();
    expect(postCalls(fetchImpl, "decline")[0].body).toEqual({ reason: "Out of scope." });
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
    expect(region).toHaveTextContent("Stopped at test");
    expect(region).toHaveTextContent("Last run: Test, failed by engine");
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

describe("the More menu", () => {
  function openMore() {
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    return screen.getByRole("menu", { name: "Task actions" });
  }

  it.each([
    ["running", { status: "in_progress", workflow_current_step: "develop" }, ["Stop", "Block", "Cancel", "Delete"]],
    ["queued", { status: "todo" }, ["Run next", "Block", "Cancel", "Delete"]],
    ["blocked by the engine", { status: "blocked", blocked_kind: "engine" }, ["Unblock", "Cancel", "Delete"]],
    ["at a gate", {}, ["Cancel", "Delete"]],
    ["in the backlog", { status: "todo", in_backlog: true }, ["Cancel", "Delete"]],
    ["done", { status: "done" }, ["Delete"]],
  ])("holds what exists for a task that is %s", async (_, fields, labels) => {
    await renderTask(BASE, taskRoutes({ task: taskDetail(fields) }));
    expect(within(openMore()).getAllByRole("menuitem").map((item) => item.textContent)).toEqual(labels);
  });

  it.each([
    ["Stop", "stop", { status: "in_progress" }, null, {}, "Stop requested. The task is blocked when the engine acts on it."],
    ["Block", "block", { status: "todo" }, "Why it is blocked", { reason: "Waiting for a key." }, "Blocked."],
    ["Unblock", "unblock", { status: "blocked", blocked_kind: "engine" }, "Guidance for the agent", { note: "Waiting for a key." }, "Unblocked. The task is back in the queue."],
    ["Cancel", "cancel", { status: "todo" }, null, undefined, "Cancelled."],
  ])("%s is confirmed, calls its endpoint, and shows a refusal", async (label, action, fields, ask, body, done) => {
    const routes = taskRoutes({ task: taskDetail(fields) });
    let refuse = true;
    routes[post(action)] = () => (refuse ? reply(400, { error: `Cannot ${action} this task`, code: "invalid_request" }) : { ok: true });
    const { fetchImpl } = await renderTask(BASE, routes);
    fireEvent.click(within(openMore()).getByRole("menuitem", { name: label }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAccessibleDescription(/./);
    expect(postCalls(fetchImpl, action)).toHaveLength(0);
    if (ask) fireEvent.change(within(dialog).getByLabelText(ask), { target: { value: "Waiting for a key." } });
    const confirm = within(dialog).getByRole("button", { name: `${label} task` });
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
    fireEvent.click(within(openMore()).getByRole("menuitem", { name: "Run next" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Run this task next" })).getByRole("button", { name: "Run next" }));
    expect(await screen.findByText("Requested. The task starts when the engine picks the request up.")).toBeInTheDocument();
    expect(fetchImpl.calls.filter((call) => `${call.method} ${call.url}` === url)[0].body).toEqual({ task_id: TASK_ID });
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
      ["Develop", "Committed b232eb1", "sonnet-5-5", "1"],
      ["Test", "Passed in 114.2 s", "engine", "1"],
      ["Review", "Approved in 7 s", "sonnet-5-5", "1"],
      ["Merge approval", "Waiting for you", "a person", ""],
      ["Merge", "Not reached", "engine", ""],
    ]);
    expect(screen.getByText(/4 runs in all/)).toBeInTheDocument();
  });

  it("sums up the checks on one line that links to Checks", async () => {
    await renderTask();
    const section = (await screen.findByRole("heading", { name: "Checks" })).closest("section");
    await waitFor(() => expect(section).toHaveTextContent("1 of 2 acceptance criteria marked met by haiku-5-5"));
    expect(section).toHaveTextContent("Tests passed in 114.2 s at b232eb1");
    expect(section).toHaveTextContent("No evidence files required by this workflow");
    expect(within(section).getByRole("link", { name: "All checks" })).toHaveAttribute("href", `${BASE}/checks`);
  });

  it("shows the details and the task as filed", async () => {
    await renderTask();
    const details = await screen.findByRole("complementary", { name: "Details" });
    await waitFor(() => expect(details).toHaveTextContent(/Workflow\s*development/));
    expect(details).toHaveTextContent(/Stage\s*Waiting for merge approval/);
    expect(within(details).getByRole("link", { name: "Sprint 56: engine truthfulness" })).toHaveAttribute("href", "/dashboard/sprints/sprint-56");
    expect(details).toHaveTextContent("A person approves merges (project setting)");
    expect(details).not.toHaveTextContent("plans");
    expect(details).toHaveTextContent(/Branch\s*foreman\/for-14/);
    expect(details).toHaveTextContent("$0.72 · 4 runs");
    expect(details).toHaveTextContent(/Filed by\s*a person on 10 Nov/);
    expect(details).toHaveTextContent("It should say how long and what the runner printed.");
    expect(details).toHaveTextContent("The result line is reported");
  });

  it("saves guidance through the messages endpoint and shows whether the agent read it", async () => {
    const task = taskDetail({
      guidance: [
        { event_id: "e1", text: "Earlier advice.", recorded_at: "2026-11-10T09:00:00Z", delivered: true, delivered_at: "2026-11-10T10:00:00Z", delivered_role: "developer", delivered_step: "develop" },
        { event_id: "e2", text: "Newer advice.", recorded_at: "2026-11-11T09:00:00Z", delivered: false, delivered_at: null, delivered_role: null, delivered_step: null },
      ],
    });
    const routes = taskRoutes({ task });
    routes[post("messages")] = { status: "recorded", message: "Recorded. The next agent step for this task will read it." };
    const { fetchImpl } = await renderTask(BASE, routes);
    const notes = await screen.findByRole("list", { name: "Guidance written" });
    const items = within(notes).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Newer advice.");
    expect(items[0]).toHaveTextContent("Waiting for the next agent step");
    expect(items[1]).toHaveTextContent(/Read by the agent at develop on 10 Nov/);

    const field = screen.getByRole("textbox", { name: "Guidance for the next agent step" });
    fireEvent.click(screen.getByRole("button", { name: "Save guidance" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Write the guidance first.");
    fireEvent.change(field, { target: { value: "Count skipped tests." } });
    const before = taskReads(fetchImpl);
    fireEvent.click(screen.getByRole("button", { name: "Save guidance" }));
    expect(await screen.findByText("Recorded. The next agent step for this task will read it.")).toBeInTheDocument();
    expect(postCalls(fetchImpl, "messages")[0].body).toEqual({ text: "Count skipped tests." });
    expect(field).toHaveValue("");
    await waitFor(() => expect(taskReads(fetchImpl)).toBeGreaterThan(before));
  });

  it("refreshes from the sprint stream while a step runs", async () => {
    const { fetchImpl } = await renderTask(BASE, taskRoutes({ task: taskDetail({ status: "in_progress", workflow_current_step: "develop", awaiting_human_gate: false, gate_policy: null, blocked_kind: null }) }));
    const [source] = fetchImpl.EventSource.sources;
    expect(source.url).toBe("/api/v1/sprints/sprint-56/stream");
    const before = taskReads(fetchImpl);
    source.emit({ type: "event", event: { id: "e9", task_id: "another-task" } });
    source.emit({ type: "event", event: { id: "e10", task_id: TASK_ID } });
    source.emit({ type: "event", event: { id: "e11", task_id: TASK_ID } });
    await waitFor(() => expect(taskReads(fetchImpl)).toBe(before + 1));
  });

  it("opens no stream when nothing runs", async () => {
    const { fetchImpl } = await renderTask();
    expect(fetchImpl.EventSource.sources).toHaveLength(0);
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
    expect(within(section).getByLabelText("Model for develop")).toHaveValue("");
    expect(within(section).getByLabelText("Model for review")).toBeInTheDocument();
    expect(within(section).queryByLabelText("Model for test")).toBeNull();
  });

  it("sets who decides and a step's model with one PATCH, keeping what else the task carries", async () => {
    const task = taskDetail({ executor_overrides: { ladder_start: 1, policy: { notification: "all" } } });
    const { section, fetchImpl } = await overrides(task);
    fireEvent.change(within(section).getByLabelText("Who decides merge approval"), { target: { value: "auto" } });
    fireEvent.change(within(section).getByLabelText("Model for develop"), { target: { value: " opus-5-5 " } });
    fireEvent.click(within(section).getByRole("button", { name: "Save overrides" }));
    await waitFor(() => expect(calls(fetchImpl, "PATCH", PATCH)).toHaveLength(1));
    expect(calls(fetchImpl, "PATCH", PATCH)[0].body).toEqual({
      executor_overrides: {
        ladder_start: 1,
        policy: { notification: "all", merge_approval: "auto" },
        models: { develop: "opus-5-5" },
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
    fireEvent.change(within(section).getByLabelText("Model for develop"), { target: { value: "x" } });
    fireEvent.click(within(section).getByRole("button", { name: "Save overrides" }));
    expect(await within(section).findByRole("alert")).toHaveTextContent("Unknown workflow step 'develop' in executor_overrides.models.");
  });

  it("names this task as the source in Details once the task says so", async () => {
    const task = taskDetail({
      executor_overrides: { policy: { merge_approval: "auto" } },
      policy: { ...taskDetail().policy, merge_approval: { value: "auto", source: "task_override" } },
    });
    await overrides(task);
    const details = await screen.findByRole("complementary", { name: "Details" });
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
    const facts = await screen.findByRole("table", { name: "Measured by the engine" });
    const claims = screen.getByRole("table", { name: "Reported by an agent" });
    const firstCells = (table) =>
      within(table)
        .getAllByRole("row")
        .slice(1)
        .map((row) => within(row).getAllByRole("cell")[0].textContent);
    expect(firstCells(facts)).toEqual(["Tests", "Branch", "Size of change"]);
    expect(firstCells(claims)).toEqual(["Review", "Criterion 1", "Criterion 2"]);
    expect(facts).toHaveTextContent("Ran 1221 tests in 114.2s OK");
    expect(facts).toHaveTextContent("Up to date with main");
    expect(facts).toHaveTextContent("3 files, +118 −7");
    expect(facts).not.toHaveTextContent("Review");
    expect(claims).toHaveTextContent("Approved");
    expect(claims).toHaveTextContent("Clean change, tests cover it.");
    expect(claims).toHaveTextContent("Partly met");
    expect(claims).not.toHaveTextContent("Size of change");
    expect(screen.getByText("Claims. Read them as an opinion on the facts above. Criteria judged by haiku-5-5.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evidence files" })).toBeInTheDocument();
    expect(screen.getByText("None required by this workflow.")).toBeInTheDocument();
  });

  it("says when nothing was claimed and the tests did not run", async () => {
    const checks = checksPayload();
    checks.facts.tests = { status: "not_run", exit_code: null, duration_seconds: null, command: null, result_line: null, commit: null, head_sha: null };
    checks.claims = { reviews: [], judged_by: "none", criteria: [] };
    await renderTask(`${BASE}/checks`, taskRoutes({ checks }));
    const facts = await screen.findByRole("table", { name: "Measured by the engine" });
    expect(facts).toHaveTextContent("Not run");
    expect(screen.queryByRole("table", { name: "Reported by an agent" })).toBeNull();
    expect(screen.getByText("No agent has reported on this task yet, and it has no acceptance criteria to judge.")).toBeInTheDocument();
  });
});

describe("Activity", () => {
  it("lists runs newest first and shows the selected run's output and prompt", async () => {
    const { fetchImpl } = await renderTask(`${BASE}/activity`);
    const table = await screen.findByRole("table", { name: "Runs" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[1].textContent)).toEqual(["Review", "Test"]);
    expect(rows[0]).toHaveTextContent("Approved");
    expect(rows[1]).toHaveTextContent("engine");
    // The commit the branch was at after each run; none for the engine's test run.
    expect(rows[0]).toHaveTextContent("b232eb1");
    expect(within(rows[1]).getAllByRole("cell")[4].textContent).toBe("");
    expect(screen.getByText("4 runs, $0.72. Newest first.")).toBeInTheDocument();

    expect(await screen.findByText("Reviewed the change.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Review" })).toBeInTheDocument();
    expect(document.querySelector("#run-output").parentElement).toHaveTextContent(/by sonnet-5-5/);
    fireEvent.click(screen.getByRole("button", { name: "Show the prompt this run was given" }));
    expect(screen.getByText("The prompt of run-3")).toBeInTheDocument();

    fireEvent.click(within(rows[1]).getByRole("button"));
    expect(await screen.findByText("Ran 1221 tests")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Test" })).toBeInTheDocument();
    expect(document.querySelector("#run-output").parentElement).toHaveTextContent(/by engine/);
    expect(within(rows[1]).getByRole("button")).toHaveAttribute("aria-pressed", "true");
    expect(calls(fetchImpl, "GET", outputUrl("run-2").slice(4))).toHaveLength(1);
  });

  it("pages 25 runs at a time with Earlier", async () => {
    const all = Array.from({ length: 30 }, (_, index) => runItem(`run-${index}`, index % 2 ? "test" : "develop"));
    const routes = taskRoutes();
    routes[RUNS_URL] = { runs: all.slice(0, 25), total: 30, limit: 25, offset: 0 };
    routes[`GET /api/v1/tasks/${TASK_ID}/runs?limit=25&offset=25`] = { runs: all.slice(25), total: 30, limit: 25, offset: 25 };
    routes[outputUrl("run-0")] = outputPayload("run-0", "First output", { prompt: null, transcript: [] });
    await renderTask(`${BASE}/activity`, routes);
    const table = await screen.findByRole("table", { name: "Runs" });
    expect(within(table).getAllByRole("row")).toHaveLength(26);
    expect(await screen.findByText("This run recorded no output.")).toBeInTheDocument();
    expect(screen.getByText("No prompt was recorded for this run.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Earlier" }));
    await waitFor(() => expect(within(screen.getByRole("table", { name: "Runs" })).getAllByRole("row")).toHaveLength(31));
    expect(screen.queryByRole("button", { name: "Earlier" })).toBeNull();
  });

  it("says when nothing has run", async () => {
    await renderTask(`${BASE}/activity`, taskRoutes({ runs: [] }));
    expect(await screen.findByText("Nothing has run on this task yet.")).toBeInTheDocument();
  });
});

describe("the page keeps its parts apart", () => {
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
    const details = await screen.findByRole("complementary", { name: "Details" });
    expect(within(details).getByRole("link", { name: /FOR-11 Record the result line/ })).toHaveAttribute("href", "/dashboard/tasks/task-a");
    expect(details).toHaveTextContent(/Record the result line\s*done/);
    expect(details).toHaveTextContent(/Time the test step\s*queued/i);
    expect(details).toHaveTextContent("A task that no longer exists");
    expect(details).toHaveTextContent(/Size\s*Small/);
    expect(details).toHaveTextContent(/Priority\s*2/);
  });

  it("leaves those rows out when there is nothing to say, and keeps the rest behind More details", async () => {
    const task = taskDetail({
      worktree_path: "/srv/foreman/.foreman/worktrees/FOR-14",
      step_visit_counts: { develop: 2, test: 1 },
      totals: { run_count: 4, total_cost_usd: 0.72, token_usage: { input: 1200, output: 34000, cache_read: 2500000 } },
    });
    await renderTask(BASE, taskRoutes({ task }));
    const details = await screen.findByRole("complementary", { name: "Details" });
    expect(details).not.toHaveTextContent("Depends on");
    expect(details).not.toHaveTextContent("Priority");
    expect(details).not.toHaveTextContent("worktrees/FOR-14");
    fireEvent.click(within(details).getByRole("button", { name: "More details" }));
    expect(details).toHaveTextContent("/srv/foreman/.foreman/worktrees/FOR-14");
    expect(details).toHaveTextContent("1.2K in · 34K out · 2.5M read from cache");
    expect(details).toHaveTextContent("Develop 2 · Test 1");
  });
});
