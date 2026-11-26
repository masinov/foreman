import React from "react";
import { render, screen, within } from "@testing-library/react";

import { ReviewVerdict, reviewVerdict } from "./ReviewVerdict";

const record = (fields = {}) => ({
  kind: "review_verdict",
  fields: {
    criteria: [
      { criterion: "The loader rejects a bad declaration", status: "verified", evidence: "foreman/definitions/records.py:112 raises" },
      { criterion: "The page reads well", status: "judgement", evidence: "Read the component; not opened." },
      { criterion: "The docs are updated", status: "not_verified", evidence: "ADR not found." },
    ],
    findings: [
      { severity: "S4", finding: "A stray blank line in records.py." },
      { severity: "S3", finding: "The helper has no docstring." },
      { severity: "S2", finding: "The docs criterion is not met." },
    ],
    ...fields,
  },
});

describe("the review's verdict", () => {
  it("shows each criterion as verified, not verified or the reviewer's judgement, with what it checked", () => {
    render(<ReviewVerdict record={record()} />);
    const region = screen.getByRole("region", { name: "Review verdict" });
    const [first, second, third] = within(within(region).getByRole("list", { name: "Criteria checked" })).getAllByRole("listitem");
    expect(first).toHaveTextContent("The loader rejects a bad declaration");
    expect(first).toHaveTextContent("Verified");
    expect(first).not.toHaveTextContent("Not verified");
    expect(first).toHaveTextContent("records.py:112 raises");
    expect(second).toHaveTextContent("Reviewer's judgement");
    expect(third).toHaveTextContent("Not verified");
    expect(third).toHaveTextContent("ADR not found.");
  });

  it("shows how each criterion was checked, and marks the commands Foreman saw run", () => {
    const basis = record({
      criteria: [
        {
          criterion: "Tests cover it",
          status: "verified",
          evidence: "Passed.",
          ran: ["pytest tests/test_x.py", "make lint"],
          read: ["tests/test_x.py"],
          from_report: false,
        },
        { criterion: "The change file", status: "verified", evidence: "As reported.", ran: [], read: [], from_report: true },
        { criterion: "Old verdict", status: "judgement", evidence: "No basis fields." },
      ],
    });
    render(<ReviewVerdict record={basis} confirmed={["pytest tests/test_x.py"]} />);
    const [first, second, third] = screen.getByRole("list", { name: "Criteria checked" }).children;
    const ran = within(within(first).getByLabelText("How it was checked")).getAllByRole("listitem").slice(0, 2);
    expect(ran[0]).toHaveTextContent("pytest tests/test_x.py");
    expect(ran[0].querySelector("code")).toHaveTextContent("pytest tests/test_x.py");
    expect(ran[0]).toHaveTextContent("Foreman saw it run");
    expect(ran[1]).toHaveTextContent("make lint");
    expect(ran[1]).toHaveTextContent("Not seen by Foreman");
    expect(first).toHaveTextContent(/Read\s*tests\/test_x\.py$/);
    expect(second).toHaveTextContent("The developer's report or the test step's output");
    expect(within(second).queryByText("Ran")).toBeNull();
    expect(within(third).queryByLabelText("How it was checked")).toBeNull();
  });

  it("lists the findings with their severities, the most serious first", () => {
    render(<ReviewVerdict record={record()} />);
    const items = within(screen.getByRole("list", { name: "Findings" })).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "S2 The docs criterion is not met.",
      "S3 The helper has no docstring.",
      "S4 A stray blank line in records.py.",
    ]);
  });

  it("keeps the S3 and S4 findings of an approving review in view", () => {
    render(<ReviewVerdict record={record({ criteria: [], findings: [{ severity: "S3", finding: "Rename it." }, { severity: "S4", finding: "A nit." }] })} />);
    const list = screen.getByRole("list", { name: "Findings" });
    expect(list).toHaveTextContent("S3 Rename it.");
    expect(list).toHaveTextContent("S4 A nit.");
    expect(screen.getByText("The review listed no criteria.")).toBeInTheDocument();
  });

  it("says when there are no findings", () => {
    render(<ReviewVerdict record={record({ findings: [] })} />);
    expect(screen.getByText("No findings.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Findings" })).toBeNull();
  });

  it("shows nothing for a step with no record, or another kind of record", () => {
    const { container, rerender } = render(<ReviewVerdict record={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ReviewVerdict record={{ kind: "developer_report", fields: {} }} />);
    expect(container).toBeEmptyDOMElement();
    expect(reviewVerdict(undefined)).toBeNull();
  });
});
