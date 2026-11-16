import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp, reply } from "../../testing/fakeApi";
import { definitionsPayload, DEFINITIONS_URL, editableRole, settingsRoutes } from "../../testing/settingsFixture";

const ROLES = "/dashboard/projects/foreman/settings/roles";
const WORKFLOW = "/dashboard/projects/foreman/settings/workflow";
const ROLE_URL = "/api/v1/projects/foreman/roles";
const WORKFLOW_URL = "/api/v1/projects/foreman/workflows";

const sent = (fetchImpl, method) => fetchImpl.calls.filter((call) => call.method === method);

async function renderRoles(routes = settingsRoutes()) {
  const fetchImpl = createFakeFetch(routes);
  renderApp(ROLES, fetchImpl);
  await screen.findByRole("table", { name: "Roles" });
  return fetchImpl;
}

async function openRole(name = "Code Reviewer", routes) {
  const fetchImpl = await renderRoles(routes);
  fireEvent.click(screen.getByRole("button", { name: `Edit role ${name}` }));
  const dialog = await screen.findByRole("dialog", { name });
  return { fetchImpl, dialog };
}

describe("Roles tab", () => {
  it("lists each role with its model, tools, how it ends and where it is used", async () => {
    await renderRoles();
    const rows = within(screen.getByRole("table", { name: "Roles" }))
      .getAllByRole("row")
      .slice(1)
      .map((row) =>
        within(row)
          .getAllByRole("cell")
          .slice(0, 5)
          .map((cell) => cell.textContent),
      );
    expect(rows).toEqual([
      ["Developer", "Project default", "Every tool", "Says it is done", "Standard Development, Light Review"],
      ["Code Reviewer", "claude-sonnet-5-5", "Read, Grep, Glob", "Approve, deny or steer", "Standard Development"],
    ]);
  });

  it("says which roles the project changed or added, and a role with no tool", async () => {
    const routes = settingsRoutes();
    routes[DEFINITIONS_URL] = definitionsPayload({
      roles: [
        editableRole({ origin: "changed" }),
        editableRole({ id: "judge", name: "Judge", origin: "own", tools: { every: false, chosen: [] }, used_by: [] }),
      ],
    });
    await renderRoles(routes);
    const table = screen.getByRole("table", { name: "Roles" });
    expect(within(table).getByText("changed for this project")).toBeInTheDocument();
    expect(within(table).getByText("this project's own")).toBeInTheDocument();
    expect(within(table).getByText("No tool")).toBeInTheDocument();
    expect(within(table).getByText("No workflow")).toBeInTheDocument();
  });
});

describe("Editing a role", () => {
  it("opens with the role's values", async () => {
    const { dialog } = await openRole();
    expect(within(dialog).getByLabelText("Name")).toHaveValue("Code Reviewer");
    expect(within(dialog).getByLabelText("Model")).toHaveValue("claude-sonnet-5-5");
    expect(within(dialog).getByLabelText("Every tool the agent program has")).not.toBeChecked();
    expect(within(dialog).getByLabelText("Read")).toBeChecked();
    expect(within(dialog).getByLabelText("Bash")).not.toBeChecked();
    expect(within(dialog).getByLabelText("Its run ends when")).toHaveValue("decides");
    expect(within(dialog).getByLabelText("Steer")).toBeChecked();
    expect(within(dialog).getByLabelText("Escalate")).not.toBeChecked();
    expect(within(dialog).getByLabelText("Time limit, minutes")).toHaveValue("10");
    expect(within(dialog).getByLabelText("Prompt").value).toContain("DENY: <reason>");
  });

  it("saves the form through the API and closes", async () => {
    const { fetchImpl, dialog } = await openRole();
    fetchImpl.routes[`PUT ${ROLE_URL}/code_reviewer`] = definitionsPayload();
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "claude-opus-5-5" } });
    fireEvent.click(within(dialog).getByLabelText("Bash"));
    fireEvent.click(within(dialog).getByLabelText("Steer"));
    fireEvent.change(within(dialog).getByLabelText("Time limit, minutes"), { target: { value: "20" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetchImpl, "PUT")).toHaveLength(1));
    expect(sent(fetchImpl, "PUT")[0].url).toBe(`${ROLE_URL}/code_reviewer`);
    expect(sent(fetchImpl, "PUT")[0].body).toEqual({
      fields: {
        name: "Code Reviewer",
        description: "Reviews completed work and returns APPROVE, DENY, or STEER",
        model: "claude-opus-5-5",
        tools: { every: false, chosen: ["Read", "Grep", "Glob", "Bash"] },
        ends: "decides",
        decisions: ["approve", "deny"],
        timeout_minutes: 20,
        max_cost_usd: 5,
        prompt: "Review the change.\nAPPROVE\nDENY: <reason>\nSTEER: <what to do>",
      },
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("shows the API's refusal and keeps the form open", async () => {
    const { fetchImpl, dialog } = await openRole();
    fetchImpl.routes[`PUT ${ROLE_URL}/code_reviewer`] = reply(400, {
      error: "Role 'code_reviewer' may decide ESCALATE but its prompt never says so.",
      code: "invalid_request",
    });
    fireEvent.click(within(dialog).getByLabelText("Escalate"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("may decide ESCALATE but its prompt never says so");
    expect(within(dialog).getByLabelText("Escalate")).toBeChecked();
  });

  it("asks nothing of the API when the form is not complete", async () => {
    const { fetchImpl, dialog } = await openRole();
    for (const decision of ["Approve", "Deny", "Steer"]) fireEvent.click(within(dialog).getByLabelText(decision));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Tick at least one decision it may give.");
    expect(sent(fetchImpl, "PUT")).toHaveLength(0);
  });

  it("hides the tool list when it has every tool, and says so when it has none", async () => {
    const { dialog } = await openRole();
    for (const tool of ["Read", "Grep", "Glob"]) fireEvent.click(within(dialog).getByLabelText(tool));
    expect(within(dialog).getByText("With none ticked it has no tool at all.")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByLabelText("Every tool the agent program has"));
    expect(within(dialog).queryByLabelText("Read")).toBeNull();
  });

  it("saves the text as it is in the text view", async () => {
    const { fetchImpl, dialog } = await openRole();
    fetchImpl.routes[`PUT ${ROLE_URL}/code_reviewer`] = definitionsPayload();
    fireEvent.click(within(dialog).getByRole("button", { name: "Edit as text" }));
    const box = within(dialog).getByLabelText("The role as TOML");
    expect(box).toHaveValue('[role]\nid = "code_reviewer"\n');
    fireEvent.change(box, { target: { value: '[role]\nid = "code_reviewer"\nname = "R"\n' } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetchImpl, "PUT")).toHaveLength(1));
    expect(sent(fetchImpl, "PUT")[0].body).toEqual({ text: '[role]\nid = "code_reviewer"\nname = "R"\n' });
  });

  it("goes back to the shipped role when the project had changed it", async () => {
    const routes = settingsRoutes();
    routes[DEFINITIONS_URL] = definitionsPayload({ roles: [editableRole({ origin: "changed" })] });
    const { fetchImpl, dialog } = await openRole("Code Reviewer", routes);
    fetchImpl.routes[`DELETE ${ROLE_URL}/code_reviewer`] = definitionsPayload();
    fireEvent.click(within(dialog).getByRole("button", { name: "Back to the shipped role" }));

    await waitFor(() => expect(sent(fetchImpl, "DELETE")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("offers no way back for a role as shipped", async () => {
    const { dialog } = await openRole();
    expect(within(dialog).queryByRole("button", { name: /Back to the shipped/ })).toBeNull();
    expect(within(dialog).queryByRole("button", { name: /Remove this/ })).toBeNull();
  });
});

describe("A new role", () => {
  it("starts as a copy of a chosen role and is saved under an id made from its name", async () => {
    const fetchImpl = await renderRoles();
    fetchImpl.routes[`PUT ${ROLE_URL}/strict_reviewer`] = definitionsPayload();
    fireEvent.click(screen.getByRole("button", { name: "New role" }));
    const start = await screen.findByRole("dialog", { name: "New role" });
    expect(within(start).getByRole("button", { name: "Continue" })).toBeDisabled();
    fireEvent.change(within(start).getByLabelText("Start from"), { target: { value: "code_reviewer" } });
    fireEvent.click(within(start).getByRole("button", { name: "Continue" }));

    const form = await screen.findByRole("dialog", { name: "New role" });
    await within(form).findByLabelText("Prompt");
    expect(within(form).getByLabelText("Name")).toHaveValue("");
    expect(within(form).getByLabelText("Read")).toBeChecked();
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Strict Reviewer" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetchImpl, "PUT")).toHaveLength(1));
    const call = sent(fetchImpl, "PUT")[0];
    expect(call.url).toBe(`${ROLE_URL}/strict_reviewer`);
    expect(call.body.copy_of).toBe("code_reviewer");
    expect(call.body.fields.name).toBe("Strict Reviewer");
  });
});

describe("Editing a workflow's steps", () => {
  async function openSteps() {
    const fetchImpl = createFakeFetch(settingsRoutes());
    renderApp(WORKFLOW, fetchImpl);
    await screen.findByRole("table", { name: "Steps of the workflow" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit steps" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Edit steps" }));
    const dialog = await screen.findByRole("dialog", { name: "Standard Development" });
    return { fetchImpl, dialog };
  }

  it("opens with every step, who does it and what follows each way it can end", async () => {
    const { dialog } = await openSteps();
    const steps = within(within(dialog).getByRole("list", { name: "Steps" })).getAllByRole("listitem");
    expect(steps).toHaveLength(6);
    expect(within(dialog).getByLabelText("Name of step 2")).toHaveValue("Test");
    expect(within(dialog).getByLabelText("Who does Test")).toHaveValue("_builtin:run_tests");
    const fails = within(dialog).getByLabelText("Test: when the tests fail, go to");
    expect(within(fails).getByRole("option", { selected: true })).toHaveTextContent("Develop");
    expect(within(dialog).getByLabelText("Test: when the tests fail, with its output")).toBeChecked();
    // The last step ends the workflow: nothing follows it.
    expect(within(dialog).queryByLabelText(/^Done: when/)).toBeNull();
  });

  it("saves the steps: one removed, another sent elsewhere, a renamed step still pointed at", async () => {
    const { fetchImpl, dialog } = await openSteps();
    fetchImpl.routes[`PUT ${WORKFLOW_URL}/development`] = definitionsPayload();
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove Review" }));
    const passes = within(dialog).getByLabelText("Test: when the tests pass, go to");
    const gate = within(passes).getByRole("option", { name: "Merge approval" });
    fireEvent.change(passes, { target: { value: gate.value } });
    fireEvent.change(within(dialog).getByLabelText("Name of step 1"), { target: { value: "Build" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetchImpl, "PUT")).toHaveLength(1));
    const { fields } = sent(fetchImpl, "PUT")[0].body;
    expect(fields.name).toBe("Standard Development");
    expect(fields.steps.map((step) => step.id)).toEqual(["build", "test", "merge_approval", "merge", "done"]);
    expect(fields.steps[1]).toEqual({
      id: "test",
      role: "_builtin:run_tests",
      policy: null,
      then: {
        success: { to: "merge_approval", carry_output: false },
        failure: { to: "build", carry_output: true },
      },
    });
    expect(fields.steps[2].policy).toBe("merge_approval");
    expect(fields.steps[4]).toEqual({ id: "done", role: "_builtin:mark_done", policy: null, then: {} });
  });

  it("moves a step and adds one", async () => {
    const { dialog } = await openSteps();
    fireEvent.click(within(dialog).getByRole("button", { name: "Move Review earlier" }));
    expect(within(dialog).getByLabelText("Name of step 2")).toHaveValue("Review");
    expect(within(dialog).getByRole("button", { name: "Move Develop earlier" })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Add a step" }));
    expect(within(dialog).getByLabelText("Name of step 7")).toHaveValue("");
    expect(within(dialog).getByLabelText("Who does step 7")).toHaveValue("developer");
  });

  it("refuses two steps with the same name before asking the API", async () => {
    const { fetchImpl, dialog } = await openSteps();
    fireEvent.change(within(dialog).getByLabelText("Name of step 2"), { target: { value: "Develop" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Two steps are called Develop.");
    expect(sent(fetchImpl, "PUT")).toHaveLength(0);
  });

  it("starts a new workflow as a copy of this one", async () => {
    const fetchImpl = createFakeFetch(settingsRoutes());
    renderApp(WORKFLOW, fetchImpl);
    await screen.findByRole("table", { name: "Steps of the workflow" });
    await waitFor(() => expect(screen.getByRole("button", { name: "New workflow" })).toBeEnabled());
    fetchImpl.routes[`PUT ${WORKFLOW_URL}/careful_development`] = definitionsPayload();
    fireEvent.click(screen.getByRole("button", { name: "New workflow" }));
    const dialog = await screen.findByRole("dialog", { name: "New workflow" });
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Careful development" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetchImpl, "PUT")).toHaveLength(1));
    expect(sent(fetchImpl, "PUT")[0].url).toBe(`${WORKFLOW_URL}/careful_development`);
    expect(sent(fetchImpl, "PUT")[0].body.copy_of).toBe("development");
  });
});
