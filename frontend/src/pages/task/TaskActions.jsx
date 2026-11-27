import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { runTaskNext } from "../../api/engine";
import { declineTask } from "../../api/backlog";
import { pauseTask, resumeTask, stopTask } from "../../api/holds";
import { blockTask, deleteTask, reopenTask, unblockTask } from "../../api/tasks";
import { askManager, splitTaskRequest } from "../../app/managerRequests";
import { paths } from "../../app/paths";
import { useNavigate } from "../../app/router";
import { Button } from "../../ui/Button";
import { Menu } from "../../ui/Menu";
import { ReasonDialog } from "../shared/ReasonDialog";
import { CloseTaskDialog } from "./CloseTaskDialog";

/**
 * What a person can do to a task besides answering its question, each with
 * what will happen in words. `done` is the sentence shown once the API
 * accepted it. Closing a task has its own dialog (`CloseTaskDialog`).
 * Actions marked `direct` act at once, with no dialog: Pause, Stop and Resume
 * are undone by one another (ADR-0043), and Run next only changes the order.
 */
export const TASK_ACTIONS = {
  run: {
    label: "Run next",
    direct: true,
    run: (client, task) => runTaskNext(client, task.project_id, task.id),
    done: (task) => `${task.task_key || "The task"} runs next.`,
  },
  pause: {
    label: "Pause",
    icon: "pause",
    direct: true,
    run: (client, task) => pauseTask(client, task.id),
    done: (task) =>
      task.step_running
        ? `Paused ${task.task_key || "the task"}. Its running step finishes first.`
        : `Paused ${task.task_key || "the task"}.`,
  },
  stop: {
    label: "Stop",
    icon: "stop",
    variant: "stop",
    direct: true,
    run: (client, task) => stopTask(client, task.id),
    done: (task) => `Stopped ${task.task_key || "the task"}. The step runs again on Resume.`,
  },
  resume: {
    label: "Resume",
    icon: "play",
    direct: true,
    run: (client, task) => resumeTask(client, task.id),
    done: (task) => `Resumed ${task.task_key || "the task"}.`,
  },
  withdraw: {
    label: "Unblock",
    direct: true,
    run: (client, task) => unblockTask(client, task.id),
    done: (task) => `Unblocked ${task.task_key || "the task"}. Its step goes on.`,
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
    effect:
      "The task is held until someone unblocks it, and what waits for it waits too. A running step finishes first. It waits in Needs you; Unblock starts its workflow over.",
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
 * The actions that exist for a task in its state: `{ buttons, more, heldAbove }`.
 *
 * `buttons` are in plain sight beside the title: what depends on the task's
 * state and its holds (ADR-0043) and ending it by hand (Close). Run next is
 * for a task that may run; a paused task shows Resume instead, never both.
 * Pause where it could run, Stop while a step of it runs, Unblock for a Block
 * still waiting for the running step. `heldAbove` is the block on its sprint
 * or the workspace: Resume is then disabled, saying which.
 * `more` is what is rare: Block, Split, Decline, Delete. Answering the task's
 * question (approve, unblock, send back) is the decision's, not listed here.
 * While a step runs the task can be neither closed nor deleted (the API
 * refuses both until the step stops).
 */
export function actionsFor(task) {
  const planned = !task.in_backlog;
  const hold = task.hold ?? null;
  const running = Boolean(task.step_running);
  const heldAbove = hold?.kind === "block" ? hold : null;
  const paused = hold?.kind === "pause";
  const blocking = hold?.kind === "blocking";
  const startable = task.status === "todo" || task.status === "in_progress";
  const buttons = [];
  const more = [];
  if (planned && startable && !hold && !running) buttons.push("run");
  // Lifting a hold comes first, as on a sprint: Resume (or why not), Unblock.
  if (paused || heldAbove) buttons.push("resume");
  if (blocking) buttons.push("withdraw");
  // A task blocked by a failure cannot run anyway; one waiting at a gate can
  // be paused, which lets the sprint go on without it (ADR-0043).
  const pausable = startable || (task.status === "blocked" && (task.awaiting_human_gate || task.blocked_kind === "question"));
  if (planned && pausable && !hold) buttons.push("pause");
  if (running && !(paused && hold.mode === "now") && !blocking) buttons.push("stop");
  if (CLOSED.has(task.status)) buttons.push("reopen");
  if (planned && OPEN.has(task.status) && !running) buttons.push("close");
  if (planned && startable && !blocking) more.push("block");
  if (task.status === "todo" || task.status === "triage") more.push("split");
  // In the backlog, "we won't do this" is Decline, the one way (owner,
  // 2026-11-18): a filed task has it in its decision, an accepted one here.
  if (!planned && task.status === "todo") more.push("decline");
  if (!running) more.push("delete");
  return { buttons, more, heldAbove };
}

/**
 * The task's actions beside its title: the buttons, the More menu and the
 * dialog that confirms the chosen one. `onDone(name, sentence)` runs once the
 * API accepted it.
 */
export function TaskActions({ task, onDone }) {
  const client = useApiClient();
  const navigate = useNavigate();
  const [chosen, setChosen] = useState(null);
  const [acting, setActing] = useState(null);
  const [refusal, setRefusal] = useState(null);
  const action = chosen && chosen !== "close" ? TASK_ACTIONS[chosen] : null;
  const { buttons, more, heldAbove } = actionsFor(task);

  async function direct(name) {
    setActing(name);
    setRefusal(null);
    try {
      await TASK_ACTIONS[name].run(client, task);
      onDone(name, TASK_ACTIONS[name].done(task));
    } catch (error) {
      setRefusal(errorSentence(error));
    } finally {
      setActing(null);
    }
  }

  function button(name) {
    const spec = TASK_ACTIONS[name];
    // A request not started yet is asked once: its sign is a disabled
    // "Runs next" until the task starts.
    if (name === "run" && task.run_next) {
      return (
        <Button key={name} disabled title="Foreman runs this task next">
          Runs next
        </Button>
      );
    }
    // Under a block on its sprint or the workspace, Resume would do
    // nothing: it says why instead, and the block is lifted where it was set.
    if (name === "resume" && heldAbove) {
      return (
        <Button key={name} icon="play" disabled title={heldAbove.reason}>
          {heldAbove.scope === "workspace" ? "Workspace blocked" : "Sprint blocked"}
        </Button>
      );
    }
    return (
      <Button
        key={name}
        icon={spec.icon ?? null}
        variant={spec.variant ?? "default"}
        disabled={acting !== null}
        onClick={() => (spec.direct ? direct(name) : setChosen(name))}
      >
        {spec.label}
      </Button>
    );
  }

  return (
    <>
      {buttons.map(button)}
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
      {refusal ? (
        <p className="notice notice--error task__action-refusal" role="alert">
          {refusal}
        </p>
      ) : null}
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
