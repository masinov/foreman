import React, { useCallback, useEffect, useRef, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { listSprintEvents, STEP_FINISHED } from "../../api/sprints";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { formatDayTime, humanize } from "../../ui/format";

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

  const keys = new Map(tasks.map((task) => [task.id, task.task_key || task.title]));
  const columns = [
    { key: "when", header: "When", className: "steps__when", render: (event) => <Mono quiet>{formatDayTime(event.timestamp)}</Mono> },
    { key: "task", header: "Task", className: "steps__task", render: (event) => <Mono quiet>{keys.get(event.task_id) ?? event.task_id}</Mono> },
    { key: "step", header: "Step", className: "steps__step", render: (event) => <span className="secondary">{humanize(event.payload?.step)}</span> },
    { key: "outcome", header: "Result", render: (event) => humanize(event.payload?.outcome) },
  ];

  return (
    <section className="steps" aria-labelledby="sprint-activity">
      <SectionHeading
        id="sprint-activity"
        title="Activity"
        note="Steps that finished, newest first. What is waiting is in the table above; agent output is on the task page."
      />
      {state.error ? (
        <p className="notice notice--error" role="alert">
          {state.error}
        </p>
      ) : null}
      {state.events && state.events.length === 0 ? <p className="empty">No step has finished in this sprint yet.</p> : null}
      {state.events && state.events.length > 0 ? (
        <Table caption="Finished steps" columns={columns} rows={state.events} hideHeader />
      ) : null}
      {state.hasMore ? (
        <Button variant="quiet" className="list-more" disabled={state.loadingMore} onClick={loadEarlier}>
          Earlier steps
        </Button>
      ) : null}
    </section>
  );
}
