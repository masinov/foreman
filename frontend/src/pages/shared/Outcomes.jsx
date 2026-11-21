import React, { useId, useState } from "react";

import { getOutcomes } from "../../api/outcomes";
import { useResource } from "../../api/useResource";
import { Caret } from "../../ui/Caret";
import { Mono } from "../../ui/Mono";
import { Table } from "../../ui/Table";
import { formatDuration, formatMoney, humanize } from "../../ui/format";

import "../../styles/outcomes.css";

// What sent a task back, in the words of the page. "person" is whoever
// reads it, so it is "you".
const CAUSES = [
  ["review", "review"],
  ["tests", "tests"],
  ["person", "you"],
  ["merge_conflict", "merge conflict"],
  ["other", "other"],
];

function times(count) {
  return count === 1 ? "once" : `${count} times`;
}

/** "45 s", "6.9 min", "14 min", "2 h 5 min". */
export function minutesText(minutes) {
  const value = Math.max(0, Number(minutes) || 0);
  if (value < 1) return formatDuration(value * 60);
  if (value < 10) return `${value.toFixed(1).replace(/\.0$/, "")} min`;
  if (value < 60) return `${Math.round(value)} min`;
  return formatDuration(value * 60);
}

/**
 * The line's parts, each `{ text, title }`: short enough for one line on a
 * desktop; what does not fit is on hover (`title`).
 */
export function outcomeParts(data) {
  const tasks = data?.tasks ?? {};
  const merged = tasks.merged ?? 0;
  const first = tasks.passed_first_time ?? 0;
  const aside = tasks.passed_first_time_conflicts_aside ?? first;
  const parts = [
    {
      text: `${first} of ${merged} first time`,
      title: `Merged tasks never sent back${aside !== first ? `; ${aside} leaving merge conflicts aside` : ""}`,
    },
  ];
  const causes = CAUSES.map(([key, word]) => [word, data?.send_backs?.[key] ?? 0]).filter(([, count]) => count > 0);
  causes.sort((a, b) => b[1] - a[1]);
  const sent = causes.reduce((sum, [, count]) => sum + count, 0);
  parts.push({
    text: sent ? `${sent} sent back` : "none sent back",
    title: sent ? `Sent back by ${causes.map(([word, count]) => `${word} ${count}`).join(", ")}` : "",
  });
  const people = data?.people ?? {};
  const asked = people.decisions_asked ?? 0;
  const stepped = people.interventions ?? 0;
  const wait = people.median_wait_seconds;
  parts.push({
    text: `${asked ? `asked you ${times(asked)}` : "never asked you"}, ${stepped ? `you stepped in ${times(stepped)}` : "you never stepped in"}`,
    title: [
      wait !== null && wait !== undefined ? `Median wait for your decision: ${formatDuration(wait)}` : "",
      people.decisions_waiting ? `${people.decisions_waiting} waiting now` : "",
    ]
      .filter(Boolean)
      .join("; "),
  });
  if (tasks.not_finished) parts.push({ text: `${tasks.not_finished} not finished`, title: "" });
  if (merged) {
    parts.push({ text: `${formatMoney(data.cost?.per_merged_task_usd)} per merged task`, title: "" });
    if (data.median_minutes_to_merge !== null && data.median_minutes_to_merge !== undefined) {
      parts.push({ text: `${minutesText(data.median_minutes_to_merge)} to merge`, title: "Median, from a task's first step to its merge" });
    }
  }
  return parts;
}

/** What one role and model did, in a sentence that fits its kind of work. */
function roleResult(row) {
  if (row.tasks_built_merged) {
    return `built ${row.tasks_built_merged} merged, ${row.tasks_built_passed_first_time} first time`;
  }
  if (row.send_backs_caused) return `sent back ${row.send_backs_caused}`;
  return "";
}

function ByRoleAndModel({ rows }) {
  const columns = [
    { key: "role", header: "Role", render: (row) => humanize(row.role) },
    { key: "model", header: "Model", className: "secondary", render: (row) => <Mono quiet>{row.model || "not recorded"}</Mono> },
    { key: "runs", header: "Runs", numeric: true, render: (row) => <Mono quiet>{row.runs}</Mono> },
    {
      key: "failed",
      header: "Failed",
      numeric: true,
      render: (row) => <Mono quiet>{row.failed_runs || ""}</Mono>,
    },
    { key: "result", header: "Result", render: roleResult },
    { key: "time", header: "Time", numeric: true, render: (row) => <Mono quiet>{formatDuration(row.duration_seconds)}</Mono> },
    { key: "spend", header: "Spend", numeric: true, render: (row) => <Mono quiet>{formatMoney(row.cost_usd)}</Mono> },
  ];
  return (
    <Table
      caption="By role and model"
      columns={columns}
      rows={rows}
      rowKey={(row) => `${row.role}:${row.model ?? ""}`}
      className="outcomes__roles"
    />
  );
}

/**
 * One line of outcome numbers (ADR-0034) for a project or one sprint, with
 * the per-role and per-model table behind "By role and model" at its end.
 * `lead` names the scope where the page does not ("All sprints" on the
 * project page). The numbers read again whenever the project changes.
 */
export function Outcomes({ projectId, sprintId = null, lead = null }) {
  const outcomes = useResource(["outcomes", projectId, sprintId ?? ""], (client, options) =>
    getOutcomes(client, projectId, { sprintId }, options),
  );
  const [open, setOpen] = useState(false);
  const tableId = useId();

  // The numbers are an aside: a page whose numbers cannot be read still works.
  if (outcomes.error || !outcomes.data) return null;
  const data = outcomes.data;
  const tasks = data.tasks ?? {};
  if (!tasks.started && !tasks.merged) return null;
  const rows = data.by_role_and_model ?? [];

  return (
    <section className="outcomes" aria-label={lead ? `Outcomes, ${lead.toLowerCase()}` : "Outcomes"}>
      <p className="outcomes__line">
        {lead ? <span className="outcomes__lead">{lead}</span> : null}
        {outcomeParts(data).map((part, index) => (
          <React.Fragment key={part.text}>
            {index > 0 ? <span className="outcomes__dot"> · </span> : null}
            <span className="outcomes__part" title={part.title || undefined}>
              {part.text}
            </span>
          </React.Fragment>
        ))}
        {rows.length ? (
          <button
            type="button"
            className="outcomes__toggle expander"
            aria-expanded={open}
            aria-controls={tableId}
            onClick={() => setOpen((value) => !value)}
          >
            <Caret direction={open ? "down" : "right"} />
            By role and model
          </button>
        ) : null}
      </p>
      <div id={tableId} hidden={!open}>
        {open ? <ByRoleAndModel rows={rows} /> : null}
      </div>
    </section>
  );
}
