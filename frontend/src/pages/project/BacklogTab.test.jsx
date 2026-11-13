import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp, reply } from "../../testing/fakeApi";
import {
  ACCEPTED,
  ACTIVE,
  backlogPayload,
  backlogRoutes,
  backlogTask,
  backlogUrl,
  FILED,
  PLANNED,
} from "../../testing/projectFixture";

const PATH = "/dashboard/projects/foreman/backlog";

// `url` is a path or a route key such as backlogUrl() ("GET /api/v1/...").
function calls(fetchImpl, method, url) {
  const path = url.replace(/^[A-Z]+ /, "");
  return fetchImpl.calls.filter((call) => call.method === method && call.url === path);
}

async function renderBacklog(routes = backlogRoutes()) {
  const fetchImpl = createFakeFetch(routes);
  const utils = renderApp(PATH, fetchImpl);
  await screen.findByRole("region", { name: /Accepted, not planned/ });
  return { ...utils, fetchImpl };
}

const filedSection = () => screen.getByRole("region", { name: /Filed, not accepted/ });
const acceptedSection = () => screen.getByRole("region", { name: /Accepted, not planned/ });

describe("the backlog tab", () => {
  it("renders both groups from the backlog endpoint", async () => {
    const { fetchImpl } = await renderBacklog();
    expect(calls(fetchImpl, "GET", backlogUrl())).toHaveLength(1);

    expect(screen.queryByRole("navigation", { name: "Project" })).toBeNull();

    const filed = filedSection();
    expect(within(filed).getByRole("link", { name: FILED.title })).toHaveAttribute("href", "/dashboard/tasks/task-filed");
    expect(within(filed).getByText(/manager, 9 Nov/)).toBeInTheDocument();
    expect(within(filed).getByText("Cannot be planned until accepted. This project sends these to a person.")).toBeInTheDocument();

    const accepted = acceptedSection();
    const rows = within(accepted).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByRole("link", { name: ACCEPTED[0].title })).toHaveAttribute("href", "/dashboard/tasks/task-a");
    expect(within(rows[0]).getByText("carried from Sprint 56: engine truthfulness")).toBeInTheDocument();
    expect(within(rows[1]).getByText("ada via github")).toBeInTheDocument();
    expect(within(rows[2]).getByText("feature")).toBeInTheDocument();
  });

  it("says who accepts when the project accepts filed work itself", async () => {
    await renderBacklog(backlogRoutes([...ACCEPTED], { triage: "auto" }));
    expect(
      within(filedSection()).getByText("Cannot be planned until accepted. This project accepts filed work on its own."),
    ).toBeInTheDocument();
  });

  it("says what is true when nothing is filed and nothing waits to be planned", async () => {
    await renderBacklog(backlogRoutes([]));
    expect(within(filedSection()).getByText(/^Nothing is filed\./)).toBeInTheDocument();
    expect(within(acceptedSection()).getByText(/^Nothing is waiting to be planned\./)).toBeInTheDocument();
    expect(within(acceptedSection()).getByRole("button", { name: "Plan" })).toBeDisabled();
  });

  it("shows an API failure as a sentence", async () => {
    const routes = backlogRoutes();
    routes[backlogUrl()] = reply(404, { error: "Project not found: foreman.", code: "not_found" });
    renderApp(PATH, createFakeFetch(routes));
    expect(await screen.findByText("Project not found: foreman.")).toBeInTheDocument();
  });
});

describe("accepting and declining filed work", () => {
  it.each([
    ["Accept", "accept", /Accepted Retry the webhook on a timeout/],
    ["Decline", "decline", /Declined Retry the webhook on a timeout/],
  ])("%s calls its endpoint, reloads and the row leaves", async (button, endpoint, sentence) => {
    const routes = backlogRoutes();
    routes[`POST /api/v1/tasks/task-filed/${endpoint}`] = { id: "task-filed" };
    const { fetchImpl } = await renderBacklog(routes);
    // After the change the API no longer lists it as filed.
    routes[backlogUrl()] = backlogPayload([...ACCEPTED]);
    routes["GET /api/v1/workspace"] = {
      ...(await (await fetchImpl("/api/v1/workspace")).json()),
    };

    fireEvent.click(within(filedSection()).getByRole("button", { name: `${button} ${FILED.title}` }));
    expect(await screen.findByText(sentence)).toBeInTheDocument();
    expect(calls(fetchImpl, "POST", `/api/v1/tasks/task-filed/${endpoint}`)).toHaveLength(1);
    await waitFor(() => expect(within(filedSection()).queryByRole("link", { name: FILED.title })).toBeNull());
    expect(within(filedSection()).getByText(/^Nothing is filed\./)).toBeInTheDocument();
    // The tab count is read again from the workspace.
    await waitFor(() => expect(calls(fetchImpl, "GET", "/api/v1/workspace").length).toBeGreaterThan(2));
  });

  it("shows a refusal as a sentence and keeps the row", async () => {
    const routes = backlogRoutes();
    routes["POST /api/v1/tasks/task-filed/accept"] = reply(422, {
      error: "Task task-filed is already accepted.",
      code: "validation_error",
    });
    await renderBacklog(routes);
    fireEvent.click(within(filedSection()).getByRole("button", { name: `Accept ${FILED.title}` }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Task task-filed is already accepted.");
    expect(within(filedSection()).getByRole("link", { name: FILED.title })).toBeInTheDocument();
  });
});

describe("selecting and planning", () => {
  it("has accessible checkboxes, a select-all, and Plan disabled with nothing selected", async () => {
    await renderBacklog();
    const section = acceptedSection();
    const plan = within(section).getByRole("button", { name: "Plan" });
    const all = within(section).getByRole("checkbox", { name: "Select all accepted tasks" });
    expect(plan).toBeDisabled();

    const first = within(section).getByRole("checkbox", { name: `Select: ${ACCEPTED[0].title}` });
    first.focus();
    expect(first).toHaveFocus();
    // A checkbox toggles with Space; a click is what the browser does for it.
    fireEvent.click(first);
    expect(first).toBeChecked();
    expect(plan).toBeEnabled();
    expect(all.indeterminate).toBe(true);

    fireEvent.click(all);
    for (const task of ACCEPTED) {
      expect(within(section).getByRole("checkbox", { name: `Select: ${task.title}` })).toBeChecked();
    }
    expect(all).toBeChecked();
    fireEvent.click(all);
    expect(plan).toBeDisabled();
    expect(all).not.toBeChecked();
  });

  it("lists a new sprint and every planned or active sprint to plan into", async () => {
    await renderBacklog();
    const select = within(acceptedSection()).getByRole("combobox", { name: "Plan selected into" });
    expect(within(select).getAllByRole("option").map((option) => [option.value, option.textContent])).toEqual([
      ["new", "A new sprint"],
      ["sprint-56", "Sprint 56: engine truthfulness (active)"],
      ["sprint-57", "Sprint 57: next (planned)"],
    ]);
  });

  it("plans the selected tasks into an existing sprint, reloads, and the rows leave", async () => {
    const routes = backlogRoutes();
    routes["POST /api/v1/projects/foreman/backlog/plan"] = {
      sprint: { id: "sprint-57", title: PLANNED.title },
      created_sprint: false,
      task_ids: ["task-a", "task-c"],
    };
    const { fetchImpl } = await renderBacklog(routes);
    const section = acceptedSection();
    fireEvent.click(within(section).getByRole("checkbox", { name: `Select: ${ACCEPTED[0].title}` }));
    fireEvent.click(within(section).getByRole("checkbox", { name: `Select: ${ACCEPTED[2].title}` }));
    fireEvent.change(within(section).getByRole("combobox", { name: "Plan selected into" }), {
      target: { value: "sprint-57" },
    });
    routes[backlogUrl()] = backlogPayload([FILED, ACCEPTED[1]]);
    fireEvent.click(within(section).getByRole("button", { name: "Plan" }));

    expect(await screen.findByText("2 tasks planned into Sprint 57: next.")).toBeInTheDocument();
    expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/backlog/plan")[0].body).toEqual({
      task_ids: ["task-a", "task-c"],
      sprint_id: "sprint-57",
    });
    await waitFor(() => expect(within(acceptedSection()).getAllByRole("row")).toHaveLength(2));
    expect(within(acceptedSection()).queryByRole("link", { name: ACCEPTED[0].title })).toBeNull();
    expect(within(acceptedSection()).getByRole("button", { name: "Plan" })).toBeDisabled();
  });

  it("shows a refusal to plan into an existing sprint as a sentence", async () => {
    const routes = backlogRoutes();
    routes["POST /api/v1/projects/foreman/backlog/plan"] = reply(422, {
      error: "Sprint sprint-56 is completed and cannot take tasks.",
      code: "validation_error",
    });
    await renderBacklog(routes);
    const section = acceptedSection();
    fireEvent.click(within(section).getByRole("checkbox", { name: `Select: ${ACCEPTED[0].title}` }));
    fireEvent.change(within(section).getByRole("combobox", { name: "Plan selected into" }), {
      target: { value: "sprint-56" },
    });
    fireEvent.click(within(section).getByRole("button", { name: "Plan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sprint sprint-56 is completed and cannot take tasks.");
    expect(within(section).getByRole("checkbox", { name: `Select: ${ACCEPTED[0].title}` })).toBeChecked();
  });

  it("asks for a title and goal in a dialog to plan into a new sprint", async () => {
    const routes = backlogRoutes();
    routes["POST /api/v1/projects/foreman/backlog/plan"] = {
      sprint: { id: "sprint-58", title: "Sprint 58: more" },
      created_sprint: true,
      task_ids: ["task-b"],
    };
    const { fetchImpl } = await renderBacklog(routes);
    fireEvent.click(within(acceptedSection()).getByRole("checkbox", { name: `Select: ${ACCEPTED[1].title}` }));
    fireEvent.click(within(acceptedSection()).getByRole("button", { name: "Plan" }));

    const dialog = await screen.findByRole("dialog", { name: "Plan into a new sprint" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create sprint and plan" }));
    expect(within(dialog).getByText("A sprint needs a title.")).toBeInTheDocument();
    expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/backlog/plan")).toHaveLength(0);

    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: "Sprint 58: more" } });
    fireEvent.change(within(dialog).getByLabelText("Goal"), { target: { value: "Finish the backlog." } });
    routes[backlogUrl()] = backlogPayload([FILED, ACCEPTED[0], ACCEPTED[2]]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Create sprint and plan" }));

    expect(await screen.findByText("1 task planned into Sprint 58: more.")).toBeInTheDocument();
    expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/backlog/plan")[0].body).toEqual({
      task_ids: ["task-b"],
      new_sprint: { title: "Sprint 58: more", goal: "Finish the backlog." },
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps the dialog open and shows a refusal for a new sprint", async () => {
    const routes = backlogRoutes();
    routes["POST /api/v1/projects/foreman/backlog/plan"] = reply(422, {
      error: "Task task-b is not accepted.",
      code: "validation_error",
    });
    await renderBacklog(routes);
    fireEvent.click(within(acceptedSection()).getByRole("checkbox", { name: `Select: ${ACCEPTED[1].title}` }));
    fireEvent.click(within(acceptedSection()).getByRole("button", { name: "Plan" }));
    const dialog = await screen.findByRole("dialog", { name: "Plan into a new sprint" });
    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: "Sprint 58" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create sprint and plan" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Task task-b is not accepted.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("filing a new task", () => {
  it("files title, type, description and criteria into the backlog, then reloads", async () => {
    const routes = backlogRoutes();
    routes["POST /api/v1/projects/foreman/backlog"] = reply(201, {
      id: "task-new",
      title: "Add a retry",
      status: "triage",
    });
    const { fetchImpl } = await renderBacklog(routes);
    fireEvent.click(screen.getByRole("button", { name: "New task" }));
    const dialog = await screen.findByRole("dialog", { name: "New task" });

    fireEvent.click(within(dialog).getByRole("button", { name: "File task" }));
    expect(within(dialog).getByText("A task needs a title.")).toBeInTheDocument();

    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: "Add a retry" } });
    fireEvent.change(within(dialog).getByLabelText("Type"), { target: { value: "fix" } });
    fireEvent.change(within(dialog).getByLabelText("Description"), { target: { value: "It fails once." } });
    fireEvent.change(within(dialog).getByLabelText("Acceptance criteria"), { target: { value: "It retries." } });
    fireEvent.change(within(dialog).getByLabelText("Size"), { target: { value: "small" } });
    // Waiting for other tasks is a thing of sprints; the backlog has no order to wait in.
    expect(within(dialog).queryByRole("button", { name: /wait for other tasks/ })).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "File task" }));

    expect(await screen.findByText("Filed Add a retry. It waits to be accepted.")).toBeInTheDocument();
    expect(calls(fetchImpl, "POST", "/api/v1/projects/foreman/backlog")[0].body).toEqual({
      title: "Add a retry",
      task_type: "fix",
      description: "It fails once.",
      acceptance_criteria: "It retries.",
      complexity: "small",
    });
    await waitFor(() => expect(calls(fetchImpl, "GET", backlogUrl()).length).toBeGreaterThan(1));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("says when the project accepted the task itself", async () => {
    const routes = backlogRoutes();
    routes["POST /api/v1/projects/foreman/backlog"] = reply(201, { id: "task-new", title: "Add a retry", status: "todo" });
    await renderBacklog(routes);
    fireEvent.click(screen.getByRole("button", { name: "New task" }));
    const dialog = await screen.findByRole("dialog", { name: "New task" });
    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: "Add a retry" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "File task" }));
    expect(
      await screen.findByText("Filed Add a retry. This project accepted it, so it is waiting to be planned."),
    ).toBeInTheDocument();
  });

  it("shows a refusal in the dialog as a sentence", async () => {
    const routes = backlogRoutes();
    routes["POST /api/v1/projects/foreman/backlog"] = reply(422, {
      error: "task_type: expected one of feature, fix.",
      code: "validation_error",
    });
    await renderBacklog(routes);
    fireEvent.click(screen.getByRole("button", { name: "New task" }));
    const dialog = await screen.findByRole("dialog", { name: "New task" });
    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: "Add a retry" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "File task" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("task_type: expected one of feature, fix.");
  });
});

describe("paging and filtering", () => {
  function manyAccepted(count, from = 0) {
    return Array.from({ length: count }, (_, index) => backlogTask(`task-m${from + index}`, `Accepted work ${from + index}`, "accepted"));
  }

  it("loads 25 rows and Show more asks the server for the next page", async () => {
    const all = manyAccepted(30);
    const routes = backlogRoutes();
    routes[backlogUrl()] = { ...backlogPayload(all.slice(0, 25), { total: 30 }), counts: { filed: 0, accepted: 30, declined: 0 } };
    routes[backlogUrl({ offset: 25 })] = { ...backlogPayload(all.slice(25), { total: 30 }), counts: { filed: 0, accepted: 30, declined: 0 } };
    const { fetchImpl } = await renderBacklog(routes);
    expect(within(acceptedSection()).getAllByRole("row")).toHaveLength(26);

    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    await waitFor(() => expect(within(acceptedSection()).getAllByRole("row")).toHaveLength(31));
    expect(calls(fetchImpl, "GET", backlogUrl({ offset: 25 }))).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  it("filters on the server and says what is true when nothing matches", async () => {
    const routes = backlogRoutes();
    routes[backlogUrl({ q: "lease" })] = backlogPayload([ACCEPTED[1]]);
    routes[backlogUrl({ q: "zzz" })] = backlogPayload([]);
    const { fetchImpl } = await renderBacklog(routes);
    const box = screen.getByRole("searchbox", { name: "Filter the backlog" });

    fireEvent.change(box, { target: { value: "lease" } });
    await waitFor(() => expect(within(acceptedSection()).getAllByRole("row")).toHaveLength(2));
    expect(calls(fetchImpl, "GET", backlogUrl({ q: "lease" }))).toHaveLength(1);
    expect(within(acceptedSection()).getByRole("link", { name: ACCEPTED[1].title })).toBeInTheDocument();

    fireEvent.change(box, { target: { value: "zzz" } });
    expect(await screen.findByText("No accepted work matches “zzz”.")).toBeInTheDocument();
    expect(within(filedSection()).getByText("No filed work matches “zzz”.")).toBeInTheDocument();
  });
});

describe("the backlog page", () => {
  it("is a page of its own below the project: its own title, its own breadcrumb step, no project tabs", async () => {
    await renderBacklog();
    expect(screen.getByRole("heading", { level: 1, name: "Backlog" })).toBeInTheDocument();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(await within(crumbs).findByRole("link", { name: /Foreman/ })).toHaveAttribute("href", "/dashboard/projects/foreman");
    expect(within(crumbs).getByText("Backlog")).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("navigation", { name: "Project" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Engine" })).toBeNull();
  });
});
