import { fireEvent, render, screen } from "@testing-library/react";

import { RouterProvider } from "../app/router";
import { Tabs } from "./Tabs";

const items = [
  { href: "/dashboard/projects/p", label: "Sprints" },
  { href: "/dashboard/projects/p/backlog", label: "Backlog" },
  { href: "/dashboard/projects/p/activity", label: "Activity" },
];

describe("Tabs", () => {
  it("renders real links and marks the current one", () => {
    window.history.replaceState({}, "", "/dashboard/projects/p/backlog");
    render(
      <RouterProvider browser={window}>
        <Tabs label="Project" items={items} />
      </RouterProvider>,
    );
    expect(screen.getByRole("navigation", { name: "Project" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sprints" })).toHaveAttribute("href", "/dashboard/projects/p");
    expect(screen.getByRole("link", { name: "Backlog" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Backlog" })).toHaveClass("tabs__link--current");
    expect(screen.getByRole("link", { name: "Sprints" })).not.toHaveAttribute("aria-current");
  });

  it("moves the current tab when one is followed", () => {
    window.history.replaceState({}, "", "/dashboard/projects/p");
    render(
      <RouterProvider browser={window}>
        <Tabs label="Project" items={items} />
      </RouterProvider>,
    );
    fireEvent.click(screen.getByRole("link", { name: "Activity" }));
    expect(window.location.pathname).toBe("/dashboard/projects/p/activity");
    expect(screen.getByRole("link", { name: "Activity" })).toHaveAttribute("aria-current", "page");
  });
});
