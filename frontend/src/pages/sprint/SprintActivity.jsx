import React, { useEffect, useRef, useState } from "react";

import { listSprintRuns } from "../../api/sprints";
import { usePagedList } from "../../api/usePagedList";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { ListPager } from "../../ui/ListPager";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { formatDayTime, formatDuration, formatMoney, humanize } from "../../ui/format";
import { ResultCell } from "../shared/ActivityResult";
import { runBy, runResult, runSeconds } from "../shared/activityWords";

// Design README: activity 25 at a time.
export const STEPS_PAGE = 25;

const FILTERS = [
  { key: "all", label: "All", problems: false },
  { key: "problems", label: "Send-backs and failures", problems: true },
];

const EMPTY = {
  all: "No step has finished in this sprint yet.",
  problems: "Nothing was sent back and nothing failed in this sprint.",
};

/**
 * What happened to each task of the sprint, step by step, newest first: the
 * work of an agent, tests, a review, a person's decision, a merge. Steps that
 * only keep a record (filing a task, marking it done) are left out. Each row
 * says who did it, how it ended and why, and leads to that run on the task's
 * Activity. `revision` grows when the page changed, so the list is read again.
 */
export function SprintActivity({ sprintId, revision }) {
  const [filterKey, setFilterKey] = useState("all");
  const filter = FILTERS.find((entry) => entry.key === filterKey);
  const list = usePagedList(
    ["sprint-runs", sprintId, filterKey],
    (client, options) => listSprintRuns(client, sprintId, { problems: filter.problems, ...options }),
    { pageSize: STEPS_PAGE },
  );
  const reload = list.reload;
  const mounted = useRef(false);
  useEffect(() => {
    // The first reading is the list's own; later changes of `revision` read it again.
    if (mounted.current) reload();
    mounted.current = true;
  }, [revision, reload]);

  const hrefOf = (run) => paths.taskRun(run.task_id, run.id);
  const columns = [
    { key: "when", header: "When", className: "steps__when", render: (run) => <Mono quiet>{formatDayTime(run.started_at)}</Mono> },
    {
      key: "task",
      header: "Task",
      className: "steps__task",
      render: (run) => (
        <Link className="row-link" href={hrefOf(run)} title={run.task_title}>
          <Mono quiet>{run.task_key ?? ""}</Mono> {run.task_title}
        </Link>
      ),
    },
    { key: "step", header: "Step", className: "steps__step", render: (run) => humanize(run.step) },
    { key: "by", header: "By", className: "secondary", render: (run) => runBy(run) },
    { key: "result", header: "Result", render: (run) => <ResultCell result={runResult(run)} /> },
    { key: "took", header: "Took", numeric: true, render: (run) => <Mono quiet>{formatDuration(runSeconds(run))}</Mono> },
    {
      key: "spend",
      header: "Spend",
      numeric: true,
      render: (run) => (run.cost_usd ? <Mono quiet>{formatMoney(run.cost_usd)}</Mono> : null),
    },
  ];

  return (
    <section className="steps" aria-labelledby="sprint-activity">
      <SectionHeading
        id="sprint-activity"
        title="Activity"
        note="Each step of each task, newest first."
        actions={
          <div className="filter-group" role="group" aria-label="Show">
            {FILTERS.map((entry) => (
              <Button
                key={entry.key}
                variant="quiet"
                inRow
                className="filter-group__option"
                aria-pressed={entry.key === filterKey}
                onClick={() => setFilterKey(entry.key)}
              >
                {entry.label}
              </Button>
            ))}
          </div>
        }
      />
      {list.error ? (
        <p className="notice notice--error" role="alert">
          {list.error}
        </p>
      ) : null}
      {list.items && list.items.length === 0 ? <p className="empty">{EMPTY[filterKey]}</p> : null}
      {list.items && list.items.length > 0 ? (
        <Table caption="Steps" columns={columns} rows={list.items} rowHref={hrefOf} />
      ) : null}
      <ListPager
        more="Earlier steps"
        loading={list.loadingMore}
        hasMore={list.hasMore}
        expanded={list.expanded}
        onMore={() => list.loadMore()}
        onFewer={list.collapse}
      />
    </section>
  );
}
