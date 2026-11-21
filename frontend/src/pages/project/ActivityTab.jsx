import React, { useState } from "react";

import { listMilestones, MILESTONE_FILTERS } from "../../api/milestones";
import { useDelayedFlag } from "../../api/useResource";
import { usePagedList } from "../../api/usePagedList";
import { Button } from "../../ui/Button";
import { ListPager } from "../../ui/ListPager";
import { SectionHeading } from "../../ui/SectionHeading";
import { MilestoneTable } from "../shared/milestones";

// Design README: activity 25 at a time.
export const ACTIVITY_PAGE = 25;

// What is true when a filter finds nothing, and what would appear.
const EMPTY = {
  all: "Nothing has happened yet. Sprints being planned, starting and finishing, and the engine stopping, appear here.",
  sprints: "No sprint has been planned, started or finished yet.",
  engine: "The engine has not started yet.",
};

/**
 * The Activity tab: what happened to the project's sprints and its engine,
 * newest first. What happened to a task is on its sprint's page.
 */
export function ActivityTab({ projectId }) {
  const [filterKey, setFilterKey] = useState("all");
  const filter = MILESTONE_FILTERS.find((entry) => entry.key === filterKey);
  const list = usePagedList(
    ["milestones", projectId, filterKey],
    (client, options) => listMilestones(client, { projectId, kinds: filter.kinds, ...options }),
    { pageSize: ACTIVITY_PAGE },
  );
  const placeholder = useDelayedFlag(list.loading && !list.items);

  return (
    <section className="activity" aria-labelledby="activity-title">
      <SectionHeading
        id="activity-title"
        title="Sprints and engine"
        actions={
          <div className="filter-group" role="group" aria-label="Show">
            {MILESTONE_FILTERS.map((entry) => (
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
      {placeholder ? <MilestoneTable caption="Activity" placeholderRows={3} /> : null}
      {list.items && list.items.length === 0 ? (
        <p className="empty">{EMPTY[filterKey]}</p>
      ) : null}
      {list.items && list.items.length > 0 ? <MilestoneTable caption="Activity" items={list.items} /> : null}
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
