import { render, screen } from "@testing-library/react";

import { StatusDot } from "./StatusDot";

describe("StatusDot", () => {
  it("is a dot and a word, the word carrying the meaning", () => {
    const { container } = render(<StatusDot tone="running">Running</StatusDot>);
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("status", "status--running");
    expect(container.querySelector(".status__dot")).toHaveAttribute("aria-hidden", "true");
  });

  it("falls back to idle for an unknown tone", () => {
    const { container } = render(<StatusDot tone="sparkly">Odd</StatusDot>);
    expect(container.firstChild).toHaveClass("status--idle");
  });
});
