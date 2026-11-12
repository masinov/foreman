import React, { useEffect, useState } from "react";

import { listProjectSprints, SPRINT_STATUSES } from "../../api/sprints";
import { usePagedList } from "../../api/usePagedList";
import { useResource } from "../../api/useResource";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Disclosure } from "../../ui/Disclosure";
import { Field } from "../../ui/Field";
import { Mono } from "../../ui/Mono";
import { Table } from "../../ui/Table";
import { formatDay, formatMoney, splitTitle } from "../../ui/format";
import { describeTaskCounts } from "../shared/words";

// Design README: finished sprints 10 at a time.
export const FINISHED_PAGE = 10;

function finished(projectId, options) {
  return { statuses: [SPRINT_STATUSES.completed], order: "recent", ...options };
}

const COLUMNS = [
  {
    key: "sprint",
    header: "Sprint",
    render: (sprint) => (
      <Link className="row-link" href={paths.sprint(sprint.id)}>
        {sprint.title}
      </Link>
    ),
  },
  { key: "tasks", header: "Tasks", className: "queue__tasks", render: (sprint) => describeTaskCounts(sprint.task_counts) },
  { key: "finished", header: "Finished", className: "queue__dates", render: (sprint) => formatDay(sprint.completed_at) },
  {
    key: "spend",
    header: "Spend",
    className: "queue__number",
    render: (sprint) => <Mono>{formatMoney(sprint.totals?.total_cost_usd)}</Mono>,
  },
];

function FinishedList({ projectId }) {
  const [filter, setFilter] = useState("");
  const q = filter.trim();
  const list = usePagedList(
    ["finished-sprints", projectId, q],
    (client, options) => listProjectSprints(client, projectId, finished(projectId, { q, ...options })),
    { pageSize: FINISHED_PAGE },
  );
  return (
    <div className="finished">
      <Field
        label="Filter finished sprints"
        hideLabel
        type="search"
        placeholder="Filter finished sprints"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
        className="finished__filter"
      />
      <p className="quiet">{q ? `Matching “${q}”, newest first` : "The 10 most recent, newest first"}</p>
      {list.error ? (
        <p className="notice notice--error" role="alert">
          {list.error}
        </p>
      ) : null}
      {list.items && list.items.length === 0 ? <p className="empty">No finished sprint matches “{q}”.</p> : null}
      {list.items && list.items.length > 0 ? <Table caption="Finished sprints" columns={COLUMNS} rows={list.items} /> : null}
      {list.hasMore ? (
        <Button variant="quiet" className="list-more" disabled={list.loadingMore} onClick={() => list.loadMore()}>
          Show 10 more
        </Button>
      ) : null}
    </div>
  );
}

/**
 * Finished sprints: a closed line saying how many and the latest, which
 * opens in place to the most recent ten, filtered and paged on the server.
 */
export function FinishedSprints({ projectId, revision }) {
  const latest = useResource(["finished-sprints-latest", projectId], (client, options) =>
    listProjectSprints(client, projectId, finished(projectId, { limit: 1, ...options })),
  );
  const reload = latest.reload;
  useEffect(() => {
    if (revision) reload();
  }, [revision, reload]);

  if (latest.error) {
    return (
      <p className="notice notice--error" role="alert">
        {latest.error}
      </p>
    );
  }
  if (!latest.data) return null;
  const { total, items } = latest.data;
  if (total === 0) return <p className="quiet finished__none">No sprint has finished yet.</p>;
  const newest = items[0];
  const when = formatDay(newest.completed_at);
  return (
    <Disclosure
      className="finished__disclosure"
      summary={
        <>
          Finished sprints <span className="finished__count">{total}</span>
          <span className="quiet">
            , latest: {splitTitle(newest.title)[0]}
            {when ? `, ${when}` : ""}
          </span>
        </>
      }
    >
      <FinishedList projectId={projectId} />
    </Disclosure>
  );
}
