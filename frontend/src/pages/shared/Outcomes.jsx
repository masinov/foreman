import React, { useEffect, useRef } from "react";

import { getOutcomes } from "../../api/outcomes";
import { useResource } from "../../api/useResource";
import { Disclosure } from "../../ui/Disclosure";
import { Mono } from "../../ui/Mono";
import { Table } from "../../ui/Table";
import { formatDuration, formatMoney, humanize, plural } from "../../ui/format";

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
  return formatDuration(value * 60);
}

/** "7 of 8", and what it is leaving merge conflicts aside when that differs. */
export function firstTimeText(tasks) {
  const merged = tasks?.merged ?? 0;
  const first = tasks?.passed_first_time ?? 0;
  const aside = tasks?.passed_first_time_conflicts_aside ?? first;
  const base = `${first} of ${merged}`;
  return aside !== first ? `${base} (${aside} leaving merge conflicts aside)` : base;
}

/** "None", or "3: review 2, tests 1", largest cause first. */
export function sentBackText(sendBacks) {
  const counts = CAUSES.map(([key, word]) => [word, sendBacks?.[key] ?? 0]).filter(([, count]) => count > 0);
  const total = counts.reduce((sum, [, count]) => sum + count, 0);
  if (!total) return "None";
  counts.sort((a, b) => b[1] - a[1]);
  return `${total}: ${counts.map(([word, count]) => `${word} ${count}`).join(", ")}`;
}

/** "Asked once (waited 4 min), stepped in twice", in the reader's terms. */
export function youText(people) {
  const asked = people?.decisions_asked ?? 0;
  const waiting = people?.decisions_waiting ?? 0;
  const stepped = people?.interventions ?? 0;
  const wait = people?.median_wait_seconds;
  const askedText = asked
    ? `asked ${times(asked)}${wait !== null && wait !== undefined ? ` (median wait ${formatDuration(wait)})` : ""}`
    : "never asked";
  const waitingText = waiting ? `, ${waiting} waiting` : "";
  const steppedText = stepped ? `stepped in ${times(stepped)}` : "never stepped in";
  const sentence = `${askedText}${waitingText}, ${steppedText}`;
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
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
    { key: "time", header: "Time", numeric: true, render: (row) => <Mono quiet>{minutesText((row.duration_seconds ?? 0) / 60)}</Mono> },
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
 * the per-role and per-model breakdown behind a click. `lead` names the scope
 * where the page does not ("All sprints" on the project page). `revision`
 * grows when the page changed, so the numbers are read again.
 */
export function Outcomes({ projectId, sprintId = null, lead = null, revision = 0 }) {
  const outcomes = useResource(["outcomes", projectId, sprintId ?? ""], (client, options) =>
    getOutcomes(client, projectId, { sprintId }, options),
  );
  const reload = outcomes.reload;
  const mounted = useRef(false);
  useEffect(() => {
    if (mounted.current) reload();
    mounted.current = true;
  }, [revision, reload]);

  // The numbers are an aside: a page whose numbers cannot be read still works.
  if (outcomes.error || !outcomes.data) return null;
  const data = outcomes.data;
  const tasks = data.tasks ?? {};
  const started = tasks.started ?? 0;
  const merged = tasks.merged ?? 0;
  if (!started && !merged) return null;

  const items = [
    { term: "First time", value: firstTimeText(tasks), title: "Merged tasks that were never sent back" },
    { term: "Sent back", value: sentBackText(data.send_backs) },
    { term: "You", value: youText(data.people) },
  ];
  if (tasks.not_finished) items.push({ term: "Not finished", value: plural(tasks.not_finished, "task") });
  if (merged) {
    items.push({ term: "Per merged task", value: <Mono>{formatMoney(data.cost?.per_merged_task_usd)}</Mono> });
    if (data.median_minutes_to_merge !== null && data.median_minutes_to_merge !== undefined) {
      items.push({
        term: "To merge",
        value: `${minutesText(data.median_minutes_to_merge)} median`,
        title: "From a task's first step to its merge",
      });
    }
  }
  const rows = data.by_role_and_model ?? [];

  return (
    <section className="outcomes" aria-label={lead ? `Outcomes, ${lead.toLowerCase()}` : "Outcomes"}>
      <div className="outcomes__line">
        {lead ? <span className="outcomes__lead">{lead}</span> : null}
        <dl className="summary">
          {items.map((item) => (
            <div className="summary__item" key={item.term} title={item.title}>
              <dt>{item.term}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      </div>
      {rows.length ? (
        <Disclosure summary="By role and model" className="outcomes__more">
          <ByRoleAndModel rows={rows} />
        </Disclosure>
      ) : null}
    </section>
  );
}
