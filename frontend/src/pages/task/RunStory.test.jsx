import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { RunLine } from "./RunStory";

function heights(full, shown) {
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(full);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(shown);
}

const story = (line) => render(<ul>{<RunLine line={{ at: "2026-11-20T17:00:47Z", ...line }} />}</ul>);

describe("a line of a run's story", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows what an agent or a user wrote whole, however long, with nothing to press", () => {
    heights(900, 54);
    const words = Array.from({ length: 30 }, (_, index) => `Line ${index + 1} of the agent's summary.`).join("\n");
    story({ body: words, prose: true });
    expect(screen.getByText(/Line 30 of the agent's summary/)).toHaveClass("run-line__words");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows the first lines of a command the agent ran, with Show all", () => {
    heights(900, 54);
    story({ says: "Ran", mono: "cat > assay/evidence.py <<'EOF'\n\"\"\"Lineage.\"\"\"\nEOF" });
    const head = screen.getByText("Ran").closest("p");
    expect(head).toHaveClass("run-line__head", "long-text__text--brief", "long-text__text--folded");
    fireEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(head).not.toHaveClass("long-text__text--folded");
  });

  it("shows the first lines of what a program printed, with Show all, whatever printed it", () => {
    heights(900, 54);
    for (const line of [
      { body: "assay:\nadmin.py\napi.py\ncard.py" },
      { says: "Merge conflict with main", body: "CONFLICT (content): Merge conflict in a.py", tone: "failed" },
      { body: "....F\n1 failed", output: true },
    ]) {
      const view = story(line);
      const shown = view.container.querySelector("pre");
      expect(shown).toHaveClass("long-text__text--output", "long-text__text--folded");
      fireEvent.click(screen.getByRole("button", { name: "Show all" }));
      expect(shown).not.toHaveClass("long-text__text--folded");
      view.unmount();
    }
  });
});
