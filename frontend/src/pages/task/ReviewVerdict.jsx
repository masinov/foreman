import React from "react";

import { LongText } from "../../ui/LongText";
import { StatusDot } from "../../ui/StatusDot";

/** The kind of record a reviewer's step returns (ADR-0042). */
export const REVIEW_VERDICT = "review_verdict";

/** What each severity means; S1 and S2 are the ones that send work back. */
export const SEVERITIES = {
  S1: "broken, unsafe or data-losing",
  S2: "an acceptance criterion not met",
  S3: "should be fixed, does not block",
  S4: "a nit",
};

const STATUSES = {
  verified: { tone: "passed", word: "Verified" },
  not_verified: { tone: "attention", word: "Not verified" },
  judgement: { tone: "idle", word: "Reviewer's judgement" },
};

const text = (value) => String(value ?? "").trim();
const texts = (value) => (Array.isArray(value) ? value.map(text).filter(Boolean) : []);

/** What a step's record says, when it is a reviewer's verdict; otherwise null. */
export function reviewVerdict(record) {
  if (!record || record.kind !== REVIEW_VERDICT || !record.fields) return null;
  const fields = record.fields;
  const criteria = Array.isArray(fields.criteria) ? fields.criteria : [];
  const findings = Array.isArray(fields.findings) ? fields.findings : [];
  return {
    criteria: criteria.map((entry) => ({
      criterion: text(entry.criterion),
      status: STATUSES[entry.status] ? entry.status : "not_verified",
      evidence: text(entry.evidence),
      // How it was checked (ADR-0041 section 2); a verdict from before has none.
      ran: texts(entry.ran),
      read: texts(entry.read),
      fromReport: entry.from_report === true,
    })),
    // Most serious first; the reviewer's own order within a severity.
    findings: findings
      .map((entry, index) => ({ severity: text(entry.severity), finding: text(entry.finding), index }))
      .sort((a, b) => a.severity.localeCompare(b.severity) || a.index - b.index),
  };
}

function Basis({ entry, confirmed }) {
  if (!entry.ran.length && !entry.read.length && !entry.fromReport) return null;
  return (
    <dl className="run-report__basis" aria-label="How it was checked">
      {entry.ran.length ? (
        <>
          <dt>Ran</dt>
          <dd>
            <ul className="run-report__list">
              {entry.ran.map((command, index) => (
                <li key={index}>
                  <code className="mono">{command}</code>{" "}
                  {confirmed.includes(command) ? (
                    <StatusDot tone="passed">Foreman saw it run</StatusDot>
                  ) : (
                    <StatusDot tone="idle">Not seen by Foreman</StatusDot>
                  )}
                </li>
              ))}
            </ul>
          </dd>
        </>
      ) : null}
      {entry.read.length ? (
        <>
          <dt>Read</dt>
          <dd>
            <ul className="run-report__list">
              {entry.read.map((path, index) => (
                <li key={index}>
                  <code className="mono">{path}</code>
                </li>
              ))}
            </ul>
          </dd>
        </>
      ) : null}
      {entry.fromReport ? (
        <>
          <dt>From</dt>
          <dd>The developer's report or the test step's output</dd>
        </>
      ) : null}
    </dl>
  );
}

/**
 * The reviewer's verdict, in the review step's details: each acceptance
 * criterion as verified, not verified or the reviewer's judgement, with what
 * it checked, and the findings with their severities. Only S1 and S2 sent
 * work back; S3 and S4 stay here when the review approved. Each criterion's
 * basis is shown: the commands it ran (marked when Foreman found them among
 * the commands the run made, `confirmed`), the files it read, and whether it
 * relied on the developer's report.
 */
export function ReviewVerdict({ record, confirmed = [] }) {
  const verdict = reviewVerdict(record);
  if (!verdict) return null;
  return (
    <section className="run-report" aria-label="Review verdict">
      <h3 className="run-report__title">Verdict</h3>
      <h4 className="run-report__heading">Acceptance criteria</h4>
      {verdict.criteria.length ? (
        <ol className="run-report__criteria" aria-label="Criteria checked">
          {verdict.criteria.map((entry, index) => {
            const status = STATUSES[entry.status];
            return (
              <li key={index} className="run-report__criterion">
                <p className="run-report__what">
                  {entry.criterion} <StatusDot tone={status.tone}>{status.word}</StatusDot>
                </p>
                {entry.evidence ? (
                  <LongText output className="run-report__how">
                    {entry.evidence}
                  </LongText>
                ) : null}
                <Basis entry={entry} confirmed={confirmed} />
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="run-report__what">The review listed no criteria.</p>
      )}
      <h4 className="run-report__heading">Findings</h4>
      {verdict.findings.length ? (
        <ul className="run-report__list" aria-label="Findings">
          {verdict.findings.map((entry) => (
            <li key={entry.index} className="run-report__finding">
              <span
                className={`run-report__severity run-report__severity--${entry.severity.toLowerCase()}`}
                title={SEVERITIES[entry.severity] ?? ""}
              >
                {entry.severity}
              </span>{" "}
              {entry.finding}
            </li>
          ))}
        </ul>
      ) : (
        <p className="run-report__what">No findings.</p>
      )}
    </section>
  );
}
