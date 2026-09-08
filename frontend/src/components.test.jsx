import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { WorktreePanel } from "./components";

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
  it("shows the live task-tree count against the cap", async () => {
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

    await waitFor(() => expect(screen.getByText("2 / 4")).toBeInTheDocument());
    expect(screen.getByText("/tmp/repo/.foreman/worktrees")).toBeInTheDocument();
  });

  it("omits the cap when it is disabled", async () => {
    const services = {
      listWorktrees: vi.fn().mockResolvedValue(payload([tree("FOR-1")], { limit: 0 })),
      pruneWorktrees: vi.fn(),
    };

    render(<WorktreePanel project={PROJECT} services={services} />);

    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
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
    await waitFor(() => expect(screen.getByText("2 / 4")).toBeInTheDocument());

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /prune worktrees/i }));
    });

    expect(services.pruneWorktrees).toHaveBeenCalledWith("proj-1");
    await waitFor(() => expect(screen.getByText("1 / 4")).toBeInTheDocument());
  });

  it("says there is nothing to prune when every tree is live", async () => {
    const services = {
      listWorktrees: vi.fn().mockResolvedValue(payload([tree("FOR-1")])),
      pruneWorktrees: vi.fn(),
    };

    render(<WorktreePanel project={PROJECT} services={services} />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /prune worktrees/i })).toHaveAttribute(
        "title",
        "Nothing to prune: every worktree belongs to a live task",
      ),
    );
  });

  it("surfaces a failed prune instead of leaving a stale count", async () => {
    const services = {
      listWorktrees: vi.fn().mockResolvedValue(payload([tree("FOR-1")])),
      pruneWorktrees: vi.fn().mockRejectedValue(new Error("worktree root is not ignored")),
    };

    render(<WorktreePanel project={PROJECT} services={services} />);
    await waitFor(() => expect(screen.getByText("1 / 4")).toBeInTheDocument());

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /prune worktrees/i }));
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
