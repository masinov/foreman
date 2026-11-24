import React, { useEffect, useLayoutEffect, useRef, useState } from "react";

import { getRunOutput, listTaskRuns } from "../../api/tasks";
import { usePagedList } from "../../api/usePagedList";
import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { paths } from "../../app/paths";
import { Link, useRoute } from "../../app/router";
import { useResource } from "../../api/useResource";
import { ListPager } from "../../ui/ListPager";
import { Button } from "../../ui/Button";
import { Caret } from "../../ui/Caret";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { formatDayTime, humanize, plural, shortSha } from "../../ui/format";
import { Spend } from "../../ui/Spend";
import { narrate } from "./runWords";
import { RunLine, withDays } from "./RunStory";
import { ActivityTable } from "../shared/ActivityTable";
import { runRole, runTook, stepOutcome } from "../shared/activityWords";
import { attemptOf, stepFacts } from "./stepFacts";
import { useTaskPulse } from "./useTaskPulse";

// Design README: activity 25 at a time.
export const RUNS_PAGE = 25;

/** How a downloaded transcript names its file: the task, the step, the run. */
function transcriptName(task, run) {
  return `${task.task_key || task.id}-${run.step}-${run.id}.txt`.replace(/[^\w.-]+/g, "-");
}

/**
 * The whole record of a run as text: its prompt, every event with what it
 * recorded, and the agent's raw stream. The page shows a story told from
 * these; this keeps all of it.
 */
export function transcriptText(task, run, output, raw) {
  const lines = [
    `${task.task_key || task.id} · ${humanize(run.step)} · ${run.id}`,
    `Started ${run.started_at ?? "?"} · ${run.status}${run.outcome ? ` · ${run.outcome}` : ""}`,
    "",
    "== Prompt ==",
    output.prompt ?? "(none recorded)",
    "",
    "== What happened ==",
  ];
  for (const entry of output.transcript ?? []) {
    const data = entry.data && Object.keys(entry.data).length ? ` ${JSON.stringify(entry.data)}` : "";
    lines.push(`${entry.at} ${entry.kind}${entry.text ? ` ${entry.text}` : ""}${data}`);
  }
  if (output.transcript_truncated) lines.push(`(Only the first ${output.cap_chars} characters of the record were kept.)`);
  if (raw?.transcript?.length) {
    lines.push("", "== Raw output ==", ...raw.transcript.map((entry) => entry.text));
  }
  return `${lines.join("\n")}\n`;
}

/** Download the transcript of a run: one file, read when asked for. */
function DownloadTranscript({ task, run, output }) {
  const client = useApiClient();
  const [state, setState] = useState({ busy: false, error: null });
  async function download() {
    setState({ busy: true, error: null });
    try {
      const raw = output.raw_entries ? await getRunOutput(client, run.id, { raw: true }) : null;
      const blob = new Blob([transcriptText(task, run, output, raw)], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = transcriptName(task, run);
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setState({ busy: false, error: null });
    } catch (error) {
      setState({ busy: false, error: errorSentence(error) });
    }
  }
  return (
    <>
      <Button className="run-facts__download" disabled={state.busy} onClick={download}>
        {state.busy ? "Preparing…" : "Download the transcript"}
      </Button>
      {state.error ? (
        <p className="notice notice--error" role="alert">
          {state.error}
        </p>
      ) : null}
    </>
  );
}

// How many changed files show before "Show all".
export const FILES_SHOWN = 5;

/** `+70 −14`, as the Changes tab writes and colours it. */
function Lines({ added, removed }) {
  return (
    <Mono>
      <span className="tone-passed">+{added ?? 0}</span> <span className="tone-failed">−{removed ?? 0}</span>
    </Mono>
  );
}

/** What a step's changes are counted against, in words. */
function againstWords(against) {
  if (against.kind === "attempt") return `since attempt ${against.attempt}'s commit ${shortSha(against.sha)}`;
  if (against.kind === "default_branch") return `since ${against.branch || "the default branch"} at ${shortSha(against.sha)}, where the branch began`;
  return `since ${shortSha(against.sha)}`;
}

/** What a step changed: how many files and lines, against what, then each file. */
function Changed({ changes }) {
  const [all, setAll] = useState(false);
  const files = [...(changes.files ?? [])].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  const shown = all ? files : files.slice(0, FILES_SHOWN);
  const total = changes.files_total ?? files.length;
  return (
    <div className="run-changes">
      <div>
        {plural(total, "file")} <Lines added={changes.added} removed={changes.removed} />
      </div>
      {changes.against ? <div className="quiet">{againstWords(changes.against)}</div> : null}
      <ul className="run-changes__files">
        {shown.map((file) => (
          <li key={file.path} className="run-changes__file">
            <span className="run-changes__path">
              <Mono title={file.path}>{file.path}</Mono>
              {file.status === "added" ? <span className="quiet"> added</span> : null}
            </span>
            {file.added === null || file.removed === null ? <span className="quiet">binary</span> : <Lines added={file.added} removed={file.removed} />}
          </li>
        ))}
      </ul>
      {files.length > FILES_SHOWN ? (
        <Button variant="quiet" className="expander" aria-expanded={all} onClick={() => setAll(!all)}>
          <Caret direction={all ? "up" : "down"} />
          {all ? "Show fewer" : `Show all ${files.length}`}
        </Button>
      ) : null}
    </div>
  );
}

/** What a merge brought in: how many commits, then each, oldest first. */
function BroughtIn({ brought }) {
  return (
    <div className="run-changes">
      <div>{plural(brought.total, "commit")}</div>
      <ul className="run-changes__files">
        {brought.commits.map((commit) => (
          <li key={commit.sha} className="run-changes__commit" title={commit.subject}>
            <Mono quiet title={commit.sha}>
              {shortSha(commit.sha)}
            </Mono>
            <span className="run-changes__subject">{commit.subject}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A fact's value: a commit, a run to pick, a link to the settings, or words. */
function FactValue({ fact, task, onPick }) {
  if (fact.changed) return <Changed changes={fact.changed} />;
  if (fact.brought) return <BroughtIn brought={fact.brought} />;
  if (fact.landed) {
    return (
      <>
        <Link className="row-link" href={paths.taskChanges(task.id)}>
          {plural(fact.landed.files_total ?? fact.landed.files?.length ?? 0, "file")}
        </Link>{" "}
        <Lines added={fact.landed.added} removed={fact.landed.removed} />
      </>
    );
  }
  if (fact.key === "session") {
    return fact.session ? (
      <>
        {fact.text}
        <button type="button" className="file-pick run-facts__pick" onClick={() => onPick(fact.session.run)}>
          {fact.session.label}
        </button>
      </>
    ) : (
      <span>{fact.text}</span>
    );
  }
  if (fact.spend) return <Spend amount={fact.spend.amount} tokens={fact.spend.tokens} />;
  if (fact.sha) return <Mono title={fact.sha}>{fact.text}</Mono>;
  if (fact.run) {
    return (
      <button type="button" className="file-pick run-facts__pick" onClick={() => onPick(fact.run)}>
        {fact.text}
      </button>
    );
  }
  if (fact.settings) {
    return (
      <Link className="row-link" href={paths.projectSettings(task.project_id)}>
        {fact.text}
      </Link>
    );
  }
  return <span className={fact.tone ? `tone-${fact.tone}` : undefined}>{fact.text}</span>;
}

/**
 * The picked run, one shape for every kind of step (owner, 2026-11-22): on
 * the left what happened, in order, each line a time, what happened, and
 * what it ran, wrote or printed, beginning with the prompt an agent was
 * sent; on the right the step's facts and the transcript to download.
 */
function RunOutput({ run, task, previous, next, onPick, pulse = 0 }) {
  const output = useResource(["run-output", run.id], (client, options) => getRunOutput(client, run.id, options));
  const reload = output.reload;
  // `pulse` grows while this run is in progress and printing.
  useEffect(() => {
    if (pulse) reload();
  }, [pulse, reload]);
  const data = output.data;
  const transcript = data?.transcript ?? [];
  const told = narrate(transcript);
  if (data?.prompt) {
    const promptLines = data.prompt.split("\n").length;
    told.unshift({
      at: run.started_at,
      kind: "prompt",
      says: `Sent the prompt · ${plural(promptLines, "line")}`,
      mono: data.prompt_truncated ? `${data.prompt}\n… (only its first ${data.cap_chars.toLocaleString("en-US")} characters were kept)` : data.prompt,
    });
  }
  const lines = data ? withDays(told, run.started_at) : [];
  const attempt = attemptOf(run, transcript);
  const facts = data ? stepFacts(run, transcript, { previous, next, task, repo: data }) : [];
  return (
    <section className="task-section run-output" aria-labelledby="run-output">
      <SectionHeading
        id="run-output"
        title={humanize(run.step)}
        note={[attempt > 1 ? `attempt ${attempt}` : null, formatDayTime(run.started_at)].filter(Boolean).join(" · ")}
      />
      {output.error ? (
        <p className="notice notice--error" role="alert">
          {output.error}
        </p>
      ) : null}
      {data ? (
        <div className="page-overview">
          <div className="page-overview__main">
            {data.transcript_truncated ? (
              <p className="notice" role="status">
                This run recorded more than {data.cap_chars.toLocaleString("en-US")} characters; the earliest of its{" "}
                {data.total_entries} events are shown. The transcript holds what was kept.
              </p>
            ) : null}
            {lines.length ? (
              <ol className="run-story" aria-label="What happened">
                {lines.map((line, index) => (
                  <RunLine key={index} line={line} />
                ))}
              </ol>
            ) : (
              <p className="empty">This run recorded nothing to read.</p>
            )}
          </div>
          <aside className="page-overview__aside run-facts" aria-label="About this step">
            <dl className="details-list">
              {facts.map((fact) => (
                <div key={fact.key} className="details-list__row">
                  <dt>{fact.term}</dt>
                  <dd>
                    <FactValue fact={fact} task={task} onPick={onPick} />
                  </dd>
                </div>
              ))}
            </dl>
            <DownloadTranscript task={task} run={run} output={data} />
          </aside>
        </div>
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

  // A row of the task's activity: the step and its attempt, how it ended,
  // who, the commit it was about, how long, what it cost. Why is on hover.
  const describe = (run) => {
    const result = stepOutcome(run, items[items.indexOf(run) + 1] ?? null);
    const by = runRole(run, task);
    const commit = run.step_commit ?? run.commit_sha;
    return {
      at: run.started_at,
      subject: { key: null, title: humanize(run.step), note: run.attempt > 1 ? `attempt ${run.attempt}` : "" },
      event: { word: result.word, tone: result.tone, why: result.note },
      by: by.text,
      byTitle: by.title,
      commit: commit ? shortSha(commit) : "",
      took: runTook(run),
      spend: run.cost_usd,
    };
  };

  const totals = task.totals ?? {};
  return (
    <div className="task-activity">
      <section className="task-section" aria-labelledby="task-runs">
        <SectionHeading
          id="task-runs"
          title="Steps"
          count={runs.total ?? undefined}
          note={<><Spend amount={totals.total_cost_usd} /> in all</>}
        />
        {runs.error ? (
          <p className="notice notice--error" role="alert">
            {runs.error}
          </p>
        ) : null}
        {runs.items && items.length === 0 ? <p className="empty">Nothing has run on this task yet.</p> : null}
        {items.length ? (
          <ActivityTable
            caption="Steps"
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
        <RunOutput
          key={selected.id}
          run={selected}
          task={task}
          previous={items[items.indexOf(selected) + 1] ?? null}
          next={items[items.indexOf(selected) - 1] ?? null}
          onPick={setPicked}
          pulse={selected.status === "running" ? pulse : 0}
        />
      ) : null}
    </div>
  );
}
