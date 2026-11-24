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
import { ListPager } from "../../ui/ListPager";
import { Field } from "../../ui/Field";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { formatDay, plural } from "../../ui/format";
import { useNotice } from "../../ui/Toast";
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
  return (
    <p className="notice notice--error" role="alert">
      {notice.text}
    </p>
  );
}

/**
 * The Backlog tab (ADR-0021, ADR-0028): work that is in no sprint. A task is
 * planned into a sprint or declined.
 *
 * Where the project lets Foreman start backlog work on its own, what an agent
 * or another system filed and no person has accepted is listed apart as
 * requests: accepting one lets Foreman start it. Where a person plans
 * everything there is nothing for acceptance to decide, so there is one list
 * and no Accept.
 *
 * Paging and the filter are the server's; the list is reloaded after every
 * change through `onChanged`, which also re-reads the count in the project head.
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

  const [notice, setNotice] = useNotice();
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [target, setTarget] = useState(NEW_SPRINT);
  const [filing, setFiling] = useState(false);
  const [namingSprint, setNamingSprint] = useState(false);

  const items = useMemo(() => list.items ?? [], [list.items]);
  const filed = items.filter((task) => task.state === BACKLOG_STATES.filed);
  const accepted = items.filter((task) => task.state === BACKLOG_STATES.accepted);
  const counts = list.meta?.counts ?? {};
  const foreman = list.meta?.foreman ?? { starts: false, limit: 0, started: null, ready: 0 };
  const planTargets = sprints.data?.items ?? [];
  // Requests are their own list only where accepting one has an effect.
  const requests = foreman.starts ? filed : [];
  const work = foreman.starts ? accepted : items;
  const workCount = foreman.starts ? (counts.accepted ?? 0) : (counts.filed ?? 0) + (counts.accepted ?? 0);

  // Only rows still in the list count as selected: a reload can remove them.
  const chosen = useMemo(() => items.filter((task) => selected.has(task.id)), [items, selected]);
  const allChosen = work.length > 0 && work.every((task) => selected.has(task.id));
  const selectAll = useRef(null);
  useEffect(() => {
    if (selectAll.current) selectAll.current.indeterminate = work.some((task) => selected.has(task.id)) && !allChosen;
  }, [work, selected, allChosen]);

  function toggle(task) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(task.id)) next.delete(task.id);
      else next.add(task.id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((previous) => {
      const next = new Set(previous);
      for (const task of work) {
        if (allChosen) next.delete(task.id);
        else next.add(task.id);
      }
      return next;
    });
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

  const pick = (task) => (
    <input
      type="checkbox"
      className="checkbox"
      aria-label={`Select: ${task.title}`}
      checked={selected.has(task.id)}
      onChange={() => toggle(task)}
    />
  );
  const by = (task) => {
    const when = formatDay(task.created_at);
    return (
      <span className="quiet">
        {filedBy(task)}
        {when ? `, ${when}` : ""}
      </span>
    );
  };
  const decline = (task) => (
    <Button
      inRow
      disabled={busy}
      aria-label={`Decline ${task.title}`}
      onClick={() => decide(task, declineTask, (done) => `Declined ${done.title}.`)}
    >
      Decline
    </Button>
  );
  const type = (task) => <span className="secondary">{task.task_type}</span>;

  const requestColumns = [
    { key: "select", header: <span className="visually-hidden">Select</span>, className: "backlog__select", render: pick },
    { key: "title", header: "Request", render: (task) => <TaskLink task={task} /> },
    { key: "type", header: "Type", className: "backlog__type", render: type },
    { key: "by", header: "Filed by", className: "backlog__by", render: by },
    {
      key: "action",
      header: "Action",
      className: "backlog__actions",
      render: (task) => (
        <>
          {decline(task)}
          <Button
            variant="gold-outline"
            inRow
            disabled={busy}
            aria-label={`Accept ${task.title}`}
            onClick={() => decide(task, acceptTask, (done) => `Accepted ${done.title}.`)}
          >
            Accept
          </Button>
        </>
      ),
    },
  ];

  const workColumns = [
    {
      key: "select",
      header: (
        <input
          ref={selectAll}
          type="checkbox"
          className="checkbox"
          aria-label="Select every task in the backlog"
          checked={allChosen}
          disabled={work.length === 0}
          onChange={toggleAll}
        />
      ),
      className: "backlog__select",
      render: pick,
    },
    { key: "title", header: "Task", render: (task) => <TaskLink task={task} /> },
    { key: "type", header: "Type", className: "backlog__type", render: type },
    { key: "by", header: "Filed by", className: "backlog__by", render: by },
    { key: "action", header: "Action", className: "backlog__actions", render: decline },
  ];

  const planInto = (
    <div className="backlog__plan">
      <label className="backlog__plan-label" htmlFor="backlog-plan-into">
        Plan selected into
      </label>
      <select id="backlog-plan-into" className="field__input" value={target} onChange={(event) => setTarget(event.target.value)}>
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
  );
  // What Foreman has done with this backlog, where it starts work itself.
  const foremanNote = !foreman.starts
    ? undefined
    : foreman.started === null
      ? "Foreman starts these itself, when a sprint is active"
      : `Foreman has started ${foreman.started} of ${foreman.limit} this sprint`;

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
        <Button icon="plus" onClick={() => setFiling(true)}>
          New task
        </Button>
      </div>
      <Notice notice={notice} />
      {list.error ? (
        <p className="notice notice--error" role="alert">
          {list.error}
        </p>
      ) : null}
      {placeholder ? <Table caption="Backlog" columns={workColumns} placeholderRows={3} /> : null}
      {sprints.error ? (
        <p className="notice notice--error" role="alert">
          {sprints.error}
        </p>
      ) : null}

      {list.items && foreman.starts && (requests.length > 0 || (counts.filed ?? 0) > 0) ? (
        <section className="backlog__group" aria-labelledby="backlog-requests">
          <SectionHeading id="backlog-requests" title="Requests" count={counts.filed ?? 0} attention />
          {requests.length > 0 ? (
            <Table caption="Requests" columns={requestColumns} rows={requests} />
          ) : (
            <p className="empty">No request matches “{q}”.</p>
          )}
        </section>
      ) : null}

      {list.items ? (
        <section className="backlog__group" aria-labelledby="backlog-work">
          <SectionHeading id="backlog-work" title="Backlog" count={workCount} note={foremanNote} actions={planInto} />
          {work.length > 0 ? (
            <Table caption="Backlog" columns={workColumns} rows={work} />
          ) : (
            <p className="empty">{q ? `Nothing in the backlog matches “${q}”.` : "The backlog is empty."}</p>
          )}
        </section>
      ) : null}

      <ListPager
        more="Show more"
        loading={list.loadingMore}
        hasMore={list.hasMore}
        expanded={list.expanded}
        onMore={() => list.loadMore()}
        onFewer={list.collapse}
      />

      <NewTaskDialog
        projectId={projectId}
        open={filing}
        onClose={() => setFiling(false)}
        onFiled={(task) => {
          setFiling(false);
          setNotice({ error: false, text: `Filed ${task?.title ?? "the task"}.` });
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
