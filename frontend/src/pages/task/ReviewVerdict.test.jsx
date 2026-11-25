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
