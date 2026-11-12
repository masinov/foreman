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
