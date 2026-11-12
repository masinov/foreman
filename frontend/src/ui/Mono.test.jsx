import { render, screen } from "@testing-library/react";

import { Mono } from "./Mono";

describe("Mono", () => {
  it("renders monospaced text, quiet on request", () => {
    render(
      <>
        <Mono>FOR-14</Mono>
        <Mono quiet>b232eb1</Mono>
      </>,
    );
    expect(screen.getByText("FOR-14")).toHaveClass("mono");
    expect(screen.getByText("FOR-14")).not.toHaveClass("mono--quiet");
    expect(screen.getByText("b232eb1")).toHaveClass("mono", "mono--quiet");
  });
});
