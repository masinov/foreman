import React, { useEffect, useMemo, useRef, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { acceptTask, BACKLOG_STATES, declineTask, listBacklog, planBacklog } from "../../api/backlog";
import { errorSentence } from "../../api/client";
import { listProjectSprints, SPRINT_STATUSES } from "../../api/sprints";
import { usePagedList } from "../../api/usePagedList";
import { useDelayedFlag, useResource } from "../../api/useResource";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { formatDay, plural } from "../../ui/format";
import { NewTaskDialog } from "./NewTaskDialog";
import { PlanNewSprintDialog } from "./PlanNewSprintDialog";

// Design README: the backlog shows 25 rows at a time.
export const BACKLOG_PAGE = 25;

const NEW_SPRINT = "new";

/** Who filed a task, in words: a person, an agent role, or another system. */
function filedBy(task) {
  if (task.carried_from) return `carried from ${task.carried_from.title}`;
  const source = task.source;
  if (source && (source.reporter || source.system)) {
    return [source.reporter, source.system ? `via ${source.system}` : null].filter(Boolean).join(" ");
  }
  return task.created_by || "unknown";
}

function TaskLink({ task }) {
  return (
    <Link className="row-link" href={paths.task(task.id)}>
      {task.title}
    </Link>
  );
}

function Notice({ notice }) {
  if (!notice) return null;
  return notice.error ? (
    <p className="notice notice--error" role="alert">
      {notice.text}
    </p>
  ) : (
    <p className="notice" role="status">
      {notice.text}
    </p>
  );
}

function triageSentence(triage) {
  return triage === "auto"
    ? "Cannot be planned until accepted. This project accepts filed work on its own."
    : "Cannot be planned until accepted. This project sends these to a person.";
}

/**
 * The Backlog tab (ADR-0021): work that is filed and waiting to be accepted,
 * and work that is accepted and waiting to be planned into a sprint. Paging
 * and the filter are the server's; the list is reloaded after every change
 * through `onChanged`, which also re-reads the tab count in the project head.
 */
export function BacklogTab({ projectId, revision, onChanged }) {
  const client = useApiClient();
  const [filter, setFilter] = useState("");
  const q = filter.trim();
  const list = usePagedList(
    ["backlog", projectId, q],
    (apiClient, options) => listBacklog(apiClient, projectId, { q, ...options }),
    { pageSize: BACKLOG_PAGE },
  );
  const sprints = useResource(["backlog-sprints", projectId], (apiClient, options) =>
    listProjectSprints(apiClient, projectId, {
      statuses: [SPRINT_STATUSES.active, SPRINT_STATUSES.planned],
      order: "queue",
      ...options,
    }),
  );
  const placeholder = useDelayedFlag(list.loading && !list.items);
  const reloadList = list.reload;
  const reloadSprints = sprints.reload;
  useEffect(() => {
    if (revision) {
      reloadList();
      reloadSprints();
    }
  }, [revision, reloadList, reloadSprints]);

  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [target, setTarget] = useState(NEW_SPRINT);
  const [filing, setFiling] = useState(false);
  const [namingSprint, setNamingSprint] = useState(false);

  const items = list.items ?? [];
  const filed = items.filter((task) => task.state === BACKLOG_STATES.filed);
  const accepted = items.filter((task) => task.state === BACKLOG_STATES.accepted);
  const counts = list.meta?.counts ?? {};
  const triage = list.meta?.triage ?? "human";
  const planTargets = sprints.data?.items ?? [];

  // Only rows still in the list count as selected: a reload can remove them.
  const chosen = useMemo(() => accepted.filter((task) => selected.has(task.id)), [accepted, selected]);
  const allChosen = accepted.length > 0 && chosen.length === accepted.length;
  const selectAll = useRef(null);
  useEffect(() => {
    if (selectAll.current) selectAll.current.indeterminate = chosen.length > 0 && !allChosen;
  }, [chosen.length, allChosen]);

  function toggle(task) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(task.id)) next.delete(task.id);
      else next.add(task.id);
      return next;
    });
  }

  function toggleAll() {
    setSelected(allChosen ? new Set() : new Set(accepted.map((task) => task.id)));
  }

  function changed() {
    onChanged?.();
  }

  async function decide(task, action, done) {
    setBusy(true);
    setNotice(null);
    try {
      await action(client, task.id);
      setNotice({ error: false, text: done(task) });
      changed();
    } catch (error) {
      setNotice({ error: true, text: errorSentence(error) });
    } finally {
      setBusy(false);
    }
  }

  /** Plan the chosen tasks; resolves to a sentence when the API refuses. */
  async function plan(destination, sprintTitle) {
    const taskIds = chosen.map((task) => task.id);
    setBusy(true);
    setNotice(null);
    try {
      await planBacklog(client, projectId, { taskIds, ...destination });
      setNotice({ error: false, text: `${plural(taskIds.length, "task")} planned into ${sprintTitle}.` });
      setSelected(new Set());
      setNamingSprint(false);
      changed();
      return null;
    } catch (error) {
      return errorSentence(error);
    } finally {
      setBusy(false);
    }
  }

  async function planSelected() {
    if (chosen.length === 0) return;
    if (target === NEW_SPRINT) {
      setNamingSprint(true);
      return;
    }
    const sprint = planTargets.find((entry) => entry.id === target);
    const refusal = await plan({ sprintId: target }, sprint?.title ?? "the sprint");
    if (refusal) setNotice({ error: true, text: refusal });
  }

  const filedColumns = [
    { key: "title", header: "Task", render: (task) => <TaskLink task={task} /> },
    {
      key: "by",
      header: "Filed by",
      className: "backlog__by",
      render: (task) => {
        const when = formatDay(task.created_at);
        return (
          <span className="quiet">
            {filedBy(task)}
            {when ? `, ${when}` : ""}
          </span>
        );
      },
    },
    {
      key: "action",
      header: "Action",
      className: "backlog__actions",
      render: (task) => (
        <>
          <Button
            inRow
            disabled={busy}
            aria-label={`Decline ${task.title}`}
            onClick={() => decide(task, declineTask, (done) => `Declined ${done.title}.`)}
          >
            Decline
          </Button>
          <Button
            variant="gold-outline"
            inRow
            disabled={busy}
            aria-label={`Accept ${task.title}`}
            onClick={() => decide(task, acceptTask, (done) => `Accepted ${done.title}. It is waiting to be planned.`)}
          >
            Accept
          </Button>
        </>
      ),
    },
  ];

  const acceptedColumns = [
    {
      key: "select",
      header: (
        <input
          ref={selectAll}
          type="checkbox"
          className="checkbox"
          aria-label="Select all accepted tasks"
          checked={allChosen}
          disabled={accepted.length === 0}
          onChange={toggleAll}
        />
      ),
      className: "backlog__select",
      render: (task) => (
        <input
          type="checkbox"
          className="checkbox"
          aria-label={`Select: ${task.title}`}
          checked={selected.has(task.id)}
          onChange={() => toggle(task)}
        />
      ),
    },
    { key: "title", header: "Task", render: (task) => <TaskLink task={task} /> },
    { key: "type", header: "Type", className: "backlog__type", render: (task) => <span className="secondary">{task.task_type}</span> },
    { key: "by", header: "Filed by", className: "backlog__by", render: (task) => <span className="quiet">{filedBy(task)}</span> },
  ];

  return (
    <div className="backlog">
      <div className="backlog__bar">
        <Field
          label="Filter the backlog"
          hideLabel
          type="search"
          placeholder="Filter the backlog"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          className="backlog__filter"
        />
        <Button onClick={() => setFiling(true)}>New task</Button>
      </div>
      <Notice notice={notice} />
      {list.error ? (
        <p className="notice notice--error" role="alert">
          {list.error}
        </p>
      ) : null}
      {placeholder ? <Table caption="Backlog" columns={acceptedColumns} placeholderRows={3} /> : null}

      {list.items ? (
        <section className="backlog__group" aria-labelledby="backlog-filed">
          <SectionHeading
            id="backlog-filed"
            title="Filed, not accepted"
            count={counts.filed ?? 0}
            note={triageSentence(triage)}
          />
          {filed.length > 0 ? (
            <Table caption="Filed, not accepted" columns={filedColumns} rows={filed} hideHeader />
          ) : (
            <p className="empty">
              {q
                ? `No filed work matches “${q}”.`
                : "Nothing is filed. Work that other systems or agents file, and tasks you add, wait here to be accepted."}
            </p>
          )}
        </section>
      ) : null}

      {list.items ? (
        <section className="backlog__group" aria-labelledby="backlog-accepted">
          <SectionHeading
            id="backlog-accepted"
            title="Accepted, not planned"
            count={counts.accepted ?? 0}
            actions={
              <div className="backlog__plan">
                <label className="backlog__plan-label" htmlFor="backlog-plan-into">
                  Plan selected into
                </label>
                <select
                  id="backlog-plan-into"
                  className="field__input"
                  value={target}
                  onChange={(event) => setTarget(event.target.value)}
                >
                  <option value={NEW_SPRINT}>A new sprint</option>
                  {planTargets.map((sprint) => (
                    <option key={sprint.id} value={sprint.id}>
                      {sprint.title} ({sprint.status})
                    </option>
                  ))}
                </select>
                <Button disabled={chosen.length === 0 || busy} onClick={planSelected}>
                  Plan
                </Button>
              </div>
            }
          />
          {sprints.error ? (
            <p className="notice notice--error" role="alert">
              {sprints.error}
            </p>
          ) : null}
          {accepted.length > 0 ? (
            <Table caption="Accepted, not planned" columns={acceptedColumns} rows={accepted} />
          ) : (
            <p className="empty">
              {q
                ? `No accepted work matches “${q}”.`
                : "Nothing is waiting to be planned. Accepted work appears here until it is planned into a sprint."}
            </p>
          )}
        </section>
      ) : null}

      {list.hasMore ? (
        <Button variant="quiet" className="list-more" disabled={list.loadingMore} onClick={() => list.loadMore()}>
          Show more
        </Button>
      ) : null}

      <NewTaskDialog
        projectId={projectId}
        open={filing}
        onClose={() => setFiling(false)}
        onFiled={(task) => {
          setFiling(false);
          setNotice({
            error: false,
            text:
              task?.status === "todo"
                ? `Filed ${task.title}. This project accepted it, so it is waiting to be planned.`
                : `Filed ${task?.title ?? "the task"}. It waits to be accepted.`,
          });
          changed();
        }}
      />
      <PlanNewSprintDialog
        open={namingSprint}
        taskCount={chosen.length}
        onClose={() => setNamingSprint(false)}
        onSubmit={({ title, goal }) => plan({ newSprint: { title, goal } }, title)}
      />
    </div>
  );
}
