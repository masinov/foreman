import React, { useId, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { getProjectWorkflow } from "../../api/projects";
import { getSprint } from "../../api/sprints";
import { sendGuidance } from "../../api/tasks";
import { useResource } from "../../api/useResource";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Disclosure } from "../../ui/Disclosure";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { StatusDot } from "../../ui/StatusDot";
import { Table } from "../../ui/Table";
import { formatDay, formatDayTime, formatMoney, formatTokens, humanize, plural } from "../../ui/format";
import { stageOf } from "../sprint/taskStage";
import { Overrides } from "./Overrides";
import { criteriaSummary, filedBy, stepRows, testsWords, whoDecides } from "./taskWords";

function Steps({ task, workflow }) {
  const total = task.totals?.run_count ?? task.runs?.length ?? 0;
  const columns = [
    { key: "step", header: "Step", className: "task-steps__step", render: (row) => row.label },
    {
      key: "result",
      header: "Result",
      render: (row) => <span className={`tone-${row.result.tone}`}>{row.result.word}</span>,
    },
    { key: "by", header: "By", className: "secondary", render: (row) => row.by },
    { key: "runs", header: "Runs", numeric: true, render: (row) => (row.runs ? <Mono quiet>{row.runs}</Mono> : null) },
  ];
  return (
    <section className="task-section" aria-labelledby="task-steps">
      <SectionHeading id="task-steps" title="Steps" />
      {workflow.error ? (
        <p className="notice notice--error" role="alert">
          {workflow.error}
        </p>
      ) : null}
      {workflow.data ? <Table caption="Steps" columns={columns} rows={stepRows(task, workflow.data)} /> : null}
      <p className="task-section__foot">
        {plural(total, "run")} in all. Every run and its output is under{" "}
        <Link href={paths.taskActivity(task.id)}>Activity</Link>.
      </p>
    </section>
  );
}

function ChecksSummary({ task, checks }) {
  const data = checks.data;
  const tests = data ? testsWords(data.facts.tests) : null;
  return (
    <section className="task-section" aria-labelledby="task-checks-summary">
      <SectionHeading
        id="task-checks-summary"
        title="Checks"
        actions={
          <Link className="section-link" href={paths.taskChecks(task.id)}>
            All checks
          </Link>
        }
      />
      {checks.error ? (
        <p className="notice notice--error" role="alert">
          {checks.error}
        </p>
      ) : null}
      {data ? (
        <div className="task-checks-line">
          <span>
            <span className={`tone-${tests.tone}`}>Tests {tests.word.toLowerCase()}</span>
            {tests.detail ? ` ${tests.detail}` : ""}
          </span>
          <span>{criteriaSummary(data.claims)}</span>
          <span>
            {data.evidence_files.length
              ? plural(data.evidence_files.length, "evidence file")
              : "No evidence files required by this workflow"}
          </span>
        </div>
      ) : null}
    </section>
  );
}

/** Whether the agent has read a note, in words. */
function noteState(note) {
  if (!note.delivered) return { tone: "attention", word: "Waiting for the next agent step" };
  const step = note.delivered_step ? humanize(note.delivered_step).toLowerCase() : "";
  const when = formatDayTime(note.delivered_at);
  return { tone: "passed", word: ["Read by the agent", step ? `at ${step}` : "", when ? `on ${when}` : ""].filter(Boolean).join(" ") };
}

function Guidance({ task, onSaved }) {
  const client = useApiClient();
  const fieldId = useId();
  const noteId = useId();
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState(null);
  const notes = [...(task.guidance ?? [])].reverse();
  const finished = task.status === "done" || task.status === "cancelled";

  async function save(event) {
    event.preventDefault();
    if (!text.trim()) {
      setNotice({ error: true, text: "Write the guidance first." });
      return;
    }
    setSaving(true);
    setNotice(null);
    try {
      const result = await sendGuidance(client, task.id, text.trim());
      setText("");
      setNotice({ error: false, text: result?.message || "Saved." });
      onSaved();
    } catch (error) {
      setNotice({ error: true, text: errorSentence(error) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="task-section" aria-labelledby={`${fieldId}-heading`}>
      <div className="section-heading">
        <h2 className="section-heading__title" id={`${fieldId}-heading`}>
          <label htmlFor={fieldId}>Guidance for the next agent step</label>
        </h2>
        <span className="section-heading__note" id={noteId}>
          {finished ? "The task is finished, so no agent step will read it." : "The next agent step for this task reads it."}
        </span>
      </div>
      <form className="guidance" onSubmit={save} noValidate>
        <textarea
          id={fieldId}
          className="field__input field__input--multiline"
          rows={3}
          placeholder="Nothing written"
          aria-describedby={noteId}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <div className="guidance__actions">
          <Button type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save guidance"}
          </Button>
          {notice ? (
            <span className={notice.error ? "notice notice--error" : "notice"} role={notice.error ? "alert" : "status"}>
              {notice.text}
            </span>
          ) : null}
        </div>
      </form>
      {notes.length ? (
        <ul className="guidance__notes" aria-label="Guidance written">
          {notes.map((note) => {
            const state = noteState(note);
            return (
              <li key={note.event_id} className="guidance__note">
                <p className="guidance__text">{note.text}</p>
                <span className="guidance__meta">
                  <StatusDot tone={state.tone}>{state.word}</StatusDot>
                  <span className="quiet">Written {formatDayTime(note.recorded_at)}</span>
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}

function SprintLink({ task }) {
  const sprint = useResource(
    ["sprint", task.sprint_id],
    (client, options) => getSprint(client, task.sprint_id, options),
    { enabled: Boolean(task.sprint_id) && !task.in_backlog },
  );
  if (task.in_backlog) return <Link href={paths.projectBacklog(task.project_id)}>Backlog</Link>;
  if (!task.sprint_id) return null;
  return <Link href={paths.sprint(task.sprint_id)}>{sprint.data?.title || task.sprint_id}</Link>;
}

/** The tasks this one waits for: each a link, saying whether it is finished. */
function Dependencies({ items }) {
  return (
    <ul className="task-details__list">
      {items.map((item) => {
        if (!item.title) {
          return (
            <li key={item.id} className="quiet">
              A task that no longer exists
            </li>
          );
        }
        const stage = stageOf(item);
        return (
          <li key={item.id}>
            <Link className="row-link" href={paths.task(item.id)}>
              {item.task_key ? <Mono quiet>{item.task_key}</Mono> : null} {item.title}
            </Link>{" "}
            <span className={item.status === "done" ? "tone-passed" : "quiet"}>
              {item.status === "done" ? "done" : stage.word.toLowerCase()}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * What the engine keeps about a task that a person rarely needs: closed
 * until asked for.
 */
function MoreDetails({ task }) {
  const usage = task.totals?.token_usage ?? {};
  const visits = Object.entries(task.step_visit_counts ?? {}).filter(([, count]) => count > 0);
  const rows = [
    {
      key: "copy",
      term: "Working copy",
      value: task.worktree_path ? (
        <Mono className="task-details__branch">{task.worktree_path}</Mono>
      ) : (
        <span className="quiet">None now. One exists while the task is being worked on.</span>
      ),
    },
    {
      key: "tokens",
      term: "Tokens",
      value: (
        <Mono>
          {`${formatTokens(usage.input)} in · ${formatTokens(usage.output)} out · ${formatTokens(usage.cache_read)} read from cache`}
        </Mono>
      ),
    },
    {
      key: "visits",
      term: "Times at each step",
      value: visits.length ? (
        visits.map(([step, count]) => `${humanize(step)} ${count}`).join(" · ")
      ) : (
        <span className="quiet">No step has run</span>
      ),
    },
    task.assigned_role ? { key: "role", term: "Last role", value: humanize(task.assigned_role) } : null,
  ].filter(Boolean);
  return (
    <Disclosure summary="More details" className="task-details__more">
      <dl className="task-details__list-terms">
        {rows.map((row) => (
          <div key={row.key} className="task-details__row">
            <dt>{row.term}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </Disclosure>
  );
}

function Details({ task, workflow }) {
  const stage = stageOf(task);
  const deciders = whoDecides(task, workflow.data);
  const who = filedBy(task);
  const when = formatDay(task.created_at);
  const rows = [
    { key: "stage", term: "Stage", value: <StatusDot tone={stage.tone}>{stage.word}</StatusDot> },
    { key: "sprint", term: "Sprint", value: <SprintLink task={task} /> },
    { key: "workflow", term: "Workflow", value: workflow.data ? workflow.data.name || workflow.data.id : null },
    {
      key: "decides",
      term: "Who decides",
      value: deciders.length ? (
        <ul className="task-details__list">
          {deciders.map((item) => (
            <li key={item.key}>
              {item.text} <span className="quiet">({item.source})</span>
            </li>
          ))}
        </ul>
      ) : null,
    },
    task.dependencies?.length
      ? { key: "depends", term: "Depends on", value: <Dependencies items={task.dependencies} /> }
      : null,
    task.complexity ? { key: "size", term: "Size", value: humanize(task.complexity) } : null,
    task.priority
      ? {
          key: "priority",
          term: "Priority",
          value: (
            <>
              {task.priority} <span className="quiet">(lower runs first; 0 is the default)</span>
            </>
          ),
        }
      : null,
    { key: "branch", term: "Branch", value: task.branch_name ? <Mono className="task-details__branch">{task.branch_name}</Mono> : <span className="quiet">None yet</span> },
    {
      key: "spend",
      term: "Spend",
      value: <Mono>{`${formatMoney(task.totals?.total_cost_usd)} · ${plural(task.totals?.run_count ?? 0, "run")}`}</Mono>,
    },
    {
      key: "filed",
      term: "Filed by",
      value: who || when ? <span className="secondary">{[who, when ? `on ${when}` : ""].filter(Boolean).join(" ")}</span> : null,
    },
  ].filter((row) => row && row.value !== null);

  return (
    <aside className="task-details" aria-labelledby="task-details">
      <SectionHeading id="task-details" title="Details" />
      <dl className="task-details__list-terms">
        {rows.map((row) => (
          <div key={row.key} className="task-details__row">
            <dt>{row.term}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
      <MoreDetails task={task} />
      <SectionHeading id="task-description" title="Description" />
      {task.description ? <p className="task-text">{task.description}</p> : <p className="empty">No description was filed.</p>}
      <SectionHeading id="task-criteria" title="Acceptance criteria" />
      {task.acceptance_criteria ? (
        <p className="task-text">{task.acceptance_criteria}</p>
      ) : (
        <p className="empty">No acceptance criteria were filed.</p>
      )}
    </aside>
  );
}

/** Overview: steps, a line of checks, guidance, and the task's details as filed. */
export function OverviewTab({ task, checks, changed }) {
  const workflow = useResource(
    ["workflow", task.project_id],
    (client, options) => getProjectWorkflow(client, task.project_id, options),
    { enabled: Boolean(task.project_id) },
  );
  return (
    <div className="task-overview">
      <div className="task-overview__main">
        <Steps task={task} workflow={workflow} />
        <ChecksSummary task={task} checks={checks} />
        <Overrides task={task} workflow={workflow.data} onSaved={() => changed(null)} />
        <Guidance task={task} onSaved={() => changed(null)} />
      </div>
      <Details task={task} workflow={workflow} />
    </div>
  );
}
