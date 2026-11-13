import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { RouterProvider } from "../app/router";
import { Menu } from "./Menu";

function renderMenu(onSelect = vi.fn()) {
  window.history.replaceState({}, "", "/dashboard/projects/b");
  render(
    <RouterProvider browser={window}>
      <p>outside</p>
      <Menu
        label="Projects"
        trigger="Beta"
        triggerLabel="Switch project"
        items={[
          { key: "a", label: "Alpha", detail: 2, href: "/dashboard/projects/a" },
          { key: "b", label: "Beta", detail: 0, href: "/dashboard/projects/b", current: true },
          { key: "c", label: "Gamma", onSelect },
        ]}
      />
    </RouterProvider>,
  );
  return { trigger: screen.getByRole("button", { name: "Switch project" }), onSelect };
}

describe("Menu", () => {
  it("opens on click with focus on the current item, and closes on Escape back to the button", () => {
    const { trigger } = renderMenu();
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("menu")).toBeNull();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const menu = screen.getByRole("menu", { name: "Projects" });
    expect(trigger).toHaveAttribute("aria-controls", menu.id);
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Alpha2", "Beta0", "Gamma"]);
    expect(screen.getByRole("menuitem", { name: /Beta/ })).toHaveFocus();
    expect(screen.getByRole("menuitem", { name: /Beta/ })).toHaveAttribute("aria-current", "page");

    fireEvent.keyDown(menu, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it("moves with the arrow keys, wrapping, and Home and End", () => {
    const { trigger } = renderMenu();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const menu = screen.getByRole("menu");
    const item = (name) => screen.getByRole("menuitem", { name: new RegExp(name) });
    expect(item("Beta")).toHaveFocus();
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(item("Gamma")).toHaveFocus();
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(item("Alpha")).toHaveFocus();
    fireEvent.keyDown(menu, { key: "ArrowUp" });
    expect(item("Gamma")).toHaveFocus();
    fireEvent.keyDown(menu, { key: "Home" });
    expect(item("Alpha")).toHaveFocus();
    fireEvent.keyDown(menu, { key: "End" });
    expect(item("Gamma")).toHaveFocus();
    // Only the focused item is in the tab order.
    expect(item("Gamma")).toHaveAttribute("tabindex", "0");
    expect(item("Alpha")).toHaveAttribute("tabindex", "-1");
  });

  it("opens from the keyboard: Enter and Space press the button", () => {
    const { trigger } = renderMenu();
    trigger.focus();
    // A button turns Enter and Space into a click; the menu opens on it.
    fireEvent.keyDown(trigger, { key: "Enter" });
    fireEvent.click(trigger);
    expect(screen.getByRole("menu")).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    fireEvent.keyDown(trigger, { key: " " });
    fireEvent.click(trigger);
    expect(screen.getByRole("menu")).toBeInTheDocument();
  });

  it("closes on a click outside", () => {
    const { trigger } = renderMenu();
    fireEvent.click(trigger);
    fireEvent.mouseDown(screen.getByText("outside"));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("follows a link item and runs an action item, returning focus to the button", () => {
    const { trigger, onSelect } = renderMenu();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("menuitem", { name: /Alpha/ }));
    expect(window.location.pathname).toBe("/dashboard/projects/a");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(trigger).toHaveFocus();

    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("menuitem", { name: "Gamma" }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(trigger).toHaveFocus();
  });

  it("opens leftwards when its button is in the right half of the window", () => {
    const { trigger } = renderMenu();
    fireEvent.click(trigger);
    expect(screen.getByRole("menu")).not.toHaveClass("menu__list--end");
    fireEvent.click(trigger);

    vi.spyOn(trigger, "getBoundingClientRect").mockReturnValue({ left: window.innerWidth - 60, width: 50 });
    fireEvent.click(trigger);
    expect(screen.getByRole("menu")).toHaveClass("menu__list--end");
  });
});
