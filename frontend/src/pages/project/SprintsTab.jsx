import React, { useEffect, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { listProjectSprints, moveSprint, SPRINT_STATUSES } from "../../api/sprints";
import { useDelayedFlag, useResource } from "../../api/useResource";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { StatusDot } from "../../ui/StatusDot";
import { Table } from "../../ui/Table";
import { formatDay, formatMoney } from "../../ui/format";
import { TaskCounts } from "../shared/TaskCounts";
import { FinishedSprints } from "./FinishedSprints";
import { NewSprintDialog } from "./NewSprintDialog";

// Design README: planned sprints 5, with a way to see the rest.
export const PLANNED_CAP = 5;

const COLUMNS = [
  {
    key: "state",
    header: "State",
    className: "queue__state",
    render: (sprint) =>
      sprint.status === SPRINT_STATUSES.active ? <StatusDot tone="running">Active</StatusDot> : <StatusDot>Planned</StatusDot>,
  },
  {
    key: "sprint",
    header: "Sprint",
    render: (sprint) => (
      <div className="cell-stack">
        <Link className="row-link row-link--strong" href={paths.sprint(sprint.id)}>
          {sprint.title}
        </Link>
      </div>
    ),
  },
  { key: "tasks", header: "Tasks", className: "queue__tasks", render: (sprint) => <TaskCounts counts={sprint.task_counts} /> },
  {
    key: "dates",
    header: "Dates",
    className: "queue__dates",
    render: (sprint) =>
      sprint.status === SPRINT_STATUSES.active && sprint.started_at ? (
        `since ${formatDay(sprint.started_at)}`
      ) : (
        <span className="quiet">not started</span>
      ),
  },
  {
    key: "spend",
    header: "Spend",
    numeric: true,
    render: (sprint) => <Mono>{formatMoney(sprint.totals?.total_cost_usd)}</Mono>,
  },
];

function EmptyQueue({ active, planned }) {
  if (active.length === 0 && planned.length === 0) {
    return <p className="empty">No sprint is active or planned. Foreman has nothing to run until a sprint is planned.</p>;
  }
  // An active sprint with nothing planned after it needs no line of its own:
  // the queue shows one sprint, and that is the whole truth.
  if (planned.length === 0 && active.length > 0) return null;
  if (active.length === 0) {
    return <p className="empty">No sprint is active. Start runs the first planned sprint.</p>;
  }
  return null;
}

/**
 * The Sprints tab: the queue only, the active sprint then the planned ones
 * in the order they will run; finished sprints are a closed line below.
 */
export function SprintsTab({ projectId, revision }) {
  const queue = useResource(["sprint-queue", projectId], (client, options) =>
    listProjectSprints(client, projectId, {
      statuses: [SPRINT_STATUSES.active, SPRINT_STATUSES.planned],
      order: "queue",
      ...options,
    }),
  );
  const placeholder = useDelayedFlag(queue.loading && !queue.data);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState(null);
  const [allPlanned, setAllPlanned] = useState(false);
  const reload = queue.reload;
  useEffect(() => {
    if (revision) reload();
  }, [revision, reload]);

  const sprints = queue.data?.items ?? [];
  const active = sprints.filter((sprint) => sprint.status === SPRINT_STATUSES.active);
  const planned = sprints.filter((sprint) => sprint.status === SPRINT_STATUSES.planned);
  const shownPlanned = allPlanned ? planned : planned.slice(0, PLANNED_CAP);

  const client = useApiClient();
  const [moving, setMoving] = useState(false);
  const [moveError, setMoveError] = useState(null);
  async function move(sprint, direction) {
    setMoving(true);
    setMoveError(null);
    setNotice(null);
    try {
      await moveSprint(client, sprint.id, direction);
      reload();
    } catch (error) {
      setMoveError(errorSentence(error));
    } finally {
      setMoving(false);
    }
  }
  // The order of planned sprints is the order they will run in, and a person
  // can change it. With one planned sprint there is nothing to reorder.
  const columns =
    planned.length > 1
      ? [
          ...COLUMNS,
          {
            key: "order",
            header: "Order",
            className: "queue__order",
            render: (sprint) => {
              const index = planned.findIndex((entry) => entry.id === sprint.id);
              if (index < 0) return null;
              return (
                <span className="queue__move">
                  <Button
                    variant="quiet"
                    inRow
                    icon="up"
                    className="button--icon"
                    disabled={moving || index === 0}
                    aria-label={`Move ${sprint.title} earlier`}
                    title="Run earlier"
                    onClick={() => move(sprint, "up")}
                  />
                  <Button
                    variant="quiet"
                    inRow
                    icon="down"
                    className="button--icon"
                    disabled={moving || index === planned.length - 1}
                    aria-label={`Move ${sprint.title} later`}
                    title="Run later"
                    onClick={() => move(sprint, "down")}
                  />
                </span>
              );
            },
          },
        ]
      : COLUMNS;

  return (
    <div className="sprints-tab">
      <section className="queue" aria-labelledby="queue-title">
        <SectionHeading
          id="queue-title"
          title="Active and planned"
          note="In the order they will run."
          actions={
            <Button icon="plus" onClick={() => setCreating(true)}>
              New sprint
            </Button>
          }
        />
        {notice ? (
          <p className="notice" role="status">
            {notice}
          </p>
        ) : null}
        {queue.error ? (
          <p className="notice notice--error" role="alert">
            {queue.error}
          </p>
        ) : null}
        {moveError ? (
          <p className="notice notice--error" role="alert">
            {moveError}
          </p>
        ) : null}
        {placeholder ? <Table caption="Sprint queue" columns={COLUMNS} placeholderRows={2} /> : null}
        {queue.data && sprints.length > 0 ? (
          <Table caption="Sprint queue" columns={columns} rows={[...active, ...shownPlanned]} />
        ) : null}
        {queue.data ? <EmptyQueue active={active} planned={planned} /> : null}
        {planned.length > PLANNED_CAP ? (
          <Button variant="quiet" className="list-more" onClick={() => setAllPlanned((value) => !value)}>
            {allPlanned ? "Show fewer" : `Show all ${planned.length} planned`}
          </Button>
        ) : null}
      </section>
      <FinishedSprints projectId={projectId} revision={revision} />
      <NewSprintDialog
        projectId={projectId}
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(sprint) => {
          setCreating(false);
          setNotice(`${sprint?.title ?? "The sprint"} is planned, last in the queue.`);
          queue.reload();
        }}
      />
    </div>
  );
}
