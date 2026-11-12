import { fireEvent, render, screen } from "@testing-library/react";

import { Button } from "./Button";

describe("Button", () => {
  it.each([
    ["default", "button--default"],
    ["quiet", "button--quiet"],
    ["gold-outline", "button--gold-outline"],
    ["gold", "button--gold"],
  ])("renders the %s variant", (variant, className) => {
    render(<Button variant={variant}>Go</Button>);
    expect(screen.getByRole("button", { name: "Go" })).toHaveClass("button", className);
  });

  it("is a non-submitting button that calls onClick", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);
    const button = screen.getByRole("button", { name: "Go" });
    expect(button).toHaveAttribute("type", "button");
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("has the in-row size and falls back to default for an unknown variant", () => {
    render(
      <Button variant="loud" inRow>
        Go
      </Button>,
    );
    expect(screen.getByRole("button")).toHaveClass("button--default", "button--in-row");
  });
});
