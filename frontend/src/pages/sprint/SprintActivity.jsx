import React, { useId, useState } from "react";

import { listSprintActivity } from "../../api/sprints";
import { useDelayedFlag } from "../../api/useResource";
import { usePagedList } from "../../api/usePagedList";
import { paths } from "../../app/paths";
import { Button } from "../../ui/Button";
import { ListPager } from "../../ui/ListPager";
import { formatMoney, shortSha } from "../../ui/format";
import { ActivityTable } from "../shared/ActivityTable";
import { runRole, runTook, stepEvent, whoWord } from "../shared/activityWords";

// Design README: activity 25 at a time.
export const STEPS_PAGE = 25;

const FILTERS = [
  { key: "all", label: "All", problems: false },
  { key: "problems", label: "Problems", problems: true },
];

// The roles come first, then the engine, then people.
const LAST = ["foreman", "user"];

const EMPTY = {
  all: "Nothing has happened to this sprint's tasks yet.",
  problems: "Nothing was sent back, failed or was blocked in this sprint.",
};
const EMPTY_BY = "Nothing in this sprint matches these filters.";

/** A row of the sprint's activity: the task, what happened to it, who, how long, what it cost. */
function describe(item) {
  const by = runRole(item);
  return {
    at: item.at,
    subject: { key: item.task_key, title: item.task_title },
    event: stepEvent(item),
    by: by.text,
    byTitle: by.title,
    commit: item.commit_sha ? shortSha(item.commit_sha) : "",
    took: runTook(item),
    spend: item.cost_usd ? formatMoney(item.cost_usd) : "",
    // A run leads to itself on the task's Activity; what a person did, to the task.
    href: item.source === "run" ? paths.taskRun(item.task_id, item.id) : paths.task(item.task_id),
  };
}

/** Everyone, then each role, Foreman and users that appear in the sprint's activity. */
function byOptions(who, chosen) {
  const present = [...new Set([...(who ?? []), ...(chosen ? [chosen] : [])])];
  const roles = present.filter((value) => !LAST.includes(value));
  return [...roles, ...LAST.filter((value) => present.includes(value))];
}

/**
 * The sprint's Activity tab: what happened to its tasks, newest first, the
 * work of an agent, tests, a review, a user's decision, a merge, a block,
 * and what a user did by hand. Steps that only keep a record are left out
 * (the API says which). By keeps what one role, Foreman or users did;
 * Problems keeps what sent a task back or stopped it. Both are on the tab
 * line (`tabLine(controls)`). The list reads again whenever the project
 * changes.
 */
export function SprintActivity({ sprintId, tabLine }) {
  const byId = useId();
  const [filterKey, setFilterKey] = useState("all");
  const [by, setBy] = useState("");
  const filter = FILTERS.find((entry) => entry.key === filterKey);
  const list = usePagedList(
    ["sprint-activity", sprintId, filterKey, by],
    (client, options) => listSprintActivity(client, sprintId, { problems: filter.problems, by, ...options }),
    { pageSize: STEPS_PAGE },
  );
  const placeholder = useDelayedFlag(list.loading && !list.items);
  const filtered = Boolean(by) || filter.problems;

  return (
    <div className="sprint__tabs">
      {tabLine(
        <>
          <label className="tabs__label" htmlFor={byId}>
            By
          </label>
          <select id={byId} className="field__input tabs__select" value={by} onChange={(event) => setBy(event.target.value)}>
            <option value="">Everyone</option>
            {byOptions(list.meta?.who, by).map((value) => (
              <option key={value} value={value}>
                {whoWord(value)}
              </option>
            ))}
          </select>
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
        </>,
      )}
      <div className="sprint__tab">
        {list.error ? (
          <p className="notice notice--error" role="alert">
            {list.error}
          </p>
        ) : null}
        {placeholder ? (
          <ActivityTable
            caption="Activity"
            describe={describe}
            keyHeader="Key"
            subjectHeader="Task"
            numbers={["took", "spend"]}
            rowKey={() => ""}
            placeholderRows={3}
          />
        ) : null}
        {list.items && list.items.length === 0 ? (
          <p className="empty">{by ? EMPTY_BY : EMPTY[filterKey]}</p>
        ) : null}
        {list.items && list.items.length > 0 ? (
          <ActivityTable
            caption={filtered ? "Activity, filtered" : "Activity"}
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
      </div>
    </div>
  );
}
