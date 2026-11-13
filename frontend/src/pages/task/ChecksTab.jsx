import React from "react";

import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { formatDayTime } from "../../ui/format";
import { branchWords, criterionWords, reviewWords, sizeWords, testsWords } from "./taskWords";

const COLUMNS = [
  { key: "check", header: "Check", className: "task-checks__check", render: (row) => row.check },
  { key: "result", header: "Result", className: "task-checks__result", render: (row) => <span className={`tone-${row.tone}`}>{row.result}</span> },
  { key: "detail", header: "Detail", className: "secondary", render: (row) => row.detail },
];

// A criterion is written as a list item in the task; the dash is the list's,
// not the criterion's.
const criterionText = (text) => String(text ?? "").replace(/^\s*[-*]\s+/, "");
// What the engine records when no judge looked. The Result column already
// says "Not judged"; repeating it under every criterion adds nothing.
const UNJUDGED_EVIDENCE = "Not checked by a judge model.";

function factRows(facts) {
  const tests = testsWords(facts.tests);
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
          {facts.tests.result_line ? <Mono quiet>{facts.tests.result_line}</Mono> : null}
          {facts.tests.status === "not_run" ? <span className="quiet">The engine has not run the tests on this branch.</span> : null}
        </span>
      ),
    },
    {
      key: "branch",
      check: "Branch",
      tone: branch.tone,
      result: branch.word,
      detail: ahead ? `${ahead} commit${ahead === 1 ? "" : "s"} on the branch` : "",
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
          {review.summary ? <span className="task-text">{review.summary}</span> : null}
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
          <span>{criterionText(item.criterion)}</span>
          {item.evidence && item.evidence !== UNJUDGED_EVIDENCE ? <span className="quiet">{item.evidence}</span> : null}
        </span>
      ),
    };
  });
  return [...reviews, ...criteria];
}

/**
 * Checks: what the engine measured (facts) and what an agent reported
 * (claims), in two tables that never mix (ADR-0018), then evidence files.
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
  const judged = data.claims.judged_by && data.claims.judged_by !== "none";
  return (
    <div className="task-checks">
      <section className="task-section" aria-labelledby="task-facts">
        <SectionHeading id="task-facts" title="Measured by the engine" note="Facts. The engine ran or read these itself." />
        <Table caption="Measured by the engine" columns={COLUMNS} rows={factRows(data.facts)} rowKey={(row) => row.key} />
      </section>
      <section className="task-section" aria-labelledby="task-claims">
        <SectionHeading
          id="task-claims"
          title="Reported by an agent"
          note={`Claims. Read them as an opinion on the facts above.${judged ? ` Criteria judged by ${data.claims.judged_by}.` : ""}`}
        />
        {claims.length ? (
          <Table caption="Reported by an agent" columns={COLUMNS} rows={claims} rowKey={(row) => row.key} />
        ) : (
          <p className="empty">No agent has reported on this task yet, and it has no acceptance criteria to judge.</p>
        )}
      </section>
      <section className="task-section" aria-labelledby="task-evidence">
        <SectionHeading id="task-evidence" title="Evidence files" />
        {data.evidence_files.length ? (
          <ul className="task-evidence">
            {data.evidence_files.map((file) => (
              <li key={file.path}>
                <Mono>{file.name}</Mono> <span className="quiet">{formatDayTime(file.captured_at)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty">None required by this workflow.</p>
        )}
      </section>
    </div>
  );
}
