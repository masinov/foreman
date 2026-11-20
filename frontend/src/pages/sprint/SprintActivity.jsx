import React, { useCallback, useEffect, useRef, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { listSprintEvents, STEP_FINISHED } from "../../api/sprints";
import { ListPager } from "../../ui/ListPager";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { formatDayTime, humanize } from "../../ui/format";
import { outcomeTone, outcomeWord } from "../shared/activityWords";

// Design README: activity 25 at a time.
export const STEPS_PAGE = 25;

/**
 * Each finished step of each task in the sprint, newest first. What is waiting
 * is in the task table, not here. `revision` grows when the page changed, so
 * the newest steps are read again.
 */
export function SprintActivity({ sprintId, tasks, revision }) {
  const client = useApiClient();
  const [state, setState] = useState({ events: null, hasMore: false, error: null, loadingMore: false });
  const generation = useRef(0);

  useEffect(() => {
    generation.current += 1;
    const current = generation.current;
    listSprintEvents(client, sprintId, { types: [STEP_FINISHED], limit: STEPS_PAGE }).then(
      (page) => {
        if (generation.current === current) setState({ events: page.events, hasMore: page.hasMore, error: null, loadingMore: false });
      },
      (error) => {
        if (generation.current === current) setState((previous) => ({ ...previous, error: errorSentence(error) }));
      },
    );
  }, [client, sprintId, revision]);

  const loadEarlier = useCallback(async () => {
    const oldest = state.events?.[state.events.length - 1];
    if (!oldest) return;
    const current = generation.current;
    setState((previous) => ({ ...previous, loadingMore: true, error: null }));
    try {
      const page = await listSprintEvents(client, sprintId, { types: [STEP_FINISHED], limit: STEPS_PAGE, before: oldest.id });
      if (generation.current !== current) return;
      setState((previous) => ({
        events: [...previous.events, ...page.events],
        hasMore: page.hasMore,
        error: null,
        loadingMore: false,
      }));
    } catch (error) {
      if (generation.current === current) setState((previous) => ({ ...previous, loadingMore: false, error: errorSentence(error) }));
    }
  }, [client, sprintId, state.events]);

  // Back to the newest page; the steps let go of are asked for again by "Earlier steps".
  const showFewer = useCallback(() => {
    generation.current += 1;
    setState((previous) => ({ ...previous, events: previous.events.slice(0, STEPS_PAGE), hasMore: true, loadingMore: false }));
  }, []);

  const byId = new Map(tasks.map((task) => [task.id, task]));
  // A step leads to its run on the task's Activity, or to the task.
  const hrefOf = (event) => (event.run_id ? paths.taskRun(event.task_id, event.run_id) : paths.task(event.task_id));
  const columns = [
    { key: "when", header: "When", className: "steps__when", render: (event) => <Mono quiet>{formatDayTime(event.timestamp)}</Mono> },
    {
      key: "task",
      header: "Task",
      className: "steps__task",
      render: (event) => {
        const task = byId.get(event.task_id);
        return (
          <Link className="row-link" href={hrefOf(event)}>
            <Mono quiet>{task?.task_key ?? event.task_id}</Mono> {task?.title ?? ""}
          </Link>
        );
      },
    },
    { key: "step", header: "Step", className: "steps__step", render: (event) => humanize(event.payload?.step) },
    {
      key: "outcome",
      header: "Result",
      render: (event) => <span className={`tone-${outcomeTone(event.payload?.outcome)}`}>{outcomeWord(event.payload?.outcome)}</span>,
    },
  ];

  return (
    <section className="steps" aria-labelledby="sprint-activity">
      <SectionHeading
        id="sprint-activity"
        title="Activity"
      />
      {state.error ? (
        <p className="notice notice--error" role="alert">
          {state.error}
        </p>
      ) : null}
      {state.events && state.events.length === 0 ? <p className="empty">No step has finished in this sprint yet.</p> : null}
      {state.events && state.events.length > 0 ? (
        <Table caption="Finished steps" columns={columns} rows={state.events} rowHref={hrefOf} />
      ) : null}
      <ListPager
        more="Earlier steps"
        loading={state.loadingMore}
        hasMore={state.hasMore}
        expanded={(state.events?.length ?? 0) > STEPS_PAGE}
        onMore={loadEarlier}
        onFewer={showFewer}
      />
    </section>
  );
}
