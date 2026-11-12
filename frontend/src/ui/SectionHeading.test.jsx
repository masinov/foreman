import { render, screen } from "@testing-library/react";

import { SectionHeading } from "./SectionHeading";

describe("SectionHeading", () => {
  it("shows the title, the count and the note", () => {
    render(<SectionHeading title="Needs you" count={3} note="across all projects" />);
    expect(screen.getByRole("heading", { level: 2, name: "Needs you 3" })).toBeInTheDocument();
    expect(screen.getByText("across all projects")).toHaveClass("section-heading__note");
  });

  it("shows a zero count and omits a missing one", () => {
    const { rerender } = render(<SectionHeading title="Needs you" count={0} />);
    expect(screen.getByRole("heading", { name: "Needs you 0" })).toBeInTheDocument();
    rerender(<SectionHeading title="Projects" level={3} actions={<button type="button">Add</button>} />);
    expect(screen.getByRole("heading", { level: 3, name: "Projects" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });
});
