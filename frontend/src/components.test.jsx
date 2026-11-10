import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { PolicyMatrixSection, TaskCard, TaskDetailDrawer, WorktreePanel } from "./components";

const PROJECT = { id: "proj-1", name: "Foreman" };

function payload(worktrees, { root = "/tmp/repo/.foreman/worktrees", limit = 4 } = {}) {
  return { project_id: "proj-1", root, max_live_worktrees: limit, worktrees };
}

function tree(slug, overrides = {}) {
  return {
    slug,
    path: `/tmp/repo/.foreman/worktrees/${slug}`,
    branch: `feat/${slug}`,
    exists: true,
    is_integration: false,
    task_id: `task-${slug}`,
    task_key: slug,
    task_status: "in_progress",
    ...overrides,
  };
}

describe("WorktreePanel", () => {
  it("shows stored copies separately from the configured storage limit", async () => {
    const services = {
      listWorktrees: vi.fn().mockResolvedValue(
        payload([
          tree("FOR-1"),
          tree("FOR-2"),
          // The integration tree is shared and never pruned, so it is not
          // part of the count the cap applies to.
          tree("_integration", { is_integration: true, task_id: null }),
        ]),
      ),
      pruneWorktrees: vi.fn(),
    };

    render(<WorktreePanel project={PROJECT} services={services} />);

    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("/tmp/repo/.foreman/worktrees")).not.toBeVisible();
    fireEvent.click(screen.getByText("Storage details"));
    expect(screen.getByText("/tmp/repo/.foreman/worktrees")).toBeVisible();
  });

  it("shows unlimited storage when the cap is disabled", async () => {
    const services = {
      listWorktrees: vi.fn().mockResolvedValue(payload([tree("FOR-1")], { limit: 0 })),
      pruneWorktrees: vi.fn(),
    };

    render(<WorktreePanel project={PROJECT} services={services} />);

    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
    expect(screen.getByText("Unlimited")).toBeInTheDocument();
  });

  it("prunes and reloads what the engine still holds", async () => {
    const services = {
      listWorktrees: vi
        .fn()
        .mockResolvedValueOnce(payload([tree("FOR-1"), tree("FOR-2", { task_status: "done" })]))
        .mockResolvedValue(payload([tree("FOR-1")])),
      pruneWorktrees: vi.fn().mockResolvedValue({ removed: [], kept: [] }),
    };

    render(<WorktreePanel project={PROJECT} services={services} />);
    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /remove unused copies/i }));
    });

    expect(services.pruneWorktrees).toHaveBeenCalledWith("proj-1");
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });

  it("says there is nothing to prune when every tree is live", async () => {
    const services = {
      listWorktrees: vi.fn().mockResolvedValue(payload([tree("FOR-1")])),
      pruneWorktrees: vi.fn(),
    };

    render(<WorktreePanel project={PROJECT} services={services} />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /remove unused copies/i })).toHaveAttribute(
        "title",
        "No unused copies: every copy belongs to an unfinished task",
      ),
    );
  });

  it("surfaces a failed prune instead of leaving a stale count", async () => {
    const services = {
      listWorktrees: vi.fn().mockResolvedValue(payload([tree("FOR-1")])),
      pruneWorktrees: vi.fn().mockRejectedValue(new Error("worktree root is not ignored")),
    };

    render(<WorktreePanel project={PROJECT} services={services} />);
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /remove unused copies/i }));
    });

    await waitFor(() =>
      expect(screen.getByText("worktree root is not ignored")).toBeInTheDocument(),
    );
  });

  it("renders nothing without a services binding", () => {
    const { container } = render(<WorktreePanel project={PROJECT} services={null} />);

    expect(container).toBeEmptyDOMElement();
  });
});

function drawerTask(overrides = {}) {
  return {
    id: "task-1",
    task_key: "FOR-9",
    title: "Disk full on web-3",
    status: "todo",
    task_type: "fix",
    priority: 0,
    branch_name: null,
    assigned_role: null,
    acceptance_criteria: null,
    workflow_current_step: null,
    step_visit_counts: {},
    depends_on_task_ids: [],
    executor_overrides: {},
    totals: { total_token_count: 0, total_cost_usd: 0, run_count: 0 },
    runs: [],
    ...overrides,
  };
}

describe("TaskDetailDrawer source", () => {
  it("shows the system, the reference, and the reporter of filed work", () => {
    render(
      <TaskDetailDrawer
        task={drawerTask({
          source: {
            system: "pagerduty",
            external_ref: "INC-42",
            url: null,
            reporter: "ana",
          },
        })}
        onClose={() => {}}
      />,
    );

    expect(screen.getByText("Source")).toBeInTheDocument();
    expect(screen.getByText("pagerduty")).toBeInTheDocument();
    expect(screen.getByText("INC-42")).toBeInTheDocument();
    expect(screen.getByText("ana")).toBeInTheDocument();
  });

  it("links the reference back to the filing system when a url is present", () => {
    render(
      <TaskDetailDrawer
        task={drawerTask({
          source: {
            system: "pagerduty",
            external_ref: "INC-42",
            url: "https://pd.example.com/INC-42",
            reporter: null,
          },
        })}
        onClose={() => {}}
      />,
    );

    const link = screen.getByRole("link", { name: "INC-42" });
    expect(link).toHaveAttribute("href", "https://pd.example.com/INC-42");
    // Opening a third-party link must not hand it back a window reference.
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.queryByText("Reporter")).not.toBeInTheDocument();
  });

  it("renders no Source section for a task a person created", () => {
    render(<TaskDetailDrawer task={drawerTask({ source: null })} onClose={() => {}} />);

    expect(screen.queryByText("Source")).not.toBeInTheDocument();
  });
});

describe("TaskDetailDrawer policy", () => {
  it("shows each decision with the layer that decided it", () => {
    render(
      <TaskDetailDrawer
        task={drawerTask({
          policy: {
            triage: { value: "human", source: "built_in_default" },
            plan_approval: { value: "human", source: "project_default" },
            merge_approval: { value: "auto", source: "task_type_rule", task_type: "fix" },
            notification: { value: "all", source: "task_override" },
          },
        })}
        onClose={() => {}}
      />,
    );

    expect(screen.getByText("Policy")).toBeInTheDocument();
    expect(screen.getByText("Merge approval")).toBeInTheDocument();
    expect(screen.getByText(/task type rule: fix/)).toBeInTheDocument();
    expect(screen.getByText(/task override/)).toBeInTheDocument();
  });

  it("renders no Policy section when the payload carries none", () => {
    render(<TaskDetailDrawer task={drawerTask({ policy: null })} onClose={() => {}} />);

    expect(screen.queryByText("Policy")).not.toBeInTheDocument();
  });
});

describe("TaskCard triage", () => {
  function triageTask(overrides = {}) {
    return {
      id: "task-1",
      task_key: "FOR-9",
      title: "Disk full on web-3",
      status: "triage",
      task_type: "fix",
      branch_name: null,
      assigned_role: null,
      totals: { total_token_count: 0 },
      ...overrides,
    };
  }

  it("offers Accept on a task waiting in triage", () => {
    const onAccept = vi.fn();
    render(
      <TaskCard task={triageTask()} selected={false} onSelect={() => {}} onAccept={onAccept} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(onAccept).toHaveBeenCalledWith("task-1");
  });

  it("offers no Accept once the task has been queued", () => {
    render(
      <TaskCard
        task={triageTask({ status: "todo" })}
        selected={false}
        onSelect={() => {}}
        onAccept={() => {}}
      />,
    );

    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument();
  });
});

describe("PolicyMatrixSection", () => {
  it("shows the four defaults, falling back to the built-ins", () => {
    render(<PolicyMatrixSection settings={{ merge_approval: "human" }} onChange={() => {}} />);

    expect(screen.getByLabelText("Triage")).toHaveValue("human");
    expect(screen.getByLabelText("Merge approval")).toHaveValue("human");
    expect(screen.getByLabelText("Notification")).toHaveValue("attention");
  });

  it("writes a default change back through onChange", () => {
    const onChange = vi.fn();
    render(<PolicyMatrixSection settings={{}} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("Triage"), { target: { value: "auto" } });

    expect(onChange).toHaveBeenCalledWith("triage", "auto");
  });

  it("adds a task type rule row and edits one decision on it", () => {
    const onChange = vi.fn();
    const { rerender } = render(<PolicyMatrixSection settings={{}} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("Add a task type rule"), {
      target: { value: "docs" },
    });
    expect(onChange).toHaveBeenCalledWith("policy_rules", { docs: {} });

    rerender(
      <PolicyMatrixSection settings={{ policy_rules: { docs: {} } }} onChange={onChange} />,
    );
    fireEvent.change(screen.getByLabelText("docs Merge approval"), {
      target: { value: "auto" },
    });

    expect(onChange).toHaveBeenLastCalledWith("policy_rules", {
      docs: { merge_approval: "auto" },
    });
  });

  it("drops a rule row once its last decision is cleared", () => {
    const onChange = vi.fn();
    render(
      <PolicyMatrixSection
        settings={{ policy_rules: { docs: { triage: "auto" } } }}
        onChange={onChange}
      />,
    );

    fireEvent.change(screen.getByLabelText("docs Triage"), { target: { value: "" } });

    expect(onChange).toHaveBeenCalledWith("policy_rules", {});
  });
});
