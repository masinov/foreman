import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp } from "../../testing/fakeApi";
import { SPRINT_URL, sprintRoutes } from "../../testing/sprintFixture";
import { taskDetail, taskRoutes } from "../../testing/taskFixture";

const HISTORY = "GET /api/v1/projects/foreman/meta/history?limit=30";
const MESSAGE = "POST /api/v1/projects/foreman/meta/message";

const lines = (...entries) =>
  new Response(entries.map((entry) => `${JSON.stringify(entry)}\n`).join(""), {
    status: 200,
    headers: { "Content-Type": "application/x-ndjson" },
  });

const asked = (fetchImpl) => fetchImpl.calls.filter((call) => call.url.endsWith("/meta/message"));

async function more(item) {
  fireEvent.click(await screen.findByRole("button", { name: "More" }));
  return screen.findByRole("menuitem", { name: item });
}

beforeEach(() => window.localStorage.clear());

describe("Plan this sprint", () => {
  function render(routes = sprintRoutes()) {
    const fetchImpl = createFakeFetch({ ...routes, [HISTORY]: { turns: [], has_more: false } });
    fetchImpl.routes[MESSAGE] = () => lines({ type: "text_delta", text: "Here is the plan." }, { type: "done" });
    renderApp("/dashboard/sprints/sprint-56", fetchImpl);
    return fetchImpl;
  }

  it("says what will happen, then asks the manager in its side bar", async () => {
    const fetchImpl = render();
    fireEvent.click(await more("Plan this sprint"));
    const dialog = await screen.findByRole("dialog", { name: "Plan this sprint" });
    expect(dialog).toHaveTextContent("proposes the tasks that reach the goal");
    expect(dialog).toHaveTextContent("Approve plans");
    // Nothing is asked before the person says so, and the side bar is closed.
    expect(asked(fetchImpl)).toHaveLength(0);
    expect(screen.queryByRole("complementary", { name: "Manager" })).toBeNull();

    fireEvent.click(within(dialog).getByRole("button", { name: "Ask the manager" }));

    const panel = await screen.findByRole("complementary", { name: "Manager" });
    await waitFor(() => expect(asked(fetchImpl)).toHaveLength(1));
    expect(asked(fetchImpl)[0].body.plan).toEqual({ kind: "plan_sprint", sprint_id: "sprint-56" });
    expect(asked(fetchImpl)[0].body.message).toBeUndefined();
    expect(await within(panel).findByText("Plan this sprint: Sprint 56: engine truthfulness")).toBeInTheDocument();
    expect(await within(panel).findByText("Here is the plan.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("is not offered for a sprint with no goal", async () => {
    const routes = sprintRoutes();
    routes[SPRINT_URL] = { ...routes[SPRINT_URL], goal: "" };
    render(routes);
    await more("Cancel sprint");
    expect(screen.queryByRole("menuitem", { name: "Plan this sprint" })).toBeNull();
  });
});

describe("Split into smaller tasks", () => {
  it("asks the manager to split a task that has not started", async () => {
    const routes = taskRoutes({ task: taskDetail({ status: "todo", blocked_kind: null }) });
    const fetchImpl = createFakeFetch({ ...routes, [HISTORY]: { turns: [], has_more: false } });
    fetchImpl.routes[MESSAGE] = () => lines({ type: "done" });
    renderApp("/dashboard/tasks/task-merge", fetchImpl);

    fireEvent.click(await more("Split into smaller tasks"));
    const dialog = await screen.findByRole("dialog", { name: "Split this task" });
    expect(dialog).toHaveTextContent("with this one cancelled");
    fireEvent.click(within(dialog).getByRole("button", { name: "Ask the manager" }));

    await screen.findByRole("complementary", { name: "Manager" });
    await waitFor(() => expect(asked(fetchImpl)).toHaveLength(1));
    expect(asked(fetchImpl)[0].body.plan).toEqual({ kind: "split_task", task_id: "task-merge" });
  });
});
