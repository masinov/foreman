import React from "react";

import { LongText } from "../../ui/LongText";
import { Markdown } from "../../ui/Markdown";
import { StatusDot } from "../../ui/StatusDot";

/** The kind of record the developer's step returns (ADR-0042). */
export const DEVELOPER_REPORT = "developer_report";

/** The lists of the report, in the order it shows them; one that is empty is left out. */
const LISTS = [
  ["not_verified", "Not verified, and why"],
  ["beyond_task", "Changed beyond the task"],
  ["docs_touched", "Docs touched"],
  ["follow_ups", "Follow-ups filed"],
];

/** What a step's record says, when it is a developer's report; otherwise null. */
export function developerReport(record) {
  if (!record || record.kind !== DEVELOPER_REPORT || !record.fields) return null;
  const fields = record.fields;
  const criteria = Array.isArray(fields.criteria) ? fields.criteria : [];
  return {
    summary: String(fields.summary ?? "").trim(),
    criteria: criteria.map((entry) => ({
      criterion: String(entry.criterion ?? "").trim(),
      how: String(entry.verification ?? "").trim(),
      verified: entry.verified === true,
    })),
    lists: LISTS.map(([key, title]) => ({
      key,
      title,
      items: (Array.isArray(fields[key]) ? fields[key] : []).map((item) => String(item).trim()).filter(Boolean),
    })).filter((list) => list.items.length > 0),
  };
}

/**
 * The developer's report, in the develop step's details: what changed and
 * why, each acceptance criterion with how it was verified, and what the
 * developer says was not verified, changed beyond the task, documented or
 * filed. It is the developer's claim; the review judges it.
 */
export function DeveloperReport({ record }) {
  const report = developerReport(record);
  if (!report) return null;
  return (
    <section className="run-report" aria-label="Developer's report">
      <h3 className="run-report__title">Report</h3>
      {report.summary ? <Markdown text={report.summary} className="run-report__words" /> : null}
      {report.criteria.length ? (
        <>
          <h4 className="run-report__heading">Acceptance criteria</h4>
          <ol className="run-report__criteria" aria-label="Acceptance criteria">
            {report.criteria.map((entry, index) => (
              <li key={index} className="run-report__criterion">
                <p className="run-report__what">
                  {entry.criterion} <StatusDot tone={entry.verified ? "passed" : "attention"}>{entry.verified ? "Verified" : "Not verified"}</StatusDot>
                </p>
                {entry.how ? (
                  <LongText output className="run-report__how">
                    {entry.how}
                  </LongText>
                ) : null}
              </li>
            ))}
          </ol>
        </>
      ) : null}
      {report.lists.map((list) => (
        <React.Fragment key={list.key}>
          <h4 className="run-report__heading">{list.title}</h4>
          <ul className="run-report__list" aria-label={list.title}>
            {list.items.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </React.Fragment>
      ))}
    </section>
  );
}
