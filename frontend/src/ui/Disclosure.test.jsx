import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { Disclosure } from "./Disclosure";

describe("Disclosure", () => {
  it("is closed, renders nothing inside, and opens in place", () => {
    const onToggle = vi.fn();
    render(
      <Disclosure summary="Finished sprints 3" onToggle={onToggle}>
        <p>Sprint 55</p>
      </Disclosure>,
    );
    const button = screen.getByRole("button", { name: "Finished sprints 3" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Sprint 55")).toBeNull();

    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Sprint 55")).toBeInTheDocument();
    expect(document.getElementById(button.getAttribute("aria-controls"))).toContainElement(screen.getByText("Sprint 55"));
    expect(onToggle).toHaveBeenLastCalledWith(true);

    fireEvent.click(button);
    expect(screen.queryByText("Sprint 55")).toBeNull();
    expect(onToggle).toHaveBeenLastCalledWith(false);
  });
});
