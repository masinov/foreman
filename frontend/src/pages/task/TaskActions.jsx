import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { runTaskNext } from "../../api/engine";
import { blockTask, cancelTask, completeTask, deleteTask, reopenTask, stopTask, unblockTask } from "../../api/tasks";
import { ENGINE_STATES } from "../../api/workspace";
import { Menu } from "../../ui/Menu";
import { ReasonDialog } from "../shared/ReasonDialog";
import { useProjectEngine } from "../shared/useProjectEngine";

/**
 * What a person can do to a task from the More menu, each with what will
 * happen in words. `done` is the sentence shown once the API accepted it.
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
  block: {
    label: "Block",
    title: "Block this task",
    effect: "The task is parked. If a step is running, the engine stops when that step ends. It waits in Needs you until someone unblocks it.",
    ask: "Why it is blocked",
    hint: "Shown on the task and in Needs you.",
    required: true,
    confirm: "Block task",
    doing: "Blocking…",
    run: (client, task, text) => blockTask(client, task.id, text),
    done: "Blocked.",
  },
  unblock: {
    label: "Unblock",
    title: "Unblock this task",
    effect: "The task goes back to the queue and its workflow starts again from the first step. Its branch is kept.",
    ask: "Guidance for the agent",
    hint: "Optional. The next agent step reads it.",
    required: false,
    confirm: "Unblock task",
    doing: "Unblocking…",
    run: (client, task, text) => unblockTask(client, task.id, text),
    done: "Unblocked. The task is back in the queue.",
  },
  complete: {
    label: "Mark done",
    title: "Mark this task done",
    effect: "The task is marked done on your word. None of its remaining steps run and Foreman checks nothing: nothing is tested, reviewed or merged by this. Its branch and working copy stay as they are. It can be reopened.",
    ask: "Why it is done",
    hint: "For example where it was merged. Shown on the task.",
    required: true,
    confirm: "Mark done",
    doing: "Marking done…",
    run: (client, task, text) => completeTask(client, task.id, text),
    done: "Marked done.",
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
  cancel: {
    label: "Cancel",
    title: "Cancel this task",
    effect: "The task is marked cancelled and its worktree is removed. Its history stays. Nothing runs it again unless it is reopened.",
    confirm: "Cancel task",
    doing: "Cancelling…",
    run: (client, task) => cancelTask(client, task.id),
    done: "Cancelled.",
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
 * The actions that exist for a task in its state, in menu order. `engine` is
 * the project's engine: Stop is a request to a running engine, so it exists
 * only while one is running this task; a task left part-way with no engine
 * on it can be asked to run next instead.
 */
export function actionsFor(task, engine = null) {
  const planned = !task.in_backlog;
  const engineOnIt = engine?.state === ENGINE_STATES.running && engine.task_id === task.id;
  const names = [];
  if (planned && (task.status === "todo" || (task.status === "in_progress" && !engineOnIt))) names.push("run");
  if (task.status === "in_progress" && engineOnIt) names.push("stop");
  if (planned && (task.status === "todo" || task.status === "in_progress")) names.push("block");
  if (task.status === "blocked" && task.blocked_kind !== "gate") names.push("unblock");
  if (planned && OPEN.has(task.status)) names.push("complete");
  if (CLOSED.has(task.status)) names.push("reopen");
  if (!CLOSED.has(task.status) && task.status !== "declined") names.push("cancel");
  names.push("delete");
  return names;
}

/**
 * The More menu and the dialog that confirms the chosen action. `onDone(name,
 * sentence)` runs once the API accepted it.
 */
export function TaskActions({ task, onDone }) {
  const client = useApiClient();
  const engine = useProjectEngine(task.project_id);
  const [chosen, setChosen] = useState(null);
  const action = chosen ? TASK_ACTIONS[chosen] : null;

  return (
    <>
      <Menu
        label="Task actions"
        trigger="More"
        triggerClassName="menu__trigger--button"
        items={actionsFor(task, engine).map((name) => ({
          key: name,
          label: TASK_ACTIONS[name].label,
          onSelect: () => setChosen(name),
        }))}
      />
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
          onDone(name, TASK_ACTIONS[name].done);
        }}
      />
    </>
  );
}
