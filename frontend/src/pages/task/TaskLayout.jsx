import React, { useCallback, useEffect, useRef, useState } from "react";

import { segment } from "../../api/client";
import { getTask, getTaskChanges, getTaskChecks } from "../../api/tasks";
import { useEventStream } from "../../api/useEventStream";
import { useResource } from "../../api/useResource";
import { paths } from "../../app/paths";
import { Link, useNavigate } from "../../app/router";
import { Tabs } from "../../ui/Tabs";
import { Decision } from "./Decision";
import { changeSize, TaskHead } from "./TaskHead";

import "../../styles/task.css";

// How long the page waits after the last event about this task before it
// reads the task again, so a burst of events is one reload.
export const STREAM_SETTLE_MS = 300;

/**
 * Follow the sprint's stream while a step of this task runs, and call
 * `refresh` once the events about it settle.
 */
function useRefreshWhileRunning(task, refresh) {
  const timer = useRef(null);
  const running = task?.status === "in_progress" && Boolean(task.sprint_id) && !task.in_backlog;
  useEventStream(running ? `/sprints/${segment(task.sprint_id)}/stream` : null, (event) => {
    if (event.task_id !== task.id) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(refresh, STREAM_SETTLE_MS);
  });
  useEffect(() => () => clearTimeout(timer.current), []);
}

function Notice({ notice }) {
  if (!notice) return null;
  return (
    <p className={notice.error ? "notice notice--error" : "notice"} role={notice.error ? "alert" : "status"}>
      {notice.text}
    </p>
  );
}

/**
 * The task page, the same on its four tabs (docs/design/dashboard-v7/05, 12,
 * 13, 14): the head, the decision when the task waits for a person, and the
 * tabs. `children({ task, checks, changes, revision, changed })` renders the
 * current tab; `revision` grows whenever the page read the task again.
 */
export function TaskLayout({ taskId, children }) {
  const navigate = useNavigate();
  const task = useResource(["task", taskId], (client, options) => getTask(client, taskId, options));
  const checks = useResource(["task-checks", taskId], (client, options) => getTaskChecks(client, taskId, options));
  const changes = useResource(["task-changes", taskId], (client, options) => getTaskChanges(client, taskId, options));
  const [revision, setRevision] = useState(0);
  const [notice, setNotice] = useState(null);

  const reloadTask = task.reload;
  const reloadChecks = checks.reload;
  const reloadChanges = changes.reload;
  const refresh = useCallback(() => {
    reloadTask();
    reloadChecks();
    reloadChanges();
    setRevision((value) => value + 1);
  }, [reloadTask, reloadChecks, reloadChanges]);

  const changed = useCallback(
    (sentence) => {
      setNotice(sentence ? { error: false, text: sentence } : null);
      refresh();
    },
    [refresh],
  );

  useRefreshWhileRunning(task.data, refresh);

  if (!task.data) {
    return task.error ? (
      <div className="status-page">
        <h1 className="page-title">This task could not be shown</h1>
        <p className="status-page__text" role="alert">
          {task.error}{" "}
          <Link className="status-page__link" href={paths.workspace()}>
            Go to the workspace
          </Link>
        </p>
      </div>
    ) : null;
  }

  const current = task.data;

  function deleted() {
    navigate(current.in_backlog ? paths.projectBacklog(current.project_id) : paths.sprint(current.sprint_id));
  }

  return (
    <div className="task">
      <TaskHead task={current} changes={changes.data} checks={checks.data} onChanged={changed} onDeleted={deleted} />
      {task.error ? (
        <p className="notice notice--error" role="alert">
          {task.error}
        </p>
      ) : null}
      <Notice notice={notice} />
      <Decision task={current} checks={checks.data} onDecided={changed} />
      <div className="task__tabs">
        <Tabs
          label="Task"
          items={[
            { href: paths.task(taskId), label: "Overview" },
            {
              href: paths.taskChanges(taskId),
              label: "Changes",
            },
            { href: paths.taskChecks(taskId), label: "Checks" },
            { href: paths.taskActivity(taskId), label: "Activity" },
          ]}
        />
        <div className="task__tab">
          {children({ task: current, checks, changes, revision, changed })}
        </div>
      </div>
    </div>
  );
}
