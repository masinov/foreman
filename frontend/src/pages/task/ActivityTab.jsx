import React, { useEffect, useLayoutEffect, useRef, useState } from "react";

import { getRunOutput, listTaskRuns } from "../../api/tasks";
import { usePagedList } from "../../api/usePagedList";
import { useRoute } from "../../app/router";
import { useResource } from "../../api/useResource";
import { ListPager } from "../../ui/ListPager";
import { Disclosure } from "../../ui/Disclosure";
import { SectionHeading } from "../../ui/SectionHeading";
import { formatDayTime, formatMoney, humanize, plural, shortSha } from "../../ui/format";
import { narrate } from "./runWords";
import { RunLine, withDays } from "./RunStory";
import { ActivityTable } from "../shared/ActivityTable";
import { runBy, runResult, runTook } from "../shared/activityWords";
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

function RunOutput({ run, task, pulse = 0 }) {
  const output = useResource(["run-output", run.id], (client, options) => getRunOutput(client, run.id, options));
  const reload = output.reload;
  // `pulse` grows while this run is in progress and printing.
  useEffect(() => {
    if (pulse) reload();
  }, [pulse, reload]);
  const by = runBy(run, task);
  const { note: why, tone } = runResult(run);
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
      {why ? <p className={`run-output__why tone-${tone}`}>{why}</p> : null}
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
 * Activity: every run of the task, newest first, 25 at a time with Earlier,
 * and under the list what the picked run said and did.
 *
 * A link may name the run to show (`?run=`, from a sprint's or a project's
 * activity); it is picked while it is among the runs listed.
 *
 * Picking is pressing a run's row. The picked row is shaded and its time is
 * gold, as a picked file is on the Changes tab. A row has no caret: a caret
 * says "this opens right under me", and what a run shows is under the whole
 * list. The newest run is shown until a person picks one; after that the
 * pick stays while newer runs arrive above it.
 *
 * While the task runs the list is read again in place (`revision` grows):
 * the rows stay on screen, a run that was not there opens into place, and
 * what is shown under the list is left alone unless it is the run that
 * changed.
 */
export function ActivityTab({ task, revision }) {
  const pulse = useTaskPulse(task.id, task.status === "in_progress");
  const runs = usePagedList(["task-runs", task.id], (client, options) => listTaskRuns(client, task.id, options), {
    pageSize: RUNS_PAGE,
  });
  const reloadRuns = runs.reload;
  const mounted = useRef(false);
  useEffect(() => {
    // The first reading is the list's own; later changes of `revision` read it again.
    if (mounted.current) reloadRuns();
    mounted.current = true;
  }, [revision, reloadRuns]);

  const { query } = useRoute();
  const named = query.get("run");
  const [picked, setPicked] = useState(named);
  useEffect(() => {
    if (named) setPicked(named);
  }, [named]);
  const items = runs.items ?? [];
  const selected = items.find((run) => run.id === picked) ?? items[0] ?? null;

  // The runs that were not in the list the last time it was drawn.
  const known = useRef(null);
  const [arrived, setArrived] = useState(() => new Set());
  useLayoutEffect(() => {
    if (!runs.items) return;
    const ids = runs.items.map((run) => run.id);
    if (known.current) {
      const fresh = ids.filter((id) => !known.current.has(id));
      if (fresh.length) setArrived(new Set(fresh));
    }
    known.current = new Set(ids);
  }, [runs.items]);

  // A row of the task's activity: the step, how it ended, who, the commit it
  // left, how long, what it cost. Why is on hover, and above the picked run.
  const describe = (run) => {
    const result = runResult(run);
    return {
      at: run.started_at,
      subject: { key: null, title: humanize(run.step) },
      event: { word: result.word, tone: result.tone, why: result.note },
      by: runBy(run, task),
      commit: run.commit_sha ? shortSha(run.commit_sha) : "",
      took: runTook(run),
      spend: run.cost_usd ? formatMoney(run.cost_usd) : "",
    };
  };

  const totals = task.totals ?? {};
  return (
    <div className="task-activity">
      <section className="task-section" aria-labelledby="task-runs">
        <SectionHeading
          id="task-runs"
          title="Activity"
          note={`${plural(totals.run_count ?? runs.total ?? 0, "run")}, ${formatMoney(totals.total_cost_usd)}`}
        />
        {runs.error ? (
          <p className="notice notice--error" role="alert">
            {runs.error}
          </p>
        ) : null}
        {runs.items && items.length === 0 ? <p className="empty">Nothing has run on this task yet.</p> : null}
        {items.length ? (
          <ActivityTable
            caption="Runs"
            items={items}
            describe={describe}
            subjectHeader="Step"
            numbers={["commit", "took", "spend"]}
            rowKey={(run) => run.id}
            onRowClick={(run) => setPicked(run.id)}
            selected={(run) => run === selected}
            arrived={(run) => arrived.has(run.id)}
          />
        ) : null}
        <ListPager
          more="Earlier"
          loading={runs.loadingMore}
          hasMore={runs.hasMore}
          expanded={runs.expanded}
          onMore={() => runs.loadMore()}
          onFewer={runs.collapse}
        />
      </section>
      {selected ? (
        <RunOutput key={selected.id} run={selected} task={task} pulse={selected.status === "running" ? pulse : 0} />
      ) : null}
    </div>
  );
}
