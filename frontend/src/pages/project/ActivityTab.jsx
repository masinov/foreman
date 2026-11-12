import React, { useState } from "react";

import { listMilestones, MILESTONE_FILTERS } from "../../api/milestones";
import { useDelayedFlag } from "../../api/useResource";
import { usePagedList } from "../../api/usePagedList";
import { Button } from "../../ui/Button";
import { SectionHeading } from "../../ui/SectionHeading";
import { MilestoneTable } from "../shared/milestones";

// Design README: activity 25 at a time.
export const ACTIVITY_PAGE = 25;

// What is true when a filter finds nothing, and what would appear.
const EMPTY = {
  all: "Nothing has happened yet. Sprints starting and finishing, merges and engine changes appear here.",
  sprints: "No sprint has started or finished yet.",
  merges: "No task has been merged yet.",
  engine: "The engine has not been started, paused or stopped yet.",
};

/** The Activity tab: the project's milestones, newest first. */
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
        title="Activity"
        note="Milestones only. Each step is on the sprint page; agent output is on the task page."
      />
      <div className="filter-group" role="group" aria-label="Show">
        {MILESTONE_FILTERS.map((entry) => (
          <Button
            key={entry.key}
            variant="quiet"
            className="filter-group__option"
            aria-pressed={entry.key === filterKey}
            onClick={() => setFilterKey(entry.key)}
          >
            {entry.label}
          </Button>
        ))}
      </div>
      {list.error ? (
        <p className="notice notice--error" role="alert">
          {list.error}
        </p>
      ) : null}
      {placeholder ? <MilestoneTable caption="Milestones" placeholderRows={3} /> : null}
      {list.items && list.items.length === 0 ? (
        <p className="empty">{EMPTY[filterKey]}</p>
      ) : null}
      {list.items && list.items.length > 0 ? <MilestoneTable caption="Milestones" items={list.items} /> : null}
      {list.hasMore ? (
        <Button variant="quiet" className="list-more" disabled={list.loadingMore} onClick={() => list.loadMore()}>
          Earlier
        </Button>
      ) : null}
    </section>
  );
}
