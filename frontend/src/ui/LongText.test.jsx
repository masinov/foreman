import { readFileSync } from "node:fs";
import { join } from "node:path";

import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { LongText } from "./LongText";

/** jsdom lays nothing out, so say how tall the text is and how much shows. */
function heights(full, shown) {
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(full);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(shown);
}

describe("LongText", () => {
  it("everything that opens more in place has one look: gold, a control's type, a caret", () => {
    const styles = (name) => readFileSync(join(process.cwd(), "src", "styles", name), "utf8");
    const css = styles("ui.css");
    const rule = css.slice(css.indexOf(".expander,"), css.indexOf(".expander:hover"));
    expect(rule).toMatch(/color: var\(--color-expander\);/);
    expect(rule).toMatch(/font-size: var\(--font-size-control\);/);
    expect(rule).toMatch(/font-weight: var\(--font-weight-medium\);/);
    expect(styles("tokens.css")).toMatch(/--color-expander: var\(--color-gold\);/);
  });

  afterEach(() => vi.restoreAllMocks());

  it("shows short text whole, with nothing to press", () => {
    heights(40, 40);
    render(<LongText>One line.</LongText>);
    expect(screen.getByText("One line.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("folds text that runs past its height and opens it in place", () => {
    heights(900, 216);
    render(<LongText>A long text.</LongText>);
    const text = screen.getByText("A long text.");
    const button = screen.getByRole("button", { name: "Show all" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls", text.id);
    expect(text).toHaveClass("long-text__text--folded");
    // A caret marks it as a control; it points the other way once open.
    expect(button).toHaveClass("expander");
    expect(button.querySelector(".caret")).toHaveClass("caret--down");

    fireEvent.click(button);
    expect(text).not.toHaveClass("long-text__text--folded");
    expect(button.querySelector(".caret")).toHaveClass("caret--up");
    expect(screen.getByRole("button", { name: "Show less" })).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(text).toHaveClass("long-text__text--folded");
  });
});
