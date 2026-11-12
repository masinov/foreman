import React, { useCallback, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { getProjectWorkflow } from "../../api/projects";
import { getSprint, listSprintTasks, SPRINT_STATUSES } from "../../api/sprints";
import { approveTask } from "../../api/tasks";
import { useResource } from "../../api/useResource";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { SectionHeading } from "../../ui/SectionHeading";
import { plural } from "../../ui/format";
import { NewTaskDialog } from "../project/NewTaskDialog";
import { AddFromBacklogDialog } from "./AddFromBacklogDialog";
import { SprintActivity } from "./SprintActivity";
import { SprintHead } from "./SprintHead";
import { TaskBoard } from "./TaskBoard";
import { TaskList } from "./TaskList";

import "../../styles/lists.css";
import "../../styles/sprint.css";

export const VIEWS = { list: "list", board: "board" };

/** List | Board: two links, so each view has an address. */
function ViewToggle({ sprintId, view }) {
  const items = [
    { key: VIEWS.list, label: "List", href: paths.sprint(sprintId) },
    { key: VIEWS.board, label: "Board", href: paths.sprintBoard(sprintId) },
  ];
  return (
    <div className="view-toggle" role="group" aria-label="View">
      {items.map((item) => (
        <Link
          key={item.key}
          href={item.href}
          className={item.key === view ? "view-toggle__link view-toggle__link--current" : "view-toggle__link"}
          aria-current={item.key === view ? "true" : undefined}
        >
          {item.label}
        </Link>
      ))}
    </div>
  );
}

/**
 * The sprint page, the same for both views (docs/design/dashboard-v7/04 and
 * 07): title, state, summary, the tasks as a list or a board, and the steps
 * that finished. Only the tasks' presentation changes with `view`.
 */
export function SprintLayout({ sprintId, view }) {
  const client = useApiClient();
  const sprint = useResource(["sprint", sprintId], (apiClient, options) => getSprint(apiClient, sprintId, options));
  const tasks = useResource(["sprint-tasks", sprintId], (apiClient, options) => listSprintTasks(apiClient, sprintId, options));
  const projectId = sprint.data?.project_id ?? null;
  const workflow = useResource(
    ["workflow", projectId],
    (apiClient, options) => getProjectWorkflow(apiClient, projectId, options),
    { enabled: view === VIEWS.board && Boolean(projectId) },
  );
  const [revision, setRevision] = useState(0);
  const [adding, setAdding] = useState(false);
  const [writing, setWriting] = useState(false);
  const [approving, setApproving] = useState(false);
  const [notice, setNotice] = useState(null);

  const reloadSprint = sprint.reload;
  const reloadTasks = tasks.reload;
  const changed = useCallback(() => {
    reloadSprint();
    reloadTasks();
    setRevision((value) => value + 1);
  }, [reloadSprint, reloadTasks]);

  async function approve(task) {
    setApproving(true);
    setNotice(null);
    try {
      await approveTask(client, task.id);
      setNotice({ error: false, text: `Approved ${task.task_key || task.title}.` });
      changed();
    } catch (error) {
      setNotice({ error: true, text: errorSentence(error) });
    } finally {
      setApproving(false);
    }
  }

  if (!sprint.data) {
    return sprint.error ? (
      <div className="status-page">
        <h1 className="page-title">This sprint could not be shown</h1>
        <p className="status-page__text" role="alert">
          {sprint.error}{" "}
          <Link className="status-page__link" href={paths.workspace()}>
            Go to the workspace
          </Link>
        </p>
      </div>
    ) : null;
  }

  const current = sprint.data;
  const open = current.status === SPRINT_STATUSES.planned || current.status === SPRINT_STATUSES.active;
  const taskList = tasks.data ?? [];

  return (
    <div className="sprint">
      <SprintHead sprint={current} onChanged={changed} />
      <section className="sprint__tasks" aria-labelledby="sprint-tasks">
        <div className="sprint__tasks-head">
          <SectionHeading id="sprint-tasks" title="Tasks" />
          <ViewToggle sprintId={sprintId} view={view} />
          {view === VIEWS.board ? (
            <span className="quiet">
              One column per step of this project's workflow. The engine moves the cards; you decide where a column waits for you.
            </span>
          ) : null}
          {open ? (
            <div className="sprint__add">
              <Button onClick={() => setAdding(true)}>Add from backlog</Button>
              <Button icon="plus" onClick={() => setWriting(true)}>
                New task
              </Button>
            </div>
          ) : null}
        </div>
        {notice ? (
          <p className={notice.error ? "notice notice--error" : "notice"} role={notice.error ? "alert" : "status"}>
            {notice.text}
          </p>
        ) : null}
        {tasks.error ? (
          <p className="notice notice--error" role="alert">
            {tasks.error}
          </p>
        ) : null}
        {view === VIEWS.board && workflow.error ? (
          <p className="notice notice--error" role="alert">
            {workflow.error}
          </p>
        ) : null}
        {tasks.data && taskList.length === 0 ? (
          <p className="empty">
            No task is planned into this sprint. {open ? "Add accepted work from the backlog." : ""}
          </p>
        ) : null}
        {tasks.data && taskList.length > 0 && view === VIEWS.list ? (
          <TaskList tasks={taskList} busy={approving} onApprove={approve} />
        ) : null}
        {tasks.data && taskList.length > 0 && view === VIEWS.board && workflow.data ? (
          <TaskBoard tasks={taskList} workflow={workflow.data} busy={approving} onApprove={approve} />
        ) : null}
      </section>
      <SprintActivity sprintId={sprintId} tasks={taskList} revision={revision} />
      <NewTaskDialog
        projectId={projectId}
        sprint={current}
        open={writing}
        onClose={() => setWriting(false)}
        onFiled={(task) => {
          setWriting(false);
          setNotice({ error: false, text: `${task?.task_key || "The task"} added to ${current.title}.` });
          changed();
        }}
      />
      <AddFromBacklogDialog
        open={adding}
        projectId={projectId}
        sprint={current}
        onClose={() => setAdding(false)}
        onPlanned={(count) => {
          setAdding(false);
          setNotice({ error: false, text: `${plural(count, "task")} planned into ${current.title}.` });
          changed();
        }}
      />
    </div>
  );
}
