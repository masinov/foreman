import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import App from "./App";

function createMockServices() {
  const streamHandlers = { onEvent: null, onError: null };

  const services = {
    listProjects: vi.fn().mockResolvedValue({
      projects: [
        {
          id: "proj-1",
          name: "Foreman",
          status: "running",
          active_sprint: { id: "sprint-1", title: "React foundation" },
          task_counts: {
            todo: 1,
            in_progress: 1,
            blocked: 1,
            done: 0,
            cancelled: 0,
          },
          totals: {
            run_count: 3,
            total_token_count: 42000,
            total_cost_usd: 1.25,
          },
        },
      ],
    }),
    getProject: vi.fn().mockResolvedValue({
      id: "proj-1",
      name: "Foreman",
      workflow_id: "development_secure",
      default_branch: "main",
      repo_path: "/tmp/foreman",
    }),
    listProjectSprints: vi.fn().mockResolvedValue({
      sprints: [
        {
          id: "sprint-1",
          title: "React foundation",
          goal: "Ship the dedicated frontend.",
          status: "active",
          task_counts: {
            todo: 1,
            in_progress: 1,
            blocked: 1,
            done: 0,
            cancelled: 0,
            total: 3,
          },
          totals: {
            run_count: 3,
            total_token_count: 42000,
            total_cost_usd: 1.25,
          },
        },
      ],
    }),
    getSprint: vi.fn().mockResolvedValue({
      id: "sprint-1",
      title: "React foundation",
      goal: "Ship the dedicated frontend.",
      status: "active",
      task_counts: {
        todo: 1,
        in_progress: 1,
        blocked: 1,
        done: 0,
        cancelled: 0,
      },
      totals: {
        run_count: 3,
        total_token_count: 42000,
        total_cost_usd: 1.25,
      },
    }),
    listSprintTasks: vi.fn().mockResolvedValue({
      tasks: [
        {
          id: "task-1",
          title: "Plan the split",
          status: "todo",
          task_type: "feature",
          branch_name: null,
          assigned_role: "architect",
          blocked_reason: null,
          acceptance_criteria: "Architecture split is documented.",
          totals: { run_count: 0, total_token_count: 0, total_cost_usd: 0 },
        },
        {
          id: "task-2",
          title: "Build the frontend",
          status: "in_progress",
          task_type: "feature",
          branch_name: "feat/react-dashboard-foundation",
          assigned_role: "developer",
          blocked_reason: null,
          acceptance_criteria: "React dashboard ships over FastAPI.",
          totals: { run_count: 2, total_token_count: 42000, total_cost_usd: 1.25 },
        },
        {
          id: "task-3",
          title: "Review release surface",
          status: "blocked",
          task_type: "bug",
          branch_name: "feat/react-dashboard-foundation",
          assigned_role: "security_reviewer",
          blocked_reason: "Awaiting human approval",
          acceptance_criteria: "Gate is resolved with a human decision.",
          totals: { run_count: 1, total_token_count: 18000, total_cost_usd: 0.5 },
        },
      ],
    }),
    listSprintEvents: vi.fn().mockResolvedValue({
      events: [
        {
          id: "event-1",
          task_id: "task-2",
          project_id: "proj-1",
          event_type: "agent.message",
          timestamp: "2026-03-31T09:00:00Z",
          role_id: "developer",
          payload: { text: "Building the new dashboard shell." },
        },
      ],
    }),
    getTask: vi.fn().mockImplementation(async (taskId) => ({
      id: taskId,
      title: taskId === "task-3" ? "Review release surface" : "Build the frontend",
      status: taskId === "task-3" ? "blocked" : "in_progress",
      task_type: taskId === "task-3" ? "bug" : "feature",
      branch_name: "feat/react-dashboard-foundation",
      assigned_role: taskId === "task-3" ? "security_reviewer" : "developer",
      created_by: "architect",
      blocked_reason: taskId === "task-3" ? "Awaiting human approval" : null,
      acceptance_criteria:
        taskId === "task-3"
          ? "Human gate outcome is persisted."
          : "React dashboard ships over FastAPI.",
      workflow_current_step: taskId === "task-3" ? "human_approval" : "develop",
      step_visit_counts: { develop: 1, review: 1 },
      totals: {
        run_count: taskId === "task-3" ? 1 : 2,
        total_token_count: taskId === "task-3" ? 18000 : 42000,
        total_cost_usd: taskId === "task-3" ? 0.5 : 1.25,
      },
      runs: [
        {
          id: `${taskId}-run-1`,
          role_id: taskId === "task-3" ? "security_reviewer" : "developer",
          workflow_step: taskId === "task-3" ? "security_review" : "develop",
          agent_backend: "claude",
          status: "completed",
          outcome: "success",
          outcome_detail: "Run finished cleanly.",
          token_count: taskId === "task-3" ? 18000 : 42000,
          cost_usd: taskId === "task-3" ? 0.5 : 1.25,
          duration_ms: 1800,
          created_at: "2026-03-31T09:00:00Z",
          model: "claude-sonnet",
        },
      ],
    })),
    approveTask: vi.fn().mockResolvedValue({
      status: "approved",
      task_id: "task-3",
      next_step: "develop",
      deferred: true,
    }),
    denyTask: vi.fn().mockResolvedValue({
      status: "denied",
      task_id: "task-3",
      next_step: "develop",
      deferred: true,
    }),
    createHumanMessage: vi.fn().mockResolvedValue({
      status: "sent",
      task_id: "task-2",
      event_id: "event-2",
    }),
    openSprintStream: vi.fn().mockImplementation((_sprintId, _options, handlers) => {
      streamHandlers.onEvent = handlers.onEvent;
      streamHandlers.onError = handlers.onError;
      return () => {};
    }),
  };

  return {
    services,
    emitEvent(payload) {
      streamHandlers.onEvent?.(payload);
    },
  };
}

describe("React dashboard foundation", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/dashboard");
  });

  it("renders the project overview and navigates to the sprint list", async () => {
    const { services } = createMockServices();
    render(<App services={services} browser={window} />);

    expect(await screen.findByText("Projects")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Open project Foreman" }));

    expect(await screen.findByText("React foundation")).toBeInTheDocument();
    expect(services.getProject).toHaveBeenCalledWith("proj-1");
    expect(services.listProjectSprints).toHaveBeenCalledWith("proj-1");
  });

  it("sends human guidance through the selected task context", async () => {
    const { services } = createMockServices();
    window.history.replaceState({}, "", "/dashboard/projects/proj-1/sprints/sprint-1");

    render(<App services={services} browser={window} />);

    expect(await screen.findByText("Build the frontend")).toBeInTheDocument();
    const textarea = await screen.findByLabelText("Human guidance");
    fireEvent.change(textarea, { target: { value: "Add a regression test for the stream reconnect path." } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(services.createHumanMessage).toHaveBeenCalledWith(
        "task-2",
        "Add a regression test for the stream reconnect path.",
      );
    });
  });

  it("updates the activity feed when the sprint stream emits a new event", async () => {
    const { services, emitEvent } = createMockServices();
    window.history.replaceState({}, "", "/dashboard/projects/proj-1/sprints/sprint-1");

    render(<App services={services} browser={window} />);

    expect(await screen.findByText("Building the new dashboard shell.")).toBeInTheDocument();

    await act(async () => {
      emitEvent({
        type: "event",
        event: {
          id: "event-2",
          task_id: "task-3",
          project_id: "proj-1",
          event_type: "human.message",
          timestamp: "2026-03-31T09:05:00Z",
          role_id: "human",
          payload: { text: "Approved. Continue to the merge step." },
        },
      });
    });

    expect(await screen.findByText("Approved. Continue to the merge step.")).toBeInTheDocument();
    expect(services.openSprintStream).toHaveBeenCalled();
  });
});
