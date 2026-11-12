import { render, screen } from "@testing-library/react";

import { Surface } from "./Surface";

describe("Surface", () => {
  it("is the tinted act-here box, as any element", () => {
    render(
      <Surface as="section" aria-label="Decide" className="extra">
        content
      </Surface>,
    );
    const region = screen.getByRole("region", { name: "Decide" });
    expect(region.tagName).toBe("SECTION");
    expect(region).toHaveClass("surface", "extra");
    expect(region).toHaveTextContent("content");
  });
});
