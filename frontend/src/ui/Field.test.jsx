import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { Field } from "./Field";

describe("Field", () => {
  it("labels its input and passes props through", () => {
    const onChange = vi.fn();
    render(<Field label="Title" value="" onChange={onChange} required />);
    const input = screen.getByRole("textbox", { name: "Title" });
    expect(input).toBeRequired();
    expect(input).toHaveClass("field__input");
    fireEvent.change(input, { target: { value: "Sprint 59" } });
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("ties a hint and an error to the input and marks it invalid", () => {
    render(<Field label="Title" hint="Starts with the sprint number." error="A sprint needs a title." />);
    const input = screen.getByRole("textbox", { name: "Title" });
    expect(input).toHaveAccessibleDescription("Starts with the sprint number. A sprint needs a title.");
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("can be a textarea and can hide its label visually", () => {
    render(
      <>
        <Field label="Goal" multiline />
        <Field label="Filter finished sprints" hideLabel type="search" />
      </>,
    );
    expect(screen.getByRole("textbox", { name: "Goal" }).tagName).toBe("TEXTAREA");
    const search = screen.getByRole("searchbox", { name: "Filter finished sprints" });
    expect(screen.getByText("Filter finished sprints")).toHaveClass("visually-hidden");
    // Typing in it is ordinary keyboard input.
    search.focus();
    expect(search).toHaveFocus();
  });
});
