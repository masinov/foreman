import React, { useEffect, useState } from "react";

import { getRunOutput, listTaskRuns } from "../../api/tasks";
import { usePagedList } from "../../api/usePagedList";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Caret } from "../../ui/Caret";
import { Disclosure } from "../../ui/Disclosure";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { formatDayTime, formatDuration, formatMoney, humanize, plural, shortSha } from "../../ui/format";
import { narrate } from "./runWords";
import { RunLine, withDays } from "./RunStory";
import { runBy, runResult, runSeconds } from "./taskWords";
import { useTaskPulse } from "./useTaskPulse";

// Design README: activity 25 at a time.
export const RUNS_PAGE = 25;

/** The agent's stream as the CLI wrote it, read only when someone opens it. */
function RawOutput({ run }) {
  const raw = useResource(["run-output-raw", run.id], (client, options) => getRunOutput(client, run.id, { ...options, raw: true }));
  if (raw.error) {
    return (
      <p className="notice notice--error" role="alert">
        {raw.error}
      </p>
    );
  }
  if (!raw.data) return null;
  return (
    <>
      {raw.data.transcript_truncated ? (
        <p className="notice" role="status">
          The raw output is longer than {raw.data.cap_chars.toLocaleString("en-US")} characters; its start is shown.
        </p>
      ) : null}
      <pre className="run-output__text run-output__prompt">{raw.data.transcript.map((entry) => entry.text).join("\n")}</pre>
    </>
  );
}

function RunOutput({ run, pulse = 0 }) {
  const output = useResource(["run-output", run.id], (client, options) => getRunOutput(client, run.id, options));
  const reload = output.reload;
  // `pulse` grows while this run is in progress and printing.
  useEffect(() => {
    if (pulse) reload();
  }, [pulse, reload]);
  const by = runBy(run);
  const data = output.data;
  const lines = data ? withDays(narrate(data.transcript), run.started_at) : [];
  return (
    <section className="task-section run-output" aria-labelledby="run-output">
      {/* The title is the step. Who ran it and when are details beside it. */}
      <SectionHeading
        id="run-output"
        title={humanize(run.step)}
        note={[by ? `by ${by}` : null, formatDayTime(run.started_at)].filter(Boolean).join(" · ")}
      />
      {output.error ? (
        <p className="notice notice--error" role="alert">
          {output.error}
        </p>
      ) : null}
      {data?.transcript_truncated ? (
        <p className="notice" role="status">
          This run recorded more than {data.cap_chars.toLocaleString("en-US")} characters; the earliest of its{" "}
          {data.total_entries} events are shown.
        </p>
      ) : null}
      {data && lines.length === 0 ? <p className="empty">This run recorded nothing to read.</p> : null}
      {lines.length ? (
        <ol className="run-story" aria-label="What happened">
          {lines.map((line, index) => (
            <RunLine key={index} line={line} />
          ))}
        </ol>
      ) : null}
      {data?.raw_entries ? (
        <Disclosure summary={`Show the raw output (${plural(data.raw_entries, "line")})`}>
          <RawOutput run={run} />
        </Disclosure>
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
  const pulse = useTaskPulse(task.id, task.status === "in_progress");
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
    {
      key: "commit",
      header: "Commit",
      className: "secondary",
      render: (run) => (run.commit_sha ? <Mono quiet>{shortSha(run.commit_sha)}</Mono> : null),
    },
    { key: "took", header: "Took", numeric: true, render: (run) => <Mono quiet>{formatDuration(runSeconds(run))}</Mono> },
    {
      key: "spend",
      header: "Spend",
      numeric: true,
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
          <Button variant="quiet" className="list-more expander" disabled={runs.loadingMore} onClick={() => runs.loadMore()}>
            <Caret />
            Earlier
          </Button>
        ) : null}
      </section>
      {selected ? <RunOutput key={selected.id} run={selected} pulse={selected.status === "running" ? pulse : 0} /> : null}
    </div>
  );
}
