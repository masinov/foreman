import React from "react";
import { render, screen, within } from "@testing-library/react";

import { DeveloperReport, developerReport } from "./DeveloperReport";

const record = (fields = {}) => ({
  kind: "developer_report",
  fields: {
    summary: "Added the loader.",
    criteria: [
      { criterion: "The loader rejects a bad declaration", verification: "pytest tests/x.py: 3 passed", verified: true },
      { criterion: "The page shows the report", verification: "Not opened in a browser.", verified: false },
    ],
    not_verified: ["The page was not opened: no display here."],
    beyond_task: [],
    docs_touched: ["docs/adr/ADR-0042.md"],
    follow_ups: [],
    ...fields,
  },
});

describe("the developer's report", () => {
  it("shows what changed, each criterion with how it was verified, and the lists that have something", () => {
    render(<DeveloperReport record={record()} />);
    const report = screen.getByRole("region", { name: "Developer's report" });
    expect(report).toHaveTextContent("Added the loader.");
    const criteria = within(report).getByRole("list", { name: "Acceptance criteria" });
    const [first, second] = within(criteria).getAllByRole("listitem");
    expect(first).toHaveTextContent("The loader rejects a bad declaration");
    expect(first).toHaveTextContent("Verified");
    expect(first).not.toHaveTextContent("Not verified");
    expect(first).toHaveTextContent("pytest tests/x.py: 3 passed");
    expect(second).toHaveTextContent("The page shows the report");
    expect(second).toHaveTextContent("Not verified");
    expect(second).toHaveTextContent("Not opened in a browser.");
    expect(within(report).getByRole("list", { name: "Not verified, and why" })).toHaveTextContent("no display here");
    expect(within(report).getByRole("list", { name: "Docs touched" })).toHaveTextContent("docs/adr/ADR-0042.md");
  });

  it("leaves out a list with nothing in it", () => {
    render(<DeveloperReport record={record()} />);
    expect(screen.queryByRole("list", { name: "Changed beyond the task" })).toBeNull();
    expect(screen.queryByRole("list", { name: "Follow-ups filed" })).toBeNull();
  });

  it("shows nothing for a step that returned no record, or another kind of record", () => {
    const { container, rerender } = render(<DeveloperReport record={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<DeveloperReport record={{ kind: "plan", fields: {} }} />);
    expect(container).toBeEmptyDOMElement();
    expect(developerReport(undefined)).toBeNull();
  });
});
