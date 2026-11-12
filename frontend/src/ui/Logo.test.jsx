import React from "react";
import { render } from "@testing-library/react";
import { Logo } from "./Logo";

describe("Logo", () => {
  it("draws the F with its square beside the rest of the word", () => {
    const { container } = render(<Logo />);
    expect(container.querySelector(".logo__letter")).not.toBeNull();
    expect(container.querySelector(".logo__task")).not.toBeNull();
    expect(container.querySelector(".logo__rest")).toHaveTextContent("oreman");
    expect(container.querySelector(".logo")).not.toHaveClass("logo--running");
  });

  it("marks itself running so the square can breathe", () => {
    const { container } = render(<Logo running />);
    expect(container.querySelector(".logo")).toHaveClass("logo--running");
  });
});
