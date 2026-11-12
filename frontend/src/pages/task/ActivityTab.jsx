import React, { useState } from "react";

import { getRunOutput, listTaskRuns } from "../../api/tasks";
import { usePagedList } from "../../api/usePagedList";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Disclosure } from "../../ui/Disclosure";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { formatDayTime, formatDuration, formatMoney, humanize, plural } from "../../ui/format";
import { runBy, runResult, runSeconds } from "./taskWords";

// Design README: activity 25 at a time.
export const RUNS_PAGE = 25;

const QUIET_KINDS = new Set(["agent.raw_output", "engine.test_output"]);

function RunOutput({ run }) {
  const output = useResource(["run-output", run.id], (client, options) => getRunOutput(client, run.id, options));
  const by = runBy(run);
  const data = output.data;
  return (
    <section className="task-section run-output" aria-labelledby="run-output">
      <SectionHeading id="run-output" title={`${humanize(run.step)}${by ? `, by ${by}` : ""}`} note={formatDayTime(run.started_at)} />
      {output.error ? (
        <p className="notice notice--error" role="alert">
          {output.error}
        </p>
      ) : null}
      {data?.transcript_truncated ? (
        <p className="notice" role="status">
          This output is longer than {data.cap_chars.toLocaleString("en-US")} characters; the earliest of its{" "}
          {data.total_entries} entries are shown.
        </p>
      ) : null}
      {data && data.transcript.length === 0 ? <p className="empty">This run recorded no output.</p> : null}
      {data && data.transcript.length ? (
        <ol className="run-output__entries" aria-label="Output">
          {data.transcript.map((entry, index) => (
            <li key={index} className="run-output__entry">
              {QUIET_KINDS.has(entry.kind) ? null : <span className="run-output__kind">{humanize(entry.kind.replace(".", " "))}</span>}
              <pre className="run-output__text">{entry.text}</pre>
            </li>
          ))}
        </ol>
      ) : null}
      {data ? (
        data.prompt ? (
          <Disclosure summary="Show the prompt this run was given">
            {data.prompt_truncated ? (
              <p className="notice" role="status">
                The prompt is longer than {data.cap_chars.toLocaleString("en-US")} characters; its start is shown.
              </p>
            ) : null}
            <pre className="run-output__text run-output__prompt">{data.prompt}</pre>
          </Disclosure>
        ) : (
          <p className="quiet">No prompt was recorded for this run.</p>
        )
      ) : null}
    </section>
  );
}

/**
 * Activity: every run of the task, newest first, 25 at a time with Earlier.
 * Selecting a run shows its output and the prompt it was given; the newest
 * is selected until another is picked.
 */
export function ActivityTab({ task, revision }) {
  const runs = usePagedList(
    ["task-runs", task.id, revision],
    (client, options) => listTaskRuns(client, task.id, options),
    { pageSize: RUNS_PAGE },
  );
  const [picked, setPicked] = useState(null);
  const items = runs.items ?? [];
  const selected = items.find((run) => run.id === picked) ?? items[0] ?? null;

  const columns = [
    {
      key: "when",
      header: "When",
      className: "task-runs__when",
      render: (run) => (
        <button
          type="button"
          className="file-pick"
          aria-pressed={run === selected}
          aria-label={`${humanize(run.step)}, ${formatDayTime(run.started_at) || "not started"}`}
          onClick={() => setPicked(run.id)}
        >
          <Mono quiet>{formatDayTime(run.started_at) || "not started"}</Mono>
        </button>
      ),
    },
    { key: "step", header: "Step", render: (run) => humanize(run.step) },
    { key: "by", header: "By", className: "secondary", render: (run) => runBy(run) },
    {
      key: "result",
      header: "Result",
      render: (run) => {
        const result = runResult(run);
        return <span className={`tone-${result.tone}`}>{result.word}</span>;
      },
    },
    { key: "took", header: "Took", className: "task-runs__number", render: (run) => <Mono quiet>{formatDuration(runSeconds(run))}</Mono> },
    {
      key: "spend",
      header: "Spend",
      className: "task-runs__number",
      render: (run) => (run.cost_usd ? <Mono quiet>{formatMoney(run.cost_usd)}</Mono> : null),
    },
  ];

  const totals = task.totals ?? {};
  return (
    <div className="task-activity">
      <section className="task-section" aria-labelledby="task-runs">
        <SectionHeading
          id="task-runs"
          title="Everything that happened"
          note={`${plural(totals.run_count ?? runs.total ?? 0, "run")}, ${formatMoney(totals.total_cost_usd)}. Newest first.`}
        />
        {runs.error ? (
          <p className="notice notice--error" role="alert">
            {runs.error}
          </p>
        ) : null}
        {runs.items && items.length === 0 ? <p className="empty">Nothing has run on this task yet.</p> : null}
        {items.length ? (
          <Table caption="Runs" columns={columns} rows={items} selected={(run) => run === selected} />
        ) : null}
        {runs.hasMore ? (
          <Button variant="quiet" className="list-more" disabled={runs.loadingMore} onClick={() => runs.loadMore()}>
            Earlier
          </Button>
        ) : null}
      </section>
      {selected ? <RunOutput key={selected.id} run={selected} /> : null}
    </div>
  );
}
