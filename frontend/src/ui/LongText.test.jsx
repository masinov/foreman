import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { LongText } from "./LongText";

/** jsdom lays nothing out, so say how tall the text is and how much shows. */
function heights(full, shown) {
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(full);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(shown);
}

describe("LongText", () => {
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

    fireEvent.click(button);
    expect(text).not.toHaveClass("long-text__text--folded");
    expect(screen.getByRole("button", { name: "Show less" })).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(text).toHaveClass("long-text__text--folded");
  });
});
