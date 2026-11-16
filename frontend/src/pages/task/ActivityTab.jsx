import React, { useState } from "react";

import { getRunOutput, listTaskRuns } from "../../api/tasks";
import { usePagedList } from "../../api/usePagedList";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Disclosure } from "../../ui/Disclosure";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { LongText } from "../../ui/LongText";
import { formatClock, formatDay, formatDayTime, formatDuration, formatMoney, humanize, plural, shortSha } from "../../ui/format";
import { narrate } from "./runWords";
import { runBy, runResult, runSeconds } from "./taskWords";
import { agentAtWork, TellAgent, ToldTheAgent } from "./TellAgent";

// Design README: activity 25 at a time.
export const RUNS_PAGE = 25;

/** The story with a line naming the day wherever it changes from the day the run started. */
function withDays(lines, startedAt) {
  const out = [];
  let day = formatDay(startedAt);
  for (const line of lines) {
    const lineDay = formatDay(line.at);
    if (lineDay && day && lineDay !== day) out.push({ day: lineDay });
    if (lineDay) day = lineDay;
    out.push(line);
  }
  return out;
}

/** One line of the story: when, what happened in words, and what it ran or said. */
function RunLine({ line }) {
  const tone = line.tone ? ` tone-${line.tone}` : "";
  if (line.day) {
    // A run can be touched again on a later day; the times alone would not say so.
    return <li className="run-line run-line--day">{line.day}</li>;
  }
  return (
    <li className="run-line">
      <Mono quiet className="run-line__at">
        {formatClock(line.at)}
      </Mono>
      <div className="run-line__what">
        {line.says || line.mono ? (
          <p className="run-line__head">
            {line.says ? <span className={`run-line__says${tone}`}>{line.says}</span> : null}
            {line.says && line.mono ? " " : null}
            {line.mono ? <Mono className="run-line__mono">{line.mono}</Mono> : null}
          </p>
        ) : null}
        {line.body ? (
          line.output ? (
            <pre className="run-output__text run-line__output">{line.body}</pre>
          ) : line.prose ? (
            <LongText>{line.body}</LongText>
          ) : (
            <pre className={line.clamp ? "run-output__text run-line__result" : "run-output__text"}>{line.body}</pre>
          )
        ) : null}
      </div>
    </li>
  );
}

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

function RunOutput({ run }) {
  const output = useResource(["run-output", run.id], (client, options) => getRunOutput(client, run.id, options));
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
export function ActivityTab({ task, revision, changed }) {
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
  // Nothing reads a note once the task is finished.
  const finished = task.status === "done" || task.status === "cancelled";
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
      <ToldTheAgent task={task} />
      {finished ? null : (
        <TellAgent
          task={task}
          running={items.find(agentAtWork) ?? null}
          onSent={() => {
            runs.reload?.();
            changed?.(null);
          }}
        />
      )}
    </div>
  );
}
