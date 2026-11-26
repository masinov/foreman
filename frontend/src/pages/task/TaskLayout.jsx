import React, { useCallback, useEffect, useRef, useState } from "react";

import { getTask, getTaskChanges, getTaskChecks } from "../../api/tasks";
import { useResource } from "../../api/useResource";
import { paths } from "../../app/paths";
import { onProjectEvent } from "../../app/projectEvents";
import { Link, useNavigate } from "../../app/router";
import { Tabs } from "../../ui/Tabs";
import { useToast } from "../../ui/Toast";
import { BacklogDecision } from "./BacklogDecision";
import { Decision } from "./Decision";
import { useSeenGateVersion } from "./seenVersion";
import { TaskHead } from "./TaskHead";

import "../../styles/task.css";

// How long the page waits after the last event about this task before it
// reads the task again, so a burst of events is one reload.
export const STREAM_SETTLE_MS = 300;

/**
 * Follow the project's stream (the one the app already holds open) while a
 * step of this task runs, and call `refresh` once the events about it settle.
 */
function useRefreshWhileRunning(task, refresh) {
  const timer = useRef(null);
  const taskId = task?.id;
  const running = task?.status === "in_progress" && Boolean(task.sprint_id) && !task.in_backlog;
  useEffect(() => {
    if (!running) return undefined;
    return onProjectEvent((event) => {
      if (event.task_id !== taskId) return;
      clearTimeout(timer.current);
      timer.current = setTimeout(refresh, STREAM_SETTLE_MS);
    });
  }, [running, taskId, refresh]);
  useEffect(() => () => clearTimeout(timer.current), []);
}

/**
 * The task page, the same on its four tabs (docs/design/dashboard-v7/05, 12,
 * 13, 14): the head, the decision when the task waits for a person, and the
 * tabs. `children({ task, checks, changes, revision, changed, sawDiff })`
 * renders the current tab; `revision` grows whenever the page read the task
 * again; `sawDiff(sha)` says the person opened the diff read at that head.
 */
export function TaskLayout({ taskId, children }) {
  const navigate = useNavigate();
  const task = useResource(["task", taskId], (client, options) => getTask(client, taskId, options));
  const checks = useResource(["task-checks", taskId], (client, options) => getTaskChecks(client, taskId, options));
  const changes = useResource(["task-changes", taskId], (client, options) => getTaskChanges(client, taskId, options));
  const [revision, setRevision] = useState(0);
  const { show } = useToast();

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
      if (sentence) show(sentence);
      refresh();
    },
    [refresh, show],
  );

  useRefreshWhileRunning(task.data, refresh);
  // The version a person at a gate is looking at, kept across reloads.
  const seen = useSeenGateVersion(task.data);

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
      {current.in_backlog && (current.status === "triage" || current.status === "todo") ? (
        <BacklogDecision task={current} onDecided={changed} />
      ) : (
        <Decision task={current} checks={checks.data} seen={seen} onDecided={changed} />
      )}
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
          {children({ task: current, checks, changes, revision, changed, sawDiff: seen.sawDiff })}
        </div>
      </div>
    </div>
  );
}
