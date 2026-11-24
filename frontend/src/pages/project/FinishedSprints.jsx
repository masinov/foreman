import React, { useEffect, useId, useState } from "react";

import { listProjectSprints, SPRINT_STATUSES } from "../../api/sprints";
import { usePagedList } from "../../api/usePagedList";
import { useResource } from "../../api/useResource";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Caret } from "../../ui/Caret";
import { ListPager } from "../../ui/ListPager";
import { SectionHeading } from "../../ui/SectionHeading";
import { Field } from "../../ui/Field";
import { Table } from "../../ui/Table";
import { formatDay, splitTitle } from "../../ui/format";
import { Spend } from "../../ui/Spend";
import { describeTaskCounts } from "../shared/words";

// Design README: finished sprints 10 at a time.
export const FINISHED_PAGE = 10;
// The most one request may ask for.
const MAX_PAGE = 200;

function shownLine(shown, total, q) {
  const what = q ? ` matching “${q}”` : "";
  if (shown >= total) return `Showing all ${total}${what}, newest first`;
  return `Showing ${shown} of ${total}${what}, newest first`;
}

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
    render: (sprint) => <Spend amount={sprint.totals?.total_cost_usd} where="row" />,
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
        placeholder="Filter by number or title"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
        className="finished__filter"
      />
      {list.items && list.total > 0 ? <p className="quiet">{shownLine(list.items.length, list.total, q)}</p> : null}
      {list.error ? (
        <p className="notice notice--error" role="alert">
          {list.error}
        </p>
      ) : null}
      {list.items && list.items.length === 0 ? <p className="empty">No finished sprint matches “{q}”.</p> : null}
      {list.items && list.items.length > 0 ? <Table caption="Finished sprints" columns={COLUMNS} rows={list.items} /> : null}
      <ListPager
        more={`Show ${Math.min(FINISHED_PAGE, (list.total ?? 0) - (list.items?.length ?? 0))} more`}
        loading={list.loadingMore}
        hasMore={list.hasMore}
        expanded={list.expanded}
        onMore={() => list.loadMore()}
        onFewer={list.collapse}
      >
        {(list.total ?? 0) - (list.items?.length ?? 0) > FINISHED_PAGE ? (
          <Button
            variant="quiet"
            className="expander"
            disabled={list.loadingMore}
            onClick={() => list.loadMore(Math.min(list.total - list.items.length, MAX_PAGE))}
          >
            <Caret />
            Show all {list.total}
          </Button>
        ) : null}
      </ListPager>
    </div>
  );
}

/**
 * Finished sprints: a heading, folded, saying how many and the latest, which
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
  const [open, setOpen] = useState(false);
  const contentId = useId();

  if (latest.error) {
    return (
      <p className="notice notice--error" role="alert">
        {latest.error}
      </p>
    );
  }
  if (!latest.data) return null;
  const { total, items } = latest.data;
  if (total === 0) {
    return (
      <section className="finished__group">
        <SectionHeading title="Finished" />
        <p className="empty">No sprint has finished yet.</p>
      </section>
    );
  }
  const newest = items[0];
  const when = formatDay(newest.completed_at);
  return (
    <section className="finished__group">
      <SectionHeading
        title="Finished"
        count={total}
        note={`latest: ${splitTitle(newest.title)[0]}${when ? `, ${when}` : ""}`}
        expanded={open}
        onToggle={setOpen}
        controls={contentId}
      />
      <div id={contentId} hidden={!open}>
        {open ? <FinishedList projectId={projectId} /> : null}
      </div>
    </section>
  );
}
