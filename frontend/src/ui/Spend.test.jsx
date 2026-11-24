import { render, screen } from "@testing-library/react";

import { Spend, spendWords } from "./Spend";

describe("Spend", () => {
  it("writes an amount alone in the mono font", () => {
    render(<Spend amount={0.09} />);
    expect(screen.getByText("$0.09")).toHaveClass("mono");
  });

  it("writes the amount first and the tokens after it", () => {
    render(<Spend amount={0.09} tokens={3500} />);
    expect(screen.getByText("$0.09 · 3.5K tokens")).toHaveClass("mono");
  });

  it("writes a zero blank in a row and as $0.00 in details", () => {
    const { container } = render(<Spend amount={0} where="row" />);
    expect(container).toBeEmptyDOMElement();
    expect(spendWords(0, 0, "row")).toBe("");
    expect(spendWords(0, 0)).toBe("$0.00");
    expect(spendWords(undefined, 0, "details")).toBe("$0.00");
  });

  it("writes tokens without an amount when there is no cost", () => {
    expect(spendWords(0, 1200)).toBe("1.2K tokens");
    expect(spendWords(0, 1200, "row")).toBe("1.2K tokens");
  });
});
