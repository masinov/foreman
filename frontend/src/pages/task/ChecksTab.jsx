import React from "react";

import { Markdown } from "../../ui/Markdown";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { formatDayTime } from "../../ui/format";
import { ownWords } from "./runWords";
import { branchWords, criterionWords, reviewWords, sizeWords, testsWords } from "./taskWords";

const COLUMNS = [
  { key: "check", header: "Check", className: "task-checks__check", render: (row) => row.check },
  { key: "result", header: "Result", className: "task-checks__result", render: (row) => <span className={`tone-${row.tone}`}>{row.result}</span> },
  { key: "detail", header: "Detail", className: "secondary", render: (row) => row.detail },
];

// A criterion is written as a list item in the task; the dash is the list's,
// not the criterion's.
const criterionText = (text) => String(text ?? "").replace(/^\s*[-*]\s+/, "");
// What evidence recorded before the criteria judge was removed says for a
// criterion nobody checked. The Result column already says so, and for a
// criterion the approving review covers the Review row names the commit.
const UNJUDGED_EVIDENCE = "Not checked by a judge model.";

function factRows(facts) {
  const tests = testsWords(facts.tests);
  const failedTests = facts.tests.counts?.failed_tests ?? [];
  const more = (facts.tests.counts?.failed ?? 0) - failedTests.length;
  const branch = branchWords(facts.branch);
  const ahead = facts.branch.ahead;
  return [
    {
      key: "tests",
      check: "Tests",
      tone: tests.tone,
      result: tests.word,
      detail: (
        <span className="cell-stack">
          {tests.detail ? <span>{tests.detail}</span> : null}
          {/* The tests that failed, by name, when the report named them; the output is in Activity. */}
          {failedTests.length ? (
            <ul className="task-checks__failed" aria-label="Failed tests">
              {failedTests.map((test, index) => (
                <li key={index}>
                  <Mono>{test.name}</Mono> {test.suite ? <span className="quiet">{test.suite}</span> : null}
                </li>
              ))}
              {more > 0 ? <li className="quiet">and {more} more</li> : null}
            </ul>
          ) : null}
          {facts.tests.status === "not_run" ? <span className="quiet">Foreman has not run the tests on this branch.</span> : null}
        </span>
      ),
    },
    {
      key: "branch",
      check: "Branch",
      tone: branch.tone,
      result: branch.word,
      detail: branch.sha ? <Mono>{branch.sha}</Mono> : ahead ? `${ahead} commit${ahead === 1 ? "" : "s"} on the branch` : "",
    },
    { key: "size", check: "Size of change", tone: "idle", result: sizeWords(facts.size), detail: "" },
  ];
}

function claimRows(claims) {
  const reviews = claims.reviews.map((review, index) => {
    const words = reviewWords(review);
    return {
      key: `review-${index}`,
      check: review.kind === "security" ? "Security review" : "Review",
      tone: words.tone,
      result: words.word,
      detail: (
        <span className="cell-stack">
          {words.detail ? <span>{words.detail}</span> : null}
          {ownWords(review.summary) ? <Markdown text={ownWords(review.summary)} className="task-checks__summary" /> : null}
        </span>
      ),
    };
  });
  const criteria = claims.criteria.map((item, index) => {
    const words = criterionWords(item.status);
    return {
      key: `criterion-${index}`,
      check: `Criterion ${index + 1}`,
      tone: words.tone,
      result: words.word,
      detail: (
        <span className="cell-stack">
          <Markdown text={criterionText(item.criterion)} />
          {item.evidence && item.evidence !== UNJUDGED_EVIDENCE && item.status !== "covered" ? (
            <span className="quiet">{item.evidence}</span>
          ) : null}
        </span>
      ),
    };
  });
  return [...reviews, ...criteria];
}

/**
 * Checks: what Foreman measured (facts) and what an agent reported
 * (claims), in two tables that never mix (ADR-0018), then evidence files
 * where there are some.
 */
export function ChecksTab({ checks }) {
  const data = checks.data;
  if (!data) {
    return checks.error ? (
      <p className="notice notice--error" role="alert">
        {checks.error}
      </p>
    ) : null;
  }
  const claims = claimRows(data.claims);
  return (
    <div className="task-checks">
      <section className="task-section" aria-labelledby="task-facts">
        <SectionHeading id="task-facts" title="Measured by Foreman" />
        <Table caption="Measured by Foreman" columns={COLUMNS} rows={factRows(data.facts)} rowKey={(row) => row.key} />
      </section>
      <section className="task-section" aria-labelledby="task-claims">
        <SectionHeading id="task-claims" title="Reported by an agent" />
        {claims.length ? (
          <Table caption="Reported by an agent" columns={COLUMNS} rows={claims} rowKey={(row) => row.key} />
        ) : (
          <p className="empty">No agent has reported on this task yet, and it has no acceptance criteria to check.</p>
        )}
      </section>
      {/* Evidence files are shown where there are some; none says nothing. */}
      {data.evidence_files.length ? (
        <section className="task-section" aria-labelledby="task-evidence">
          <SectionHeading id="task-evidence" title="Evidence files" />
          <ul className="task-evidence">
            {data.evidence_files.map((file) => (
              <li key={file.path}>
                <Mono>{file.name}</Mono> <span className="quiet">{formatDayTime(file.captured_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
