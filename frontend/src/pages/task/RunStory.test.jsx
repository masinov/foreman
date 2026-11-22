import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { lastLines, RunLine } from "./RunStory";

function heights(full, shown) {
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(full);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(shown);
}

const story = (line) => render(<ul>{<RunLine line={{ at: "2026-11-20T17:00:47Z", ...line }} />}</ul>);

describe("a line of a run's story", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows what an agent or a user wrote whole and formatted, with nothing to press", () => {
    heights(900, 54);
    const words = [
      "The log no longer holds the host.",
      "",
      "**Cause:** uvicorn prints the `address`.",
      "",
      "**Tests added in `tests/test_serve.py`:**",
      "",
      "- **Bind failure:** the port is taken.",
      "  - nested detail",
      "- **Normal run:** nothing leaks.",
      ...Array.from({ length: 20 }, (_, index) => `\nParagraph ${index + 1}.`),
    ].join("\n");
    const { container } = story({ body: words, prose: true });
    expect(screen.getByText("Paragraph 20.")).toBeInTheDocument();
    expect(container.querySelector(".run-line__words")).toBeInTheDocument();
    expect(screen.getByText("Cause:").tagName).toBe("STRONG");
    expect(screen.getByText("address").tagName).toBe("CODE");
    expect(screen.getByText("tests/test_serve.py").closest("strong")).toHaveTextContent("Tests added in tests/test_serve.py:");
    // A deeper item belongs to the item above it.
    expect(screen.getByText("nested detail").closest("ul").parentElement).toHaveTextContent("Bind failure:");
    expect(container).not.toHaveTextContent("**");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows the first lines of what it ran, with Show all", () => {
    heights(900, 54);
    story({ says: "Ran", mono: "cat > assay/evidence.py <<'EOF'\n\"\"\"Lineage.\"\"\"\nEOF" });
    const command = screen.getByText(/cat > assay/);
    expect(command.tagName).toBe("PRE");
    expect(command).toHaveClass("run-line__command", "long-text__text--folded");
    fireEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(command).not.toHaveClass("long-text__text--folded");
  });

  it("shows the last lines of what a program printed, where the result is, with Show all", () => {
    const printed = "warning: deprecated\n....\n------\nRan 186 tests in 175s\n\nOK\n";
    story({ body: printed, output: true });
    const shown = screen.getByText(/Ran 186 tests/);
    expect(shown.textContent).toBe("Ran 186 tests in 175s\n\nOK");
    expect(shown).not.toHaveTextContent("warning");
    fireEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(shown).toHaveTextContent("warning: deprecated");
    fireEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(shown).not.toHaveTextContent("warning");
  });

  it("has nothing to press for output of three lines or fewer", () => {
    story({ body: "Ran 9 tests\n\nOK" });
    expect(screen.queryByRole("button")).toBeNull();
    expect(lastLines("a\nb\nc\n\n")).toEqual({ text: "a\nb\nc", more: false });
  });
});
