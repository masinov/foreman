import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp, reply } from "../testing/fakeApi";
import { accessRoutes } from "../testing/accessFixture";
import { workspaceRoutes } from "../testing/workspaceFixture";

const TOKEN_SESSION = {
  authentication: "token",
  name: "Dashboard token",
  can_sign_out: true,
  identity_provider: null,
};

function trigger(name) {
  return within(screen.getByRole("banner")).findByRole("button", { name: new RegExp(`^You: ${name}`) });
}

describe("The user menu", () => {
  afterEach(() => window.localStorage.clear());

  it("shows who the server says is acting, at the right end of the bar", async () => {
    renderApp("/dashboard", createFakeFetch(workspaceRoutes()));
    const button = await trigger("Local operator");
    expect(button).toHaveTextContent("Local operator");
    expect(button).toHaveAttribute("aria-haspopup", "menu");
    const right = document.querySelector(".topbar__right");
    expect(right.lastElementChild).toContainElement(button);
  });

  it.each([
    ["a project page", "/dashboard/projects/foreman"],
    ["the workspace settings", "/dashboard/settings"],
    ["a page that does not exist", "/dashboard/nowhere"],
  ])("is on %s", async (_, path) => {
    renderApp(path, createFakeFetch(accessRoutes()));
    expect(await trigger("Local operator")).toBeInTheDocument();
  });

  it("names the dashboard token when a token protects the dashboard", async () => {
    renderApp("/dashboard", createFakeFetch({ ...workspaceRoutes(), "GET /api/v1/session": TOKEN_SESSION }));
    expect(await trigger("Dashboard token")).toHaveTextContent("Dashboard token");
  });

  it("opens from the keyboard, links to workspace settings and offers no sign out without authentication", async () => {
    renderApp("/dashboard", createFakeFetch(workspaceRoutes()));
    const button = await trigger("Local operator");
    button.focus();
    fireEvent.keyDown(button, { key: "ArrowDown" });
    const menu = screen.getByRole("menu", { name: "You" });
    const items = within(menu).getAllByRole("menuitem");
    expect(items.map((item) => item.textContent)).toEqual(["Workspace settings"]);
    expect(items[0]).toHaveFocus();
    expect(items[0]).toHaveAttribute("href", "/dashboard/settings");
    fireEvent.keyDown(menu, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(button).toHaveFocus();
  });

  it("goes to workspace settings when chosen", async () => {
    renderApp("/dashboard", createFakeFetch(accessRoutes()));
    fireEvent.click(await trigger("Local operator"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Workspace settings" }));
    expect(window.location.pathname).toBe("/dashboard/settings");
    expect(await screen.findByRole("heading", { name: "Workspace settings", level: 1 })).toBeInTheDocument();
  });

  it("signs out of a token session by forgetting the token and loading the page again", async () => {
    window.localStorage.setItem("foreman.dashboard.token", "dash-secret");
    const reload = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...original, pathname: original.pathname, reload },
    });
    try {
      renderApp("/dashboard", createFakeFetch({ ...workspaceRoutes(), "GET /api/v1/session": TOKEN_SESSION }));
      const button = await trigger("Dashboard token");
      fireEvent.keyDown(button, { key: "Enter" });
      fireEvent.click(button);
      const menu = await screen.findByRole("menu", { name: "You" });
      fireEvent.click(within(menu).getByRole("menuitem", { name: "Sign out" }));
      expect(window.localStorage.getItem("foreman.dashboard.token")).toBeNull();
      expect(reload).toHaveBeenCalledTimes(1);
    } finally {
      Object.defineProperty(window, "location", { configurable: true, value: original });
    }
  });

  it("still offers workspace settings when the session cannot be read", async () => {
    renderApp(
      "/dashboard",
      createFakeFetch({
        ...workspaceRoutes(),
        "GET /api/v1/session": reply(500, { error: "Internal error. See the dashboard log.", code: "internal_error" }),
      }),
    );
    const link = await waitFor(() => within(screen.getByRole("banner")).getByRole("link", { name: "Workspace settings" }));
    expect(link).toHaveAttribute("href", "/dashboard/settings");
    expect(within(screen.getByRole("banner")).queryByRole("button", { name: /^You/ })).toBeNull();
  });
});
