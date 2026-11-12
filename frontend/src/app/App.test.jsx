import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp } from "../testing/fakeApi";
import { workspaceRoutes } from "../testing/workspaceFixture";
import { settingsRoutes } from "../testing/settingsFixture";

function goBack() {
  return act(async () => {
    window.history.back();
    await new Promise((resolve) => window.addEventListener("popstate", resolve, { once: true }));
  });
}

describe("App routing and shell", () => {
  it("renders the workspace with the word, the breadcrumb and no manager", async () => {
    renderApp("/dashboard", createFakeFetch(workspaceRoutes()));
    const banner = screen.getByRole("banner");
    expect(within(banner).getByRole("link", { name: "Foreman" })).toHaveAttribute("href", "/dashboard");
    const crumbs = within(banner).getByRole("navigation", { name: "Breadcrumb" });
    // The wordmark is the one link to the workspace; the breadcrumb is empty here.
    expect(within(crumbs).queryAllByRole("listitem")).toHaveLength(0);
    expect(within(banner).getByRole("link", { name: "Workspace settings" })).toHaveAttribute("href", "/dashboard/settings");
    expect(document.querySelector(".manager-slot")).toBeNull();
    expect(within(banner).queryByRole("button", { name: "Manager" })).toBeNull();
    expect(await screen.findByText("FOR-14")).toBeInTheDocument();
    expect(document.title).toBe("Workspace · Foreman");
  });

  it("renders the shared not-built page naming the commands that do the job, and no link away", async () => {
    renderApp("/dashboard/settings", createFakeFetch(workspaceRoutes()));
    expect(screen.getByRole("heading", { name: "This page is not built yet" })).toBeInTheDocument();
    const commands = screen.getByRole("list", { name: "Commands" });
    expect(within(commands).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "foreman roles",
      "foreman workflows",
    ]);
    const page = document.querySelector(".status-page");
    expect(within(page).queryAllByRole("link")).toHaveLength(0);
    expect(page.innerHTML).not.toMatch(/legacy|previous dashboard/i);
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).queryByRole("link")).toBeNull();
    expect(within(crumbs).getByText("Workspace settings")).toHaveAttribute("aria-current", "page");
  });

  it("puts project settings below the project in the breadcrumb", async () => {
    renderApp("/dashboard/projects/foreman/settings/workflow", createFakeFetch(settingsRoutes()));
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(await within(crumbs).findByRole("link", { name: "Foreman" })).toHaveAttribute("href", "/dashboard/projects/foreman");
    expect(within(crumbs).getByText("Settings")).toHaveAttribute("aria-current", "page");
  });

  it("switches project from the breadcrumb, with what waits in each", async () => {
    renderApp("/dashboard/projects/other/backlog", createFakeFetch(workspaceRoutes()));
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    const switcher = await within(crumbs).findByRole("button", { name: "Other project" });
    expect(switcher).toHaveAttribute("aria-haspopup", "menu");
    fireEvent.click(switcher);
    const menu = screen.getByRole("menu", { name: "Projects" });
    expect(within(menu).getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Foreman2", "Other project"]);
    expect(within(menu).getByRole("menuitem", { name: "Other project" })).toHaveFocus();
    fireEvent.keyDown(menu, { key: "ArrowUp" });
    const foreman = within(menu).getByRole("menuitem", { name: /Foreman/ });
    expect(foreman).toHaveFocus();
    expect(foreman).toHaveAttribute("href", "/dashboard/projects/foreman");
    fireEvent.click(foreman);
    expect(window.location.pathname).toBe("/dashboard/projects/foreman");
    expect(await within(crumbs).findByRole("button", { name: "Foreman 2 need you" })).toBeInTheDocument();
  });

  it("names the command that does the job on a page that is not built yet", () => {
    renderApp("/dashboard/settings");
    const commands = screen.getByRole("list", { name: "Commands" });
    expect(within(commands).getByText("foreman roles")).toBeInTheDocument();
  });

  it("renders not-found at the old legacy address", () => {
    renderApp("/dashboard/legacy");
    expect(screen.getByRole("heading", { name: "Nothing is at this address" })).toBeInTheDocument();
    expect(within(document.querySelector(".status-page")).queryAllByRole("link", { name: /dashboard/i })).toHaveLength(0);
  });

  it("renders not-found for an unknown path", () => {
    renderApp("/dashboard/what");
    expect(screen.getByRole("heading", { name: "Nothing is at this address" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the workspace" })).toHaveAttribute("href", "/dashboard");
  });

  it("follows a link without a page load, and back returns", async () => {
    renderApp("/dashboard", createFakeFetch(workspaceRoutes()));
    const link = await screen.findByRole("link", { name: "Make the test step report what happened" });
    expect(link.tagName).toBe("A");

    fireEvent.click(link);
    expect(window.location.pathname).toBe("/dashboard/tasks/task-merge");
    expect(await screen.findByRole("heading", { name: "This task could not be shown" })).toBeInTheDocument();

    await goBack();
    expect(window.location.pathname).toBe("/dashboard");
    await waitFor(() => expect(screen.getByRole("region", { name: /Needs you/ })).toBeInTheDocument());
  });

  it("leaves a modified click to the browser", async () => {
    renderApp("/dashboard/settings", createFakeFetch(workspaceRoutes()));
    const link = within(screen.getByRole("banner")).getByRole("link", { name: "Foreman" });
    let preventedByApp = null;
    // Runs after the application's handler; stops jsdom from attempting a real page load.
    const observe = (event) => {
      preventedByApp = event.defaultPrevented;
      event.preventDefault();
    };
    window.addEventListener("click", observe, { once: true });
    link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0, ctrlKey: true }));
    expect(preventedByApp).toBe(false);
    expect(window.location.pathname).toBe("/dashboard/settings");
  });
});
