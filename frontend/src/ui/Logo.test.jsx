import React from "react";
import { render } from "@testing-library/react";
import { Logo } from "./Logo";

describe("Logo", () => {
  it("is the name as type, with nothing drawn beside it", () => {
    const { container } = render(<Logo />);
    expect(container.querySelector(".logo")).toHaveTextContent("Foreman");
    expect(container.querySelector("svg")).toBeNull();
  });
});
