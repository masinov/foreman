import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { runTaskNext } from "../../api/engine";
import { declineTask } from "../../api/backlog";
import { blockTask, deleteTask, reopenTask, stopTask } from "../../api/tasks";
import { ENGINE_STATES } from "../../api/workspace";
import { askManager, splitTaskRequest } from "../../app/managerRequests";
import { paths } from "../../app/paths";
import { useNavigate } from "../../app/router";
import { Button } from "../../ui/Button";
import { Menu } from "../../ui/Menu";
import { ReasonDialog } from "../shared/ReasonDialog";
import { useProjectEngine } from "../shared/useProjectEngine";
import { CloseTaskDialog } from "./CloseTaskDialog";

/**
 * What a person can do to a task besides answering its question, each with
 * what will happen in words. `done` is the sentence shown once the API
 * accepted it. Closing a task has its own dialog (`CloseTaskDialog`).
 */
export const TASK_ACTIONS = {
  run: {
    label: "Run next",
    title: "Run this task next",
    effect: "The project's engine is asked to run this task before any other. If no engine is running, one is started.",
    confirm: "Run next",
    doing: "Asking…",
    run: (client, task) => runTaskNext(client, task.project_id, task.id),
    done: "Requested. The task starts when the engine picks the request up.",
  },
  stop: {
    label: "Stop",
    title: "Stop this task",
    effect: "The engine stops the step it is running and blocks the task, saying you stopped it. Its branch and commits stay.",
    confirm: "Stop task",
    doing: "Stopping…",
    run: (client, task) => stopTask(client, task.id),
    done: "Stop requested. The task is blocked when the engine acts on it.",
  },
  reopen: {
    label: "Reopen",
    title: "Reopen this task",
    effect: "The task goes back to the queue and its workflow starts again from the first step. Its branch is kept, and what was merged stays merged.",
    confirm: "Reopen task",
    doing: "Reopening…",
    run: (client, task) => reopenTask(client, task.id),
    done: "Reopened. The task is back in the queue.",
  },
  close: { label: "Close" },
  block: {
    label: "Block",
    title: "Block this task",
    effect: "The task is parked before it starts. It waits in Needs you until someone unblocks it.",
    ask: "Why it is blocked",
    hint: "Shown on the task and in Needs you.",
    required: true,
    confirm: "Block task",
    doing: "Blocking…",
    run: (client, task, text) => blockTask(client, task.id, text),
    done: "Blocked.",
  },
  split: {
    label: "Split into smaller tasks",
    title: "Split this task",
    effect:
      "The manager reads the task and the code it touches, and proposes smaller tasks that together do what this one asks, with this one cancelled. You are taken to the sprint, where the proposal appears in the manager's side bar. Who confirms it is this project's “Approve plans” setting.",
    confirm: "Ask the manager",
    doing: "Asking…",
    run: async (client, task) => askManager(splitTaskRequest(task)),
    done: "Asked. The proposal appears in the manager's side bar.",
  },
  decline: {
    label: "Decline",
    title: "Decline this task",
    ask: "Why it is declined",
    hint: "Optional. Kept with the task in the backlog.",
    required: false,
    effect: "The task stays in the backlog, marked declined. Nothing runs it.",
    confirm: "Decline task",
    doing: "Declining…",
    run: (client, task, text) => declineTask(client, task.id, { reason: text }),
    done: "Declined.",
  },
  delete: {
    label: "Delete",
    title: "Delete this task",
    effect: "The task, its runs, its history and its worktree are deleted. This cannot be undone.",
    confirm: "Delete task",
    doing: "Deleting…",
    run: (client, task) => deleteTask(client, task.id),
    done: "Deleted.",
  },
};

const OPEN = new Set(["todo", "in_progress", "blocked"]);
const CLOSED = new Set(["done", "cancelled"]);

/**
 * The actions that exist for a task in its state: `{ buttons, more }`.
 *
 * `buttons` are in plain sight beside the title. They are what depends on
 * the task's state (Run next, Stop, Reopen) and the one thing that is the
 * same in every open state, ending the task by hand (Close). `more` is what
 * is rare: Block, Split, Delete. Answering the task's question (approve,
 * unblock, send back) is the decision's, not listed here. Block exists only
 * for a task that has not started: a started one has Stop and Close.
 *
 * `engine` is the project's engine, null until it is known. Stop is a
 * request to a running engine, so it exists only while one is running this
 * task, and while it does the task can be neither closed nor deleted (the
 * API refuses both until the step stops). Until the engine is known, a task
 * in progress shows neither Run next nor Stop.
 */
export function actionsFor(task, engine) {
  const planned = !task.in_backlog;
  const inProgress = task.status === "in_progress";
  const engineOnIt = inProgress && engine?.state === ENGINE_STATES.running && engine.task_id === task.id;
  const engineKnown = !inProgress || Boolean(engine);
  const buttons = [];
  const more = [];
  if (planned && engineKnown && (task.status === "todo" || (inProgress && !engineOnIt))) buttons.push("run");
  if (engineOnIt) buttons.push("stop");
  if (CLOSED.has(task.status)) buttons.push("reopen");
  if (planned && engineKnown && OPEN.has(task.status) && !engineOnIt) buttons.push("close");
  if (planned && task.status === "todo") more.push("block");
  if (task.status === "todo" || task.status === "triage") more.push("split");
  // In the backlog, "we won't do this" is Decline, the one way (owner,
  // 2026-11-18): a filed task has it in its decision, an accepted one here.
  if (!planned && task.status === "todo") more.push("decline");
  if (engineKnown && !engineOnIt) more.push("delete");
  return { buttons, more };
}

/**
 * The task's actions beside its title: the buttons, the More menu and the
 * dialog that confirms the chosen one. `onDone(name, sentence)` runs once the
 * API accepted it.
 */
export function TaskActions({ task, onDone }) {
  const client = useApiClient();
  const engine = useProjectEngine(task.project_id);
  const navigate = useNavigate();
  const [chosen, setChosen] = useState(null);
  const action = chosen && chosen !== "close" ? TASK_ACTIONS[chosen] : null;
  const { buttons, more } = actionsFor(task, engine);

  return (
    <>
      {buttons.map((name) =>
        // A request the engine has not started yet is asked once: its sign
        // is a disabled "Runs next" until the engine starts the task.
        name === "run" && task.run_next ? (
          <Button key={name} disabled title="The engine runs this task next">
            Runs next
          </Button>
        ) : (
          <Button key={name} onClick={() => setChosen(name)}>
            {TASK_ACTIONS[name].label}
          </Button>
        ),
      )}
      {more.length ? (
        <Menu
          label="Task actions"
          trigger="More"
          triggerClassName="menu__trigger--button"
          items={more.map((name) => ({
            key: name,
            label: TASK_ACTIONS[name].label,
            onSelect: () => setChosen(name),
          }))}
        />
      ) : null}
      <ReasonDialog
        open={Boolean(action)}
        title={action?.title}
        effect={action?.effect}
        ask={action?.ask}
        hint={action?.hint}
        required={action?.required}
        confirm={action?.confirm}
        doing={action?.doing}
        run={(text) => action.run(client, task, text)}
        onClose={() => setChosen(null)}
        onDone={() => {
          const name = chosen;
          setChosen(null);
          if (name === "split") {
            // The manager works at the level of the sprint, so that is where its answer is.
            navigate(task.in_backlog ? paths.projectBacklog(task.project_id) : paths.sprint(task.sprint_id));
            return;
          }
          onDone(name, TASK_ACTIONS[name].done);
        }}
      />
      <CloseTaskDialog
        open={chosen === "close"}
        task={task}
        onClose={() => setChosen(null)}
        onDone={(sentence) => {
          setChosen(null);
          onDone("close", sentence);
        }}
      />
    </>
  );
}
