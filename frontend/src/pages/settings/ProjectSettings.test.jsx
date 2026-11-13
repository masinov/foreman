import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp, reply } from "../../testing/fakeApi";
import {
  DEVELOPMENT,
  LIGHT,
  SAVE_URL,
  settingsPayload,
  settingsRoutes,
  SETTINGS_URL,
  WORKFLOW_URL,
} from "../../testing/settingsFixture";

const GENERAL = "/dashboard/projects/foreman/settings";
const WORKFLOW = "/dashboard/projects/foreman/settings/workflow";

async function renderGeneral(routes = settingsRoutes()) {
  const fetchImpl = createFakeFetch(routes);
  renderApp(GENERAL, fetchImpl);
  await screen.findByLabelText("Spend per sprint");
  return fetchImpl;
}

const saves = (fetchImpl) => fetchImpl.calls.filter((call) => `${call.method} ${call.url}` === SAVE_URL);

describe("the page around project settings", () => {
  it("is a page of its own: breadcrumb, two tabs, no engine row and no Needs you", async () => {
    await renderGeneral();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).queryByRole("link", { name: "Workspace" })).toBeNull();
    expect(await within(crumbs).findByRole("link", { name: /^Foreman/ })).toHaveAttribute(
      "href",
      "/dashboard/projects/foreman",
    );
    expect(within(crumbs).getByText("Settings")).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { level: 1, name: "Project settings" })).toBeInTheDocument();
    expect(await screen.findByText("Foreman · /srv/foreman")).toBeInTheDocument();
    const tabs = screen.getByRole("navigation", { name: "Project settings" });
    expect(within(tabs).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([GENERAL, WORKFLOW]);
    expect(within(tabs).getByRole("link", { current: "page" })).toHaveTextContent("General");
    expect(screen.queryByRole("region", { name: /needs you/i })).toBeNull();
    expect(screen.queryByText(/Needs you/i, { selector: "h2" })).toBeNull();
    expect(document.querySelector(".engine")).toBeNull();
    // The engine and the manager are in the top bar.
    const banner = screen.getByRole("banner");
    expect(await within(banner).findByRole("button", { name: /Engine/ })).toBeInTheDocument();
    expect(within(banner).getByRole("button", { name: "Manager" })).toBeInTheDocument();
  });

  it("says when the project does not exist", async () => {
    renderApp("/dashboard/projects/nope/settings", createFakeFetch(settingsRoutes()));
    expect(await screen.findByRole("heading", { name: "There is no project nope" })).toBeInTheDocument();
  });
});

describe("General: every field reads its real value", () => {
  it("shows what the API says each setting is", async () => {
    await renderGeneral();
    expect(screen.getByLabelText("Accept filed work")).toHaveValue("human");
    expect(screen.getByLabelText("Approve plans")).toHaveValue("human");
    expect(screen.getByLabelText("Approve merges")).toHaveValue("auto");
    expect(screen.getByLabelText("Approve merges").selectedOptions[0]).toHaveTextContent("Foreman");
    expect(screen.getByLabelText("Foreman picks its own tasks")).toHaveValue("directed");
    expect(screen.getByLabelText("At most, per sprint")).toHaveValue("5");
    expect(screen.getByLabelText("Spend per task")).toHaveValue("");
    expect(screen.getByLabelText("Spend per sprint")).toHaveValue("12.5");
    expect(screen.getByLabelText("Time per task")).toHaveValue("");
    expect(screen.getByLabelText("Attempts at one step")).toHaveValue("5");
    expect(screen.getByLabelText("Tasks in progress at once")).toHaveValue("4");
    expect(screen.getByLabelText("Default model")).toHaveValue("");
    expect(screen.getByLabelText("Manager model")).toHaveValue("claude-opus-5-5");
    expect(screen.getByLabelText("Give up after")).toHaveValue("30");
    expect(screen.getByLabelText("Tell me")).toHaveValue("attention");
    expect(screen.getByLabelText("Keep events")).toHaveValue("");
    expect(screen.getByLabelText("Keep runs")).toHaveValue("30");
    expect(screen.getByLabelText("Keep prompts")).toHaveValue("");
  });

  it("shows a limit in minutes that the API holds in milliseconds", async () => {
    await renderGeneral(settingsRoutes({ effective: { time_limit_per_task_ms: 5400000 } }));
    expect(screen.getByLabelText("Time per task")).toHaveValue("90");
  });

  it("lists the exception rules", async () => {
    await renderGeneral(settingsRoutes({ effective: { policy_rules: { docs: { merge_approval: "auto" } } } }));
    const rules = screen.getByRole("list", { name: "Exception rules" });
    expect(within(rules).getByText("docs")).toBeInTheDocument();
    expect(within(rules).getByText("Approve merges: Foreman")).toBeInTheDocument();
  });

  it("says there are no rules when there are none", async () => {
    await renderGeneral();
    expect(screen.getByText(/None\. A rule can send one kind of task to a different decider\./)).toBeInTheDocument();
  });
});

describe("General: host-level values are read-only", () => {
  it("shows them as text with the terminal sentence and offers no control", async () => {
    await renderGeneral();
    const machine = screen.getByRole("region", { name: "This machine" });
    expect(within(machine).getByText(/changed from a terminal/)).toBeInTheDocument();
    expect(within(machine).getByText("foreman config foreman --set key=value")).toBeInTheDocument();
    expect(within(machine).getByText("ln -s ../node_modules frontend/node_modules")).toBeInTheDocument();
    expect(within(machine).getByText("venv")).toBeInTheDocument();
    expect(within(machine).getByText("The default, inside the project's .foreman folder")).toBeInTheDocument();
    expect(within(machine).queryAllByRole("textbox")).toHaveLength(0);
    expect(within(machine).queryAllByRole("combobox")).toHaveLength(0);
    expect(within(machine).queryAllByRole("button")).toHaveLength(0);
  });

  it("shows the test command as text, and only its timeout as a control", async () => {
    await renderGeneral();
    const tests = screen.getByRole("region", { name: "Tests" });
    expect(within(tests).getByText("./venv/bin/python -m unittest")).toBeInTheDocument();
    expect(within(tests).queryByLabelText("Test command")).toBeNull();
    expect(within(tests).getAllByRole("textbox")).toHaveLength(1);
    expect(within(tests).getByLabelText("Give up after")).toBeInTheDocument();
  });

  it("never sends a host-level setting", async () => {
    const fetchImpl = await renderGeneral(settingsRoutes());
    fetchImpl.routes[SAVE_URL] = settingsPayload();
    fireEvent.change(screen.getByLabelText("Spend per task"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saves(fetchImpl)).toHaveLength(1));
    const sent = Object.keys(saves(fetchImpl)[0].body.settings);
    for (const key of ["test_command", "worktree_root", "worktree_setup_command", "context_dir"]) {
      expect(sent).not.toContain(key);
    }
  });
});

describe("General: Save and Discard", () => {
  it("is not offered until something changes", async () => {
    await renderGeneral();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Discard" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Spend per task"), { target: { value: "2" } });
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Discard" })).toBeEnabled();
  });

  it("sends only what changed, in the units the API stores", async () => {
    const fetchImpl = await renderGeneral();
    fetchImpl.routes[SAVE_URL] = settingsPayload();
    fireEvent.change(screen.getByLabelText("Approve merges"), { target: { value: "human" } });
    fireEvent.change(screen.getByLabelText("Spend per task"), { target: { value: "4.5" } });
    fireEvent.change(screen.getByLabelText("Time per task"), { target: { value: "90" } });
    fireEvent.change(screen.getByLabelText("Give up after"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("Spend per sprint"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Keep runs"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Keep prompts"), { target: { value: "14" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saves(fetchImpl)).toHaveLength(1));
    expect(saves(fetchImpl)[0].body).toEqual({
      settings: {
        merge_approval: "human",
        cost_limit_per_task_usd: 4.5,
        time_limit_per_task_ms: 5400000,
        test_timeout_seconds: 1200,
        cost_limit_per_sprint_usd: 0,
        run_retention_days: null,
        prompt_retention_days: 14,
      },
    });
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("reads the page again after saving", async () => {
    const fetchImpl = await renderGeneral();
    fetchImpl.routes[SAVE_URL] = settingsPayload();
    fetchImpl.routes[SETTINGS_URL] = settingsPayload({ cost_limit_per_task_usd: 4 });
    fireEvent.change(screen.getByLabelText("Spend per task"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Saved.");
    await waitFor(() => expect(screen.getByLabelText("Spend per task")).toHaveValue("4"));
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("restores everything on Discard and sends nothing", async () => {
    const fetchImpl = await renderGeneral();
    fireEvent.change(screen.getByLabelText("Spend per task"), { target: { value: "9" } });
    fireEvent.change(screen.getByLabelText("Tell me"), { target: { value: "none" } });
    fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(screen.getByRole("list", { name: "Exception rules" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(screen.getByLabelText("Spend per task")).toHaveValue("");
    expect(screen.getByLabelText("Tell me")).toHaveValue("attention");
    expect(screen.queryByRole("list", { name: "Exception rules" })).toBeNull();
    expect(saves(fetchImpl)).toHaveLength(0);
  });

  it("adds and removes exception rules, saved with the page", async () => {
    const fetchImpl = await renderGeneral();
    fetchImpl.routes[SAVE_URL] = settingsPayload();
    fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
    fireEvent.change(screen.getByLabelText("Kind of task"), { target: { value: "docs" } });
    fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "merge_approval" } });
    fireEvent.change(screen.getByLabelText("Decided by"), { target: { value: "auto" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saves(fetchImpl)).toHaveLength(1));
    expect(saves(fetchImpl)[0].body).toEqual({ settings: { policy_rules: { docs: { merge_approval: "auto" } } } });
  });

  it("removes a rule, and the kind of task with it when it was the last", async () => {
    const fetchImpl = await renderGeneral(
      settingsRoutes({ effective: { policy_rules: { docs: { merge_approval: "auto" }, spike: { triage: "auto" } } } }),
    );
    fetchImpl.routes[SAVE_URL] = settingsPayload();
    fireEvent.click(screen.getByRole("button", { name: "Remove the docs rule for approve merges" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saves(fetchImpl)).toHaveLength(1));
    expect(saves(fetchImpl)[0].body).toEqual({ settings: { policy_rules: { spike: { triage: "auto" } } } });
  });

  it("does not send a value it can see is not a number", async () => {
    const fetchImpl = await renderGeneral();
    fireEvent.change(screen.getByLabelText("At most, per sprint"), { target: { value: "lots" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Enter a whole number.")).toBeInTheDocument();
    expect(saves(fetchImpl)).toHaveLength(0);
  });
});

describe("General: the API's refusal", () => {
  it("shows beside the field it is about, and nothing else", async () => {
    const fetchImpl = await renderGeneral();
    fetchImpl.routes[SAVE_URL] = reply(400, {
      error: "Expected non-negative numeric for setting, got -1.0",
      code: "invalid_request",
      field: "cost_limit_per_task_usd",
    });
    fireEvent.change(screen.getByLabelText("Spend per task"), { target: { value: "-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    const message = await screen.findByText("Expected non-negative numeric for setting, got -1.0.");
    const input = screen.getByLabelText("Spend per task");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")).toContain(message.id);
    expect(message.closest(".setting-row")).toContainElement(input);
    expect(screen.getByLabelText("Spend per sprint")).not.toHaveAttribute("aria-invalid");
    // Editing the field clears its message.
    fireEvent.change(screen.getByLabelText("Spend per task"), { target: { value: "1" } });
    expect(screen.queryByText(/Expected non-negative/)).toBeNull();
  });

  it("shows an error that names no field next to Save", async () => {
    const fetchImpl = await renderGeneral();
    fetchImpl.routes[SAVE_URL] = reply(500, { error: "Internal error. See the dashboard log.", code: "internal_error" });
    fireEvent.change(screen.getByLabelText("Spend per task"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Internal error. See the dashboard log.");
    expect(screen.getByLabelText("Spend per task")).not.toHaveAttribute("aria-invalid");
    // What was typed is kept.
    expect(screen.getByLabelText("Spend per task")).toHaveValue("1");
  });
});

describe("Workflow tab", () => {
  async function renderWorkflow(routes = settingsRoutes()) {
    const fetchImpl = createFakeFetch(routes);
    renderApp(WORKFLOW, fetchImpl);
    await screen.findByRole("table", { name: "Steps of the workflow" });
    return fetchImpl;
  }

  function rowsOf(table) {
    return within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell").map((cell) => cell.textContent));
  }

  it("is a tab of the same page", async () => {
    await renderWorkflow();
    const tabs = screen.getByRole("navigation", { name: "Project settings" });
    expect(within(tabs).getByRole("link", { current: "page" })).toHaveTextContent("Workflow");
    expect(document.querySelector(".engine")).toBeNull();
  });

  it("derives each step from the definition: who, how, when it moves on, otherwise", async () => {
    await renderWorkflow();
    const rows = rowsOf(screen.getByRole("table", { name: "Steps of the workflow" }));
    expect(rows).toEqual([
      ["Develop", "Developer", "agent, project default model", "it reports the work done", ""],
      [
        "Test",
        "Engine",
        "runs the project's test command",
        "the tests pass",
        "If the tests fail: back to Develop, with its output",
      ],
      [
        "Review",
        "Code Reviewer",
        "agent, claude-sonnet-5-5",
        "it approves",
        "If it denies or steers: back to Develop, with its output",
      ],
      [
        "Merge approval",
        "Foreman",
        "this project's Who decides setting",
        "approved",
        "If denied or sent back: back to Develop, with its output",
      ],
      [
        "Merge",
        "Engine",
        "merges the task branch into main",
        "the merge succeeds",
        "If the merge conflicts or the merge fails: back to Develop, with its output",
      ],
      ["Done", "Engine", "marks the task done", "The last step", ""],
    ]);
  });

  it("names a person at a gate that the project's Who decides setting gives to a person", async () => {
    await renderWorkflow(settingsRoutes({ effective: { merge_approval: "human" } }));
    const table = screen.getByRole("table", { name: "Steps of the workflow" });
    expect(within(table).getByRole("row", { name: /Merge approval/ })).toHaveTextContent("A person");
  });

  it("shows other steps and outcomes for a different workflow", async () => {
    await renderWorkflow(settingsRoutes({ workflow: LIGHT }));
    const rows = rowsOf(screen.getByRole("table", { name: "Steps of the workflow" }));
    expect(rows.map((row) => row[0])).toEqual(["Draft", "Plan approval", "Ship"]);
    expect(rows[0]).toEqual(["Draft", "Developer", "agent, project default model", "it reports the work done", ""]);
    expect(rows[1]).toEqual([
      "Plan approval",
      "A person",
      "this project's Who decides setting",
      "approved",
      "If denied: back to Draft",
    ]);
    expect(rows[2][3]).toBe("The last step");
    expect(screen.getByRole("heading", { name: /Light Review/ })).toBeInTheDocument();
    expect(screen.queryByText("Review")).toBeNull();
  });

  it("states what finishing requires as facts and claims, from the definition", async () => {
    await renderWorkflow();
    const table = screen.getByRole("table", { name: "What finishing requires" });
    expect(rowsOf(table)).toEqual([
      ["Tests pass at the commit being merged", "Fact", "measured by the engine"],
      ["Code review approves that same commit", "Claim", "reported by the reviewing agent"],
      ["Acceptance criteria marked met", "Claim", "reported by the reviewing agent"],
    ]);
  });

  it("says so when the workflow requires nothing, and when the guard is off", async () => {
    await renderWorkflow(settingsRoutes({ workflow: { ...LIGHT, requirements_enforced: false } }));
    expect(screen.queryByRole("table", { name: "What finishing requires" })).toBeNull();
    expect(screen.getByText(/no test or review step/)).toBeInTheDocument();
    expect(screen.getByText(/completion guard is off/)).toBeInTheDocument();
  });

  it("lists the roles with what each does, its backend and model", async () => {
    await renderWorkflow();
    const table = screen.getByRole("table", { name: "Roles in this workflow" });
    expect(rowsOf(table)).toEqual([
      ["Developer", "Writes code, tests, and documentation for assigned tasks", "claude_code", "project default"],
      ["Code Reviewer", "Reviews completed work and returns APPROVE, DENY, or STEER", "claude_code", "claude-sonnet-5-5"],
    ]);
  });

  it("says where the definition file is and that it is not edited here", async () => {
    await renderWorkflow();
    expect(screen.getByText("/srv/foreman/foreman/data/workflows/development.toml")).toBeInTheDocument();
    expect(screen.getByText(/cannot be edited here/)).toBeInTheDocument();
  });

  it("asks for confirmation before changing the workflow, then changes it through the API", async () => {
    const fetchImpl = await renderWorkflow();
    fetchImpl.routes[SAVE_URL] = settingsPayload();
    fireEvent.click(screen.getByRole("button", { name: "Use another workflow" }));
    const dialog = await screen.findByRole("dialog", { name: "Use another workflow" });
    const choose = await within(dialog).findByRole("option", { name: "Light Review" });
    // The current workflow is not offered.
    expect(within(dialog).queryByRole("option", { name: "Standard Development" })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "Use this workflow" })).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Workflow"), { target: { value: choose.value } });
    expect(within(dialog).getByText(/Draft, then Plan approval, then Ship/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Tasks already underway are not moved/)).toBeInTheDocument();
    // Nothing has changed yet.
    expect(saves(fetchImpl)).toHaveLength(0);

    fetchImpl.routes[WORKFLOW_URL] = LIGHT;
    fireEvent.click(within(dialog).getByRole("button", { name: "Use Light Review" }));
    await waitFor(() => expect(saves(fetchImpl)).toHaveLength(1));
    expect(saves(fetchImpl)[0].body).toEqual({ workflow_id: "light" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(await screen.findByRole("heading", { name: /Light Review/ })).toBeInTheDocument();
  });

  it("changes nothing when the confirmation is cancelled", async () => {
    const fetchImpl = await renderWorkflow();
    fireEvent.click(screen.getByRole("button", { name: "Use another workflow" }));
    const dialog = await screen.findByRole("dialog", { name: "Use another workflow" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(saves(fetchImpl)).toHaveLength(0);
  });

  it("shows the API's refusal in the dialog and keeps it open", async () => {
    const fetchImpl = await renderWorkflow();
    fetchImpl.routes[SAVE_URL] = reply(400, { error: "There is no workflow 'light'.", code: "invalid_request", field: "workflow_id" });
    fireEvent.click(screen.getByRole("button", { name: "Use another workflow" }));
    const dialog = await screen.findByRole("dialog", { name: "Use another workflow" });
    await within(dialog).findByRole("option", { name: "Light Review" });
    fireEvent.change(within(dialog).getByLabelText("Workflow"), { target: { value: "light" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Use Light Review" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("There is no workflow 'light'.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
