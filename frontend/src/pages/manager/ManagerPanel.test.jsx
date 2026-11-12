import { readFileSync } from "node:fs";
import { join } from "node:path";

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";

import { youAreOn } from "../../app/manager";
import { matchRoute } from "../../app/routes";
import { createFakeFetch, renderApp, reply } from "../../testing/fakeApi";
import { sprintRoutes } from "../../testing/sprintFixture";
import { projectRoutes } from "../../testing/projectFixture";
import { taskDetail, taskRoutes } from "../../testing/taskFixture";
import { workspaceRoutes } from "../../testing/workspaceFixture";
import { QUEUE_URL } from "../../testing/projectFixture";

const readStyles = (name) => readFileSync(join(process.cwd(), "src", "styles", name), "utf8");
const shellCss = readStyles("shell.css");
const managerCss = readStyles("manager.css");

const HISTORY = "GET /api/v1/projects/foreman/meta/history?limit=30";
const MESSAGE = "POST /api/v1/projects/foreman/meta/message";
const SESSION = "DELETE /api/v1/projects/foreman/meta/session";

function turn(id, role, text, tool_uses = []) {
  return { id, role, text, tool_uses, origin: "chat", created_at: "2026-11-11T10:00:00Z" };
}

/** A reply the test writes line by line, like the server does. */
function controlledStream() {
  const encoder = new TextEncoder();
  let controller;
  const body = new ReadableStream({
    start(c) {
      controller = c;
    },
  });
  return {
    response: new Response(body, { status: 200, headers: { "Content-Type": "application/x-ndjson" } }),
    push: (line) => act(async () => controller.enqueue(encoder.encode(`${JSON.stringify(line)}\n`))),
    end: () => act(async () => controller.close()),
  };
}

function withManager(routes, history = { turns: [], has_more: false }) {
  return { ...routes, [HISTORY]: history };
}

function toggle() {
  return within(screen.getByRole("banner")).queryByRole("button", { name: "Manager" });
}

function panel() {
  return screen.getByRole("complementary", { name: "Manager" });
}

beforeEach(() => window.localStorage.clear());

describe("the Manager toggle", () => {
  it.each([
    ["a project page", "/dashboard/projects/foreman", projectRoutes],
    ["a project's Backlog", "/dashboard/projects/foreman/backlog", projectRoutes],
    ["a sprint page", "/dashboard/sprints/sprint-56", sprintRoutes],
    ["a task page", "/dashboard/tasks/task-merge", taskRoutes],
  ])("is in the top bar on %s, not pressed to start with", async (_name, path, routes) => {
    renderApp(path, createFakeFetch(withManager(routes())));
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
    expect(document.querySelector(".manager-slot")).toBeNull();
  });

  it.each([
    ["the workspace", "/dashboard"],
    ["workspace settings", "/dashboard/settings"],
    ["an unknown page", "/dashboard/nope"],
  ])("is not on %s", async (_name, path) => {
    window.localStorage.setItem("foreman.dashboard.manager.open", "true");
    renderApp(path, createFakeFetch(workspaceRoutes()));
    expect(toggle()).toBeNull();
    expect(document.querySelector(".manager-slot")).toBeNull();
  });

  it("opens and closes the side bar, remembers it, and keeps it across pages", async () => {
    const routes = withManager({ ...projectRoutes(), ...sprintRoutes(), ...taskRoutes() });
    const { unmount } = renderApp("/dashboard/projects/foreman", createFakeFetch(routes));
    fireEvent.click(toggle());
    expect(toggle()).toHaveAttribute("aria-pressed", "true");
    expect(within(panel()).getByRole("heading", { name: "Manager" })).toBeInTheDocument();
    expect(window.localStorage.getItem("foreman.dashboard.manager.open")).toBe("true");

    // Project to sprint to task: the same side bar stays open.
    fireEvent.click(await screen.findByRole("link", { name: /Sprint 56/ }));
    await screen.findByRole("heading", { level: 1, name: /Sprint 56/ });
    expect(toggle()).toHaveAttribute("aria-pressed", "true");
    expect(panel()).toBeInTheDocument();

    // A new visit finds it as it was left.
    unmount();
    renderApp("/dashboard/tasks/task-merge", createFakeFetch(routes));
    expect(toggle()).toHaveAttribute("aria-pressed", "true");
    expect(await within(panel()).findByText("You are on: FOR-14")).toBeInTheDocument();

    fireEvent.click(toggle());
    expect(document.querySelector(".manager-slot")).toBeNull();
    expect(window.localStorage.getItem("foreman.dashboard.manager.open")).toBe("false");
  });
});

describe("You are on", () => {
  it("is named from the route", () => {
    const on = (path, loaded) => youAreOn(matchRoute(path).route, loaded);
    expect(on("/dashboard/projects/foreman")).toBe("Sprints");
    expect(on("/dashboard/projects/foreman/backlog")).toBe("Backlog");
    expect(on("/dashboard/projects/foreman/activity")).toBe("Activity");
    expect(on("/dashboard/projects/foreman/settings")).toBe("Settings");
    expect(on("/dashboard/sprints/s/board", { sprint: { title: "Sprint 56: x" } })).toBe("Sprint 56: x");
    expect(on("/dashboard/tasks/t/checks", { task: { task_key: "FOR-14", title: "T" } })).toBe("FOR-14");
    expect(on("/dashboard/tasks/t", { task: { task_key: null, title: "Untitled work" } })).toBe("Untitled work");
    expect(on("/dashboard/sprints/s")).toBeNull();
    expect(on("/dashboard")).toBeNull();
  });

  it("follows the page as the person moves, and the project is named", async () => {
    window.localStorage.setItem("foreman.dashboard.manager.open", "true");
    const routes = withManager({ ...projectRoutes(), ...sprintRoutes(), ...taskRoutes() });
    renderApp("/dashboard/projects/foreman", createFakeFetch(routes));
    expect(await within(panel()).findByText("You are on: Sprints")).toBeInTheDocument();
    expect(await within(panel()).findByText("Foreman")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: /^Backlog/ }));
    expect(await within(panel()).findByText("You are on: Backlog")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Activity" }));
    expect(await within(panel()).findByText("You are on: Activity")).toBeInTheDocument();
  });
});

describe("the conversation", () => {
  async function openAt(path, routes, history) {
    window.localStorage.setItem("foreman.dashboard.manager.open", "true");
    const fetchImpl = createFakeFetch(withManager(routes, history));
    renderApp(path, fetchImpl);
    await within(panel()).findByText(/You are on:/);
    return fetchImpl;
  }

  it("loads the history and offers earlier messages", async () => {
    const older = { turns: [turn("t0", "user", "An older question")], has_more: false };
    const fetchImpl = await openAt("/dashboard/projects/foreman", projectRoutes(), {
      turns: [turn("t1", "user", "Plan the next sprint."), turn("t2", "assistant", "Done.", [{ name: "Bash" }, { name: "Bash" }])],
      has_more: true,
    });
    fetchImpl.routes["GET /api/v1/projects/foreman/meta/history?limit=30&before=t1"] = older;
    const thread = within(panel()).getByRole("log");
    expect(await within(thread).findByText("Plan the next sprint.")).toBeInTheDocument();
    expect(within(thread).getByText("Done.")).toBeInTheDocument();
    expect(within(thread).getByText("Ran Bash ×2.")).toBeInTheDocument();
    fireEvent.click(within(thread).getByRole("button", { name: "Earlier messages" }));
    expect(await within(thread).findByText("An older question")).toBeInTheDocument();
    expect(within(thread).queryByRole("button", { name: "Earlier messages" })).toBeNull();
  });

  it("sends a message with the page, and the reply grows as it is written, with a cursor", async () => {
    const stream = controlledStream();
    const routes = taskRoutes();
    const fetchImpl = await openAt("/dashboard/tasks/task-merge", routes);
    fetchImpl.routes[MESSAGE] = () => stream.response;
    const box = within(panel()).getByRole("textbox", { name: "Message to the manager" });
    fireEvent.change(box, { target: { value: "Is this safe to merge?" } });
    fireEvent.click(within(panel()).getByRole("button", { name: "Send" }));

    const thread = within(panel()).getByRole("log");
    expect(await within(thread).findByText("Is this safe to merge?")).toBeInTheDocument();
    expect(box).toHaveValue("");
    const call = fetchImpl.calls.find((entry) => entry.method === "POST" && entry.url.endsWith("/meta/message"));
    expect(call.body).toEqual({ message: "Is this safe to merge?", context: { page: "FOR-14", task_id: "task-merge" } });

    // Nothing yet but the cursor.
    expect(document.querySelector(".manager__cursor")).not.toBeNull();
    await stream.push({ type: "text_delta", text: "It touches " });
    expect(await within(thread).findByText(/It touches/)).toBeInTheDocument();
    expect(within(thread).queryByText(/the engine/)).toBeNull();
    expect(within(panel()).getByRole("button", { name: "Replying" })).toBeDisabled();
    await stream.push({ type: "text_delta", text: "the engine only." });
    expect(await within(thread).findByText("It touches the engine only.")).toBeInTheDocument();
    expect(document.querySelector(".manager__cursor")).not.toBeNull();

    await stream.push({ type: "done", session_id: "s1" });
    await stream.end();
    await waitFor(() => expect(document.querySelector(".manager__cursor")).toBeNull());
    expect(within(panel()).getByRole("button", { name: "Send" })).toBeDisabled(); // empty draft
  });

  it("sends with Enter and keeps a new line for Shift+Enter", async () => {
    const stream = controlledStream();
    const fetchImpl = await openAt("/dashboard/projects/foreman", projectRoutes());
    fetchImpl.routes[MESSAGE] = () => stream.response;
    const box = within(panel()).getByRole("textbox", { name: "Message to the manager" });
    fireEvent.change(box, { target: { value: "Hello" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(fetchImpl.calls.some((entry) => entry.url.endsWith("/meta/message"))).toBe(false);
    fireEvent.keyDown(box, { key: "Enter" });
    expect(await within(panel()).findByText("Hello")).toBeInTheDocument();
    const call = fetchImpl.calls.find((entry) => entry.url.endsWith("/meta/message"));
    expect(call.body.context).toEqual({ page: "Sprints" });
    await stream.end();
  });

  it("shows a failed reply as a sentence with Retry, which sends the message again", async () => {
    const fetchImpl = await openAt("/dashboard/projects/foreman", projectRoutes());
    const first = controlledStream();
    fetchImpl.routes[MESSAGE] = () => first.response;
    const box = within(panel()).getByRole("textbox", { name: "Message to the manager" });
    fireEvent.change(box, { target: { value: "Plan a sprint" } });
    fireEvent.click(within(panel()).getByRole("button", { name: "Send" }));
    await first.push({ type: "text_delta", text: "Let me look" });
    await first.push({ type: "error", message: "Claude Code CLI not found" });
    await first.end();

    const alert = await within(panel()).findByRole("alert");
    expect(alert).toHaveTextContent("Claude Code CLI not found.");
    expect(within(panel()).getByText("Let me look")).toBeInTheDocument();

    const second = controlledStream();
    fetchImpl.routes[MESSAGE] = () => second.response;
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    await second.push({ type: "text_delta", text: "Here is a plan." });
    await second.push({ type: "done", session_id: "s" });
    await second.end();
    expect(await within(panel()).findByText("Here is a plan.")).toBeInTheDocument();
    expect(within(panel()).queryByRole("alert")).toBeNull();
    expect(within(panel()).getAllByText("Plan a sprint")).toHaveLength(1);
    const sends = fetchImpl.calls.filter((entry) => entry.url.endsWith("/meta/message"));
    expect(sends.map((entry) => entry.body.message)).toEqual(["Plan a sprint", "Plan a sprint"]);
  });

  it("says why when the server refuses the message", async () => {
    const fetchImpl = await openAt("/dashboard/projects/foreman", projectRoutes());
    fetchImpl.routes[MESSAGE] = reply(403, { error: "The manager is off for this dashboard", code: "forbidden" });
    fireEvent.change(within(panel()).getByRole("textbox", { name: "Message to the manager" }), { target: { value: "hi" } });
    fireEvent.click(within(panel()).getByRole("button", { name: "Send" }));
    expect(await within(panel()).findByRole("alert")).toHaveTextContent("The manager is off for this dashboard.");
    expect(within(panel()).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("treats a reply that stops without finishing as a failure", async () => {
    const fetchImpl = await openAt("/dashboard/projects/foreman", projectRoutes());
    const stream = controlledStream();
    fetchImpl.routes[MESSAGE] = () => stream.response;
    fireEvent.change(within(panel()).getByRole("textbox", { name: "Message to the manager" }), { target: { value: "hi" } });
    fireEvent.click(within(panel()).getByRole("button", { name: "Send" }));
    await stream.push({ type: "text_delta", text: "Half" });
    await stream.end();
    expect(await within(panel()).findByRole("alert")).toHaveTextContent("The reply stopped before it was finished.");
  });

  it("clears the conversation only after a confirmation", async () => {
    const fetchImpl = await openAt("/dashboard/projects/foreman", projectRoutes(), {
      turns: [turn("t1", "user", "Plan the next sprint."), turn("t2", "assistant", "Done.")],
      has_more: false,
    });
    fetchImpl.routes[SESSION] = { project_id: "foreman", cleared: true };
    await within(panel()).findByText("Done.");
    fireEvent.click(within(panel()).getByRole("button", { name: "Start a new conversation" }));
    const dialog = screen.getByRole("dialog", { name: "Start a new conversation?" });
    expect(dialog).toHaveTextContent("2 messages");
    expect(fetchImpl.calls.some((entry) => entry.method === "DELETE")).toBe(false);

    fireEvent.click(within(dialog).getByRole("button", { name: "Keep it as it is" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(within(panel()).getByText("Done.")).toBeInTheDocument();

    fireEvent.click(within(panel()).getByRole("button", { name: "Start a new conversation" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Start a new conversation" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(fetchImpl.calls.filter((entry) => entry.method === "DELETE").map((entry) => entry.url)).toEqual([
      "/api/v1/projects/foreman/meta/session",
    ]);
    expect(within(panel()).queryByText("Done.")).toBeNull();
    expect(within(panel()).getByText(/No conversation yet/)).toBeInTheDocument();
  });

  it("closes from the panel", async () => {
    await openAt("/dashboard/projects/foreman", projectRoutes());
    fireEvent.click(within(panel()).getByRole("button", { name: "Close" }));
    expect(document.querySelector(".manager-slot")).toBeNull();
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
  });
});

describe("the narrow layout", () => {
  it("covers the page below the width where both fit, with a close control shown only there", () => {
    expect(shellCss).toMatch(/@media \(max-width: 960px\)\s*\{\s*\.manager-slot\s*\{[^}]*position: fixed;/);
    expect(shellCss).toMatch(/\.manager-slot\s*\{[^}]*position: sticky;[^}]*flex: 0 0 var\(--manager-width\)/);
    expect(managerCss).toMatch(/\.manager \.manager__close\s*\{\s*display: none;/);
    expect(managerCss).toMatch(/@media \(max-width: 960px\)\s*\{\s*\.manager \.manager__close\s*\{\s*display: inline-flex;/);
  });
});

// ── Proposals (ADR-0022) ─────────────────────────────────────────────────

const PROPOSAL_ID = "prop-1";
const PROPOSAL_URL = `GET /api/v1/proposals/${PROPOSAL_ID}`;
const CONFIRM_URL = `POST /api/v1/proposals/${PROPOSAL_ID}/confirm`;
const DECLINE_URL = `POST /api/v1/proposals/${PROPOSAL_ID}/decline`;

function proposal(fields = {}) {
  return {
    id: PROPOSAL_ID,
    project_id: "foreman",
    state: "proposed",
    proposed_by: "manager",
    reason: "The two fixes touch leasing; the JSON output can wait.",
    operations: [
      { kind: "plan_tasks", task_ids: ["task-a", "task-b"], new_sprint: { title: "Sprint 57" } },
      { kind: "send_back", task_id: "task-merge", guidance: "Report skipped tests too." },
    ],
    leaves: ["task-c"],
    names: {
      tasks: {
        "task-a": { key: "FOR-20", title: "Resume a stale agent step in place" },
        "task-b": { key: "FOR-21", title: "Check the lease fencing token on writes" },
        "task-c": { key: "FOR-22", title: "JSON output on the remaining read commands" },
        "task-merge": { key: "FOR-14", title: "Report the test result line" },
      },
      sprints: {},
    },
    created_at: "2026-11-12T10:00:00Z",
    decided_by: null,
    decided_at: null,
    outcome: null,
    ...fields,
  };
}

function card() {
  return within(panel()).getByText(/^Proposed change\./).closest(".proposal");
}

describe("a proposal in the conversation", () => {
  async function openWith(routes, history) {
    window.localStorage.setItem("foreman.dashboard.manager.open", "true");
    const fetchImpl = createFakeFetch(withManager(routes, history));
    renderApp("/dashboard/projects/foreman", fetchImpl);
    await within(panel()).findByText(/You are on:/);
    return fetchImpl;
  }

  const queueLoads = (fetchImpl) => fetchImpl.calls.filter((call) => `GET ${call.url}` === QUEUE_URL).length;

  it("arrives on the stream as a card saying what will be created, changed and left", async () => {
    const stream = controlledStream();
    const fetchImpl = await openWith({ ...projectRoutes(), [PROPOSAL_URL]: proposal() });
    fetchImpl.routes[MESSAGE] = () => stream.response;
    fireEvent.change(within(panel()).getByRole("textbox", { name: "Message to the manager" }), { target: { value: "Plan the next sprint." } });
    fireEvent.click(within(panel()).getByRole("button", { name: "Send" }));
    await stream.push({ type: "text_delta", text: "The two fixes fit one sprint." });
    await stream.push({ type: "proposal", proposal_id: PROPOSAL_ID });

    const proposed = await within(panel()).findByText("Proposed change. Nothing happens until you confirm.");
    const box = within(proposed.closest(".proposal"));
    const terms = box.getAllByRole("term").map((node) => node.textContent);
    const what = box.getAllByRole("definition").map((node) => node.textContent);
    expect(terms).toEqual(["Create", "Plan in", "", "Send back", "Guidance", "Leave"]);
    expect(what).toEqual([
      "Sprint 57, planned",
      "FOR-20 Resume a stale agent step in place",
      "FOR-21 Check the lease fencing token on writes",
      "FOR-14 Report the test result line",
      "Report skipped tests too.",
      "FOR-22 JSON output on the remaining read commands",
    ]);
    expect(box.getByRole("button", { name: "Not now" })).toBeEnabled();
    expect(box.getByRole("button", { name: "Confirm" })).toHaveClass("button--gold-outline");
    await stream.push({ type: "done", session_id: "s1" });
    await stream.end();
  });

  it("Confirm applies it, says so on the card, and reloads the page's data", async () => {
    const fetchImpl = await openWith(
      { ...projectRoutes(), [PROPOSAL_URL]: proposal() },
      { turns: [turn("t1", "user", "Plan it."), turn("t2", "assistant", "Here it is.", [{ name: "Bash" }, { proposal_id: PROPOSAL_ID }])], has_more: false },
    );
    fetchImpl.routes[CONFIRM_URL] = proposal({ state: "confirmed", decided_by: "ada", outcome: { sentence: "Applied 2 operations." } });
    await within(panel()).findByText("Proposed change. Nothing happens until you confirm.");
    await waitFor(() => expect(queueLoads(fetchImpl)).toBeGreaterThan(0));
    const before = queueLoads(fetchImpl);

    fireEvent.click(within(card()).getByRole("button", { name: "Confirm" }));

    expect(await within(panel()).findByText("Confirmed by ada. Applied 2 operations.")).toBeInTheDocument();
    expect(fetchImpl.calls.filter((call) => call.method === "POST").map((call) => call.url)).toEqual([`/api/v1/proposals/${PROPOSAL_ID}/confirm`]);
    expect(within(card()).queryByRole("button", { name: "Confirm" })).toBeNull();
    expect(within(card()).getByText("Proposed change.")).toBeInTheDocument();
    await waitFor(() => expect(queueLoads(fetchImpl)).toBeGreaterThan(before));
  });

  it("Not now declines it and says nothing was changed", async () => {
    const fetchImpl = await openWith(
      { ...projectRoutes(), [PROPOSAL_URL]: proposal() },
      { turns: [turn("t2", "assistant", "Here it is.", [{ proposal_id: PROPOSAL_ID }])], has_more: false },
    );
    fetchImpl.routes[DECLINE_URL] = proposal({ state: "declined", decided_by: "ada", outcome: { sentence: "Declined. Nothing was changed." } });
    await within(panel()).findByText("Proposed change. Nothing happens until you confirm.");
    fireEvent.click(within(card()).getByRole("button", { name: "Not now" }));
    expect(await within(panel()).findByText("Declined by ada. Nothing was changed.")).toBeInTheDocument();
    expect(fetchImpl.calls.some((call) => call.url.endsWith("/confirm"))).toBe(false);
  });

  it("shows a refused confirmation with its sentence", async () => {
    const fetchImpl = await openWith(
      { ...projectRoutes(), [PROPOSAL_URL]: proposal() },
      { turns: [turn("t2", "assistant", "", [{ proposal_id: PROPOSAL_ID }])], has_more: false },
    );
    const sentence = "Operation 2 of 2 (send a task back with guidance) was refused: Task task-merge is done, not waiting for a person. Nothing was applied.";
    fetchImpl.routes[CONFIRM_URL] = proposal({ state: "failed", decided_by: "ada", outcome: { sentence, failed: { index: 1 } } });
    await within(panel()).findByText("Proposed change. Nothing happens until you confirm.");
    fireEvent.click(within(card()).getByRole("button", { name: "Confirm" }));
    expect(await within(panel()).findByText(`Not applied. ${sentence}`)).toHaveClass("proposal__outcome--failed");
  });

  it("an API refusal is shown on the card and the proposal is read again", async () => {
    const fetchImpl = await openWith(
      { ...projectRoutes(), [PROPOSAL_URL]: proposal() },
      { turns: [turn("t2", "assistant", "", [{ proposal_id: PROPOSAL_ID }])], has_more: false },
    );
    fetchImpl.routes[CONFIRM_URL] = reply(400, { error: "Proposal prop-1 is already declined by grace.", code: "invalid_request" });
    await within(panel()).findByText("Proposed change. Nothing happens until you confirm.");
    fetchImpl.routes[PROPOSAL_URL] = proposal({ state: "declined", decided_by: "grace" });
    fireEvent.click(within(card()).getByRole("button", { name: "Confirm" }));
    expect(await within(panel()).findByRole("alert")).toHaveTextContent("already declined by grace");
    expect(await within(panel()).findByText("Declined by grace. Nothing was changed.")).toBeInTheDocument();
  });

  it("a proposal from earlier in the conversation shows its final state", async () => {
    await openWith(
      { ...projectRoutes(), [PROPOSAL_URL]: proposal({ state: "confirmed", decided_by: "ada", outcome: { sentence: "Applied 2 operations." } }) },
      { turns: [turn("t2", "assistant", "Here it is.", [{ proposal_id: PROPOSAL_ID }])], has_more: false },
    );
    expect(await within(panel()).findByText("Confirmed by ada. Applied 2 operations.")).toBeInTheDocument();
    expect(within(card()).queryByRole("button")).toBeNull();
  });
});

describe("the overlay at narrow widths", () => {
  let matches;
  beforeEach(() => {
    matches = true;
    window.matchMedia = vi.fn((query) => ({
      matches: query === "(max-width: 960px)" && matches,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
  });
  afterEach(() => {
    delete window.matchMedia;
  });

  async function openFromToggle() {
    renderApp("/dashboard/projects/foreman", createFakeFetch(withManager(projectRoutes())));
    const button = toggle();
    button.focus();
    fireEvent.click(button);
    await within(panel()).findByText(/You are on:/);
    return button;
  }

  it("takes focus, keeps Tab inside, and Escape closes it and gives focus back", async () => {
    const button = await openFromToggle();
    const region = screen.getByRole("dialog", { name: "Manager" });
    const box = within(region).getByRole("textbox", { name: "Message to the manager" });
    expect(box).toHaveFocus();

    const close = within(region).getByRole("button", { name: "Close" });
    const focusable = Array.from(region.querySelectorAll("button:not([disabled]), textarea:not([disabled])"));
    const last = focusable[focusable.length - 1];
    last.focus();
    fireEvent.keyDown(last, { key: "Tab" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
    expect(last).toHaveFocus();

    fireEvent.keyDown(box, { key: "Escape" });
    expect(document.querySelector(".manager-slot")).toBeNull();
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
    expect(button).toHaveFocus();
  });

  it("beside the page it is not a dialog and Escape leaves it open", async () => {
    matches = false;
    await openFromToggle();
    expect(screen.queryByRole("dialog", { name: "Manager" })).toBeNull();
    fireEvent.keyDown(within(panel()).getByRole("textbox", { name: "Message to the manager" }), { key: "Escape" });
    expect(panel()).toBeInTheDocument();
  });
});
