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
    expect(within(table).getByText("No tools")).toBeInTheDocument();
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
    fireEvent.click(within(dialog).getByRole("button", { name: "Back to the default role" }));

    await waitFor(() => expect(sent(fetchImpl, "DELETE")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("offers no way back for a role as shipped", async () => {
    const { dialog } = await openRole();
    expect(within(dialog).queryByRole("button", { name: /Back to the/ })).toBeNull();
    expect(within(dialog).queryByRole("button", { name: /Remove this/ })).toBeNull();
  });
});

describe("A new role", () => {
  it("starts as a copy of a chosen role and is saved under an id made from its name", async () => {
    const fetchImpl = await renderRoles();
    fetchImpl.routes[`PUT ${ROLE_URL}/strict_reviewer`] = definitionsPayload();
    fireEvent.click(screen.getByRole("button", { name: "New role" }));
    const start = await screen.findByRole("dialog", { name: "New role" });
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

  it("starts empty unless a role to copy is chosen", async () => {
    const fetchImpl = await renderRoles();
    fetchImpl.routes[`PUT ${ROLE_URL}/doc_writer`] = definitionsPayload();
    fireEvent.click(screen.getByRole("button", { name: "New role" }));
    const start = await screen.findByRole("dialog", { name: "New role" });
    expect(within(start).getByLabelText("Start from")).toHaveDisplayValue("An empty role");
    fireEvent.click(within(start).getByRole("button", { name: "Continue" }));

    const form = await screen.findByRole("dialog", { name: "New role" });
    expect(await within(form).findByLabelText("Prompt")).toHaveValue("Say here what this role does.\n{completion_marker}");
    expect(within(form).getByLabelText("What it does")).toHaveValue("");
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Doc writer" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetchImpl, "PUT")).toHaveLength(1));
    expect(sent(fetchImpl, "PUT")[0].url).toBe(`${ROLE_URL}/doc_writer`);
    expect(sent(fetchImpl, "PUT")[0].body.copy_of).toBe("_blank");
  });
});

describe("A role's model", () => {
  it("is chosen from a list, with the project's default first", async () => {
    const { fetchImpl, dialog } = await openRole();
    fetchImpl.routes[`PUT ${ROLE_URL}/code_reviewer`] = definitionsPayload();
    const model = within(dialog).getByLabelText("Model");
    expect(model.tagName).toBe("SELECT");
    expect(model).toHaveValue("claude-sonnet-5-5");
    expect(within(model).getAllByRole("option")[0]).toHaveTextContent(/default/);
    fireEvent.change(model, { target: { value: "" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetchImpl, "PUT")).toHaveLength(1));
    expect(sent(fetchImpl, "PUT")[0].body.fields.model).toBe("");
  });

  it("takes a model the list does not have", async () => {
    const { fetchImpl, dialog } = await openRole();
    fetchImpl.routes[`PUT ${ROLE_URL}/code_reviewer`] = definitionsPayload();
    expect(within(dialog).queryByLabelText("Model id")).toBeNull();
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "_other" } });
    fireEvent.change(within(dialog).getByLabelText("Model id"), { target: { value: "some-new-model" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetchImpl, "PUT")).toHaveLength(1));
    expect(sent(fetchImpl, "PUT")[0].body.fields.model).toBe("some-new-model");
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

  // The step whose fields are shown beside the graph.
  const choose = (dialog, title) => fireEvent.click(within(dialog).getByRole("button", { name: new RegExp(`^Step \\d+: ${title}$`) }));
  const picked = (dialog, label) => within(within(dialog).getByLabelText(label)).getByRole("option", { selected: true });

  it("opens as a graph: the steps in order, with a line wherever a task leaves the order", async () => {
    const { dialog } = await openSteps();
    const graph = within(dialog).getByRole("group", { name: "Steps" });
    // The step that marks a task done is the end of the graph, not a step to edit.
    expect(within(graph).getAllByRole("button").map((node) => node.getAttribute("aria-label"))).toEqual([
      "Step 1: Develop",
      "Step 2: Test",
      "Step 3: Review",
      "Step 4: Merge approval",
      "Step 5: Merge",
    ]);
    expect(graph).toHaveTextContent("Done");
    // In words under each step: what does not simply go on to the next one.
    expect(graph).toHaveTextContent("fail ↩ 1");
    expect(graph).toHaveTextContent("denies, steers ↩ 1");
    expect(graph).toHaveTextContent("fails, conflict ↩ 1");
    // Every way back leads to Develop: one line beside the rail.
    expect(graph.querySelectorAll(".wf-graph__line")).toHaveLength(1);

    // The first step is shown beside it; another is one click away.
    expect(within(dialog).getByLabelText("Name of step 1")).toHaveValue("Develop");
    choose(dialog, "Test");
    expect(within(dialog).getByLabelText("Name of step 2")).toHaveValue("Test");
    expect(within(dialog).getByLabelText("Who does Test")).toHaveValue("_builtin:run_tests");
    expect(picked(dialog, "Test: when the tests pass")).toHaveTextContent("on to 3 · Review");
    expect(picked(dialog, "Test: when the tests fail")).toHaveTextContent("back to 1 · Develop");
    choose(dialog, "Merge");
    expect(picked(dialog, "Merge: when it merges")).toHaveTextContent("the task is done");
    expect(within(dialog).queryByRole("checkbox")).toBeNull();
  });

  it("saves the shipped workflow exactly as it was when nothing is changed", async () => {
    const { fetchImpl, dialog } = await openSteps();
    fetchImpl.routes[`PUT ${WORKFLOW_URL}/development`] = definitionsPayload();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetchImpl, "PUT")).toHaveLength(1));
    const { fields } = sent(fetchImpl, "PUT")[0].body;
    const before = definitionsPayload().workflows.find((workflow) => workflow.id === "development");
    expect(fields.steps).toEqual(
      before.steps.map((step) => ({ id: step.id, role: step.role, policy: step.policy ?? null, then: step.then })),
    );
  });

  it("saves the steps: one removed, another sent elsewhere, a renamed step still pointed at", async () => {
    const { fetchImpl, dialog } = await openSteps();
    fetchImpl.routes[`PUT ${WORKFLOW_URL}/development`] = definitionsPayload();
    choose(dialog, "Review");
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove Review" }));
    // With Review gone, the tests passing leads on to what is now below: the approval.
    choose(dialog, "Test");
    expect(picked(dialog, "Test: when the tests pass")).toHaveTextContent("on to 3 · Merge approval");
    choose(dialog, "Develop");
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

  it("keeps the sequence when a step is moved or added", async () => {
    const { fetchImpl, dialog } = await openSteps();
    fetchImpl.routes[`PUT ${WORKFLOW_URL}/development`] = definitionsPayload();
    expect(within(dialog).getByRole("button", { name: "Move Develop up" })).toBeDisabled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Add a step" }));
    // The new step is the last one and is the one shown; the merge now leads on to it.
    fireEvent.change(within(dialog).getByLabelText("Name of step 6"), { target: { value: "Announce" } });
    expect(within(dialog).getByLabelText("Who does Announce")).toHaveValue("developer");
    expect(picked(dialog, "Announce: when it says it is done")).toHaveTextContent("the task is done");

    // Choosing who does a step fills in where each of its endings leads: on,
    // and otherwise back to the last step that did the work.
    fireEvent.change(within(dialog).getByLabelText("Who does Announce"), { target: { value: "code_reviewer" } });
    expect(picked(dialog, "Announce: when it approves")).toHaveTextContent("the task is done");
    expect(picked(dialog, "Announce: when it denies")).toHaveTextContent("back to 1 · Develop");

    fireEvent.click(within(dialog).getByRole("button", { name: "Move Announce up" }));
    expect(within(dialog).getByLabelText("Name of step 5")).toHaveValue("Announce");
    expect(picked(dialog, "Announce: when it approves")).toHaveTextContent("on to 6 · Merge");
    choose(dialog, "Merge approval");
    expect(picked(dialog, "Merge approval: when the user approves")).toHaveTextContent("on to 5 · Announce");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetchImpl, "PUT")).toHaveLength(1));
    const { steps } = sent(fetchImpl, "PUT")[0].body.fields;
    expect(steps.map((step) => step.id)).toEqual(["develop", "test", "review", "merge_approval", "announce", "merge", "done"]);
    expect(steps[4].then).toEqual({
      approve: { to: "merge", carry_output: false },
      deny: { to: "develop", carry_output: true },
      steer: { to: "develop", carry_output: true },
    });
    expect(steps[5].then.success).toEqual({ to: "done", carry_output: false });
  });

  it("refuses two steps with the same name before asking the API", async () => {
    const { fetchImpl, dialog } = await openSteps();
    fireEvent.click(within(dialog).getByRole("button", { name: "Step 2: Test" }));
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
    const start = await screen.findByRole("dialog", { name: "New workflow" });
    expect(within(start).getByLabelText("Start from")).toHaveDisplayValue("An empty workflow");
    fireEvent.change(within(start).getByLabelText("Start from"), { target: { value: "development" } });
    fireEvent.click(within(start).getByRole("button", { name: "Continue" }));
    const dialog = await screen.findByRole("dialog", { name: "New workflow" });
    await within(dialog).findByLabelText("Name");
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Careful development" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent(fetchImpl, "PUT")).toHaveLength(1));
    expect(sent(fetchImpl, "PUT")[0].url).toBe(`${WORKFLOW_URL}/careful_development`);
    expect(sent(fetchImpl, "PUT")[0].body.copy_of).toBe("development");
  });
});
