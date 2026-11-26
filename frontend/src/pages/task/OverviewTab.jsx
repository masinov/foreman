import React from "react";

import { getProjectWorkflow } from "../../api/projects";
import { getSprint } from "../../api/sprints";
import { useResource } from "../../api/useResource";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { LongText } from "../../ui/LongText";
import { Markdown } from "../../ui/Markdown";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { StatusDot } from "../../ui/StatusDot";
import { Table } from "../../ui/Table";
import { formatDay, formatTokens, humanize } from "../../ui/format";
import { Spend } from "../../ui/Spend";
import { useProjectEngine } from "../shared/useProjectEngine";
import { stageOf } from "../sprint/taskStage";
import { Overrides } from "./Overrides";
import { RestsOn } from "./RestsOn";
import { filedBy, stepRows, whoDecides } from "./taskWords";

function Steps({ task, workflow }) {
  const engine = useProjectEngine(task.project_id);
  const columns = [
    { key: "step", header: "Step", className: "task-steps__step", render: (row) => row.label },
    {
      key: "result",
      header: "Result",
      render: (row) => (
        <span className={`tone-${row.result.tone}`} title={row.result.title || undefined}>
          {row.result.word}
        </span>
      ),
    },
    { key: "by", header: "By", className: "secondary", render: (row) => (row.byTitle ? <span title={row.byTitle}>{row.by}</span> : row.by) },
    { key: "runs", header: "Attempts", numeric: true, render: (row) => (row.runs ? <Mono quiet>{row.runs}</Mono> : null) },
  ];
  return (
    <section className="task-section" aria-labelledby="task-steps">
      <SectionHeading id="task-steps" title="Steps" />
      {workflow.error ? (
        <p className="notice notice--error" role="alert">
          {workflow.error}
        </p>
      ) : null}
      {workflow.data ? <Table caption="Steps" columns={columns} rows={stepRows(task, workflow.data, engine)} /> : null}
    </section>
  );
}

/** Whether the agent has read a note, in words. */
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

/** Tasks this one waits for, or that wait for it: each a link, saying whether it is finished. */
function Dependencies({ items, engine }) {
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
        const stage = stageOf(item, engine);
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
/** What was filed: the description and the acceptance criteria, as written. */
function Filed({ task }) {
  return (
    <>
      <section className="task-section" aria-labelledby="task-description">
        <SectionHeading id="task-description" title="Description" />
        {task.description ? (
          <LongText className="task-text">
            <Markdown text={task.description} />
          </LongText>
        ) : (
          <p className="empty">No description was filed.</p>
        )}
      </section>
      <section className="task-section" aria-labelledby="task-criteria">
        <SectionHeading id="task-criteria" title="Acceptance criteria" />
        {task.acceptance_criteria ? (
          <LongText className="task-text">
            <Markdown text={task.acceptance_criteria} />
          </LongText>
        ) : (
          <p className="empty">No acceptance criteria were filed.</p>
        )}
      </section>
    </>
  );
}

/** "while working on FOR-12": the task an agent filed this from, linked. */
function FiledFrom({ from }) {
  if (!from.exists) return <> while working on a task that no longer exists</>;
  const label = from.task_key || from.task_id;
  const href = from.run_id ? paths.taskRun(from.task_id, from.run_id) : paths.taskActivity(from.task_id);
  return (
    <>
      {" while working on "}
      <Link className="row-link" href={href}>
        <Mono quiet>{label}</Mono>
      </Link>
    </>
  );
}

function Details({ task, workflow }) {
  const usage = task.totals?.token_usage ?? {};
  const engine = useProjectEngine(task.project_id);
  const stage = stageOf(task, engine);
  const deciders = whoDecides(task, workflow.data);
  const who = filedBy(task);
  const when = formatDay(task.created_at);
  const rows = [
    { key: "stage", term: "Status", value: stage.title ? <span title={stage.title}><StatusDot tone={stage.tone}>{stage.word}</StatusDot></span> : <StatusDot tone={stage.tone}>{stage.word}</StatusDot> },
    task.closed_by_hand
      ? {
          key: "closed",
          term: "Marked done",
          value: (
            <>
              By hand{task.closed_by_hand.by ? ` by ${task.closed_by_hand.by}` : ""}
              {formatDay(task.closed_by_hand.at) ? ` on ${formatDay(task.closed_by_hand.at)}` : ""}, not checked by
              Foreman.{task.closed_by_hand.reason ? <span className="secondary"> {task.closed_by_hand.reason}</span> : null}
            </>
          ),
        }
      : null,
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
      ? { key: "depends", term: "Depends on", value: <Dependencies items={task.dependencies} engine={engine} /> }
      : null,
    // What waits for it: what holding it holds too (ADR-0043).
    task.needed_by?.length
      ? { key: "needed", term: "Needed by", value: <Dependencies items={task.needed_by} engine={engine} /> }
      : null,
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
    // A working copy exists while the task is worked on; none says nothing.
    task.worktree_path
      ? { key: "copy", term: "Working copy", value: <Mono className="task-details__branch">{task.worktree_path}</Mono> }
      : null,
    {
      key: "spend",
      term: "Spend",
      value: <Spend amount={task.totals?.total_cost_usd} />,
    },
    usage.input || usage.output || usage.cache_read
      ? {
          key: "tokens",
          term: "Tokens",
          value: (
            <Mono>
              {`${formatTokens(usage.input)} in · ${formatTokens(usage.output)} out · ${formatTokens(usage.cache_read)} cached`}
            </Mono>
          ),
        }
      : null,
    {
      key: "filed",
      term: "Filed by",
      value:
        who || when ? (
          <span className="secondary">
            {who}
            {task.filed_from ? <FiledFrom from={task.filed_from} /> : null}
            {when ? `${who || task.filed_from ? " " : ""}on ${when}` : ""}
          </span>
        ) : null,
    },
    task.assigned_role ? { key: "role", term: "Last role", value: humanize(task.assigned_role) } : null,
  ].filter((row) => row && row.value !== null);

  return (
    <section className="task-section" aria-labelledby="task-details">
      <SectionHeading id="task-details" title="Details" />
      <dl className="details-list">
        {rows.map((row) => (
          <div key={row.key} className="details-list__row">
            <dt>{row.term}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/**
 * Overview: in the wide column what happened and what was asked for (the
 * steps, the description and criteria as filed); beside it the task's
 * facts and its own settings. Checks have their own tab (owner, 2026-11-22).
 */
export function OverviewTab({ task, changed }) {
  const workflow = useResource(
    ["workflow", task.project_id],
    (client, options) => getProjectWorkflow(client, task.project_id, options),
    { enabled: Boolean(task.project_id) },
  );
  // Nothing reads guidance or an override once the task is finished.
  const finished = task.status === "done" || task.status === "cancelled";
  return (
    <div className="page-overview">
      <div className="page-overview__main">
        <Steps task={task} workflow={workflow} />
        <Filed task={task} />
        <RestsOn task={task} onChanged={changed} />
      </div>
      <aside className="page-overview__aside" aria-label="Details and overrides">
        <Details task={task} workflow={workflow} />
        {finished ? null : <Overrides task={task} workflow={workflow.data} onSaved={() => changed(null)} />}
      </aside>
    </div>
  );
}
