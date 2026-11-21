import React, { useState } from "react";

import { listSprintActivity } from "../../api/sprints";
import { usePagedList } from "../../api/usePagedList";
import { paths } from "../../app/paths";
import { Button } from "../../ui/Button";
import { ListPager } from "../../ui/ListPager";
import { SectionHeading } from "../../ui/SectionHeading";
import { formatMoney, shortSha } from "../../ui/format";
import { ActivityTable } from "../shared/ActivityTable";
import { runBy, runTook, stepEvent } from "../shared/activityWords";

// Design README: activity 25 at a time.
export const STEPS_PAGE = 25;

const FILTERS = [
  { key: "all", label: "All", problems: false },
  { key: "problems", label: "Problems", problems: true },
];

const EMPTY = {
  all: "Nothing has happened to this sprint's tasks yet.",
  problems: "Nothing was sent back, failed or was blocked in this sprint.",
};

/** A row of the sprint's activity: the task, what happened to it, who, how long, what it cost. */
function describe(item) {
  return {
    at: item.at,
    subject: { key: item.task_key, title: item.task_title },
    event: stepEvent(item),
    by: runBy(item),
    commit: item.commit_sha ? shortSha(item.commit_sha) : "",
    took: runTook(item),
    spend: item.cost_usd ? formatMoney(item.cost_usd) : "",
    // A run leads to itself on the task's Activity; what a person did, to the task.
    href: item.source === "run" ? paths.taskRun(item.task_id, item.id) : paths.task(item.task_id),
  };
}

/**
 * What happened to the sprint's tasks, newest first: the work of an agent,
 * tests, a review, a person's decision, a merge, a block, and what a person
 * did by hand. Steps that only keep a record are left out (the API says
 * which). The list reads again whenever the project changes.
 */
export function SprintActivity({ sprintId }) {
  const [filterKey, setFilterKey] = useState("all");
  const filter = FILTERS.find((entry) => entry.key === filterKey);
  const list = usePagedList(
    ["sprint-activity", sprintId, filterKey],
    (client, options) => listSprintActivity(client, sprintId, { problems: filter.problems, ...options }),
    { pageSize: STEPS_PAGE },
  );

  return (
    <section className="steps" aria-labelledby="sprint-activity">
      <SectionHeading
        id="sprint-activity"
        title="Activity"
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
        <ActivityTable
          caption="Activity"
          items={list.items}
          describe={describe}
          keyHeader="Key"
          subjectHeader="Task"
          numbers={["took", "spend"]}
          rowKey={(item) => `${item.source}:${item.id}`}
        />
      ) : null}
      <ListPager
        more="Earlier"
        loading={list.loadingMore}
        hasMore={list.hasMore}
        expanded={list.expanded}
        onMore={() => list.loadMore()}
        onFewer={list.collapse}
      />
    </section>
  );
}
