import { ENGINE_STATES } from "../../api/workspace";
import { humanize } from "../../ui/format";
import { shownCommit } from "../shared/gateVersion";
import { whenSet } from "../shared/workWords";

// How a task reads on the sprint page: its stage in words, where it sorts,
// the checks it carries, and which board column it is in. The words are the
// design's (docs/design/dashboard-v7/04, 07); steps come from the project's
// workflow, never from a list here.

const MERGE_APPROVAL = "merge_approval";
const PLAN_APPROVAL = "plan_approval";

/** Groups in the order a person reads a sprint: needs them, moving, waiting, finished. */
export const GROUPS = { needsYou: 0, running: 1, queued: 2, finished: 3 };

export function waitsForMerge(task) {
  return Boolean(task.awaiting_human_gate) && task.gate_policy === MERGE_APPROVAL;
}

/** True when a person has to act before the task moves. */
export function needsPerson(task) {
  return task.status === "blocked" || task.status === "triage";
}

/**
 * A status and the step the task is at, named as Activity and the board name
 * it: "Running · Develop", "Blocked · Test". The status alone where the task
 * is at no step.
 */
function atStep(status, task) {
  return task.workflow_current_step ? `${status} · ${humanize(task.workflow_current_step)}` : status;
}

/**
 * What a user's hold on a task says (ADR-0043): `{ tone, word, title }`, or
 * null. A block above (on the sprint or the workspace) reads "Blocked"; a
 * Block waiting for the running step to end, "Blocking"; a pause, "Pausing"
 * or "Stopping" while the step still runs, then "Paused" or "Stopped". Who,
 * why and when are the title.
 */
export function holdStage(task) {
  const hold = task.hold;
  if (!hold) return null;
  const when = whenSet(hold.at);
  const who = [hold.by ? `by ${hold.by}` : "", when ? `at ${when}` : ""].filter(Boolean).join(" ");
  if (hold.kind === "block") {
    return { tone: "attention", word: "Blocked", title: `The ${hold.scope} is blocked: ${hold.reason}` };
  }
  if (hold.kind === "blocking") {
    return {
      tone: task.step_running ? "running" : "attention",
      word: task.step_running ? "Blocking" : "Blocked",
      title: `Blocked when its step ends: ${hold.reason}`,
    };
  }
  const stopped = hold.mode === "now";
  if (task.step_running) {
    return { tone: "running", word: stopped ? "Stopping" : "Pausing", title: `${stopped ? "Stopped" : "Paused"} ${who}`.trim() };
  }
  return {
    tone: "idle",
    word: stopped ? "Stopped" : "Paused",
    title: stopped ? `Stopped ${who}; the cut step runs again on Resume.` : `Paused ${who}`.trim(),
  };
}

/**
 * `{ tone, word, group }` for a task: its status, and where it is under way
 * the step it is at (owner, 2026-11-24: the list's column is its Status).
 * A user's hold says so first (`holdStage`, ADR-0043). A task part-way
 * through its workflow is "Running" while a step of it runs; a task a person
 * asked to run next says "Runs next" until it starts; otherwise it is
 * "Waiting" for its turn (`title` says after which task, or that no worker
 * runs the project; `engine` is the project's worker from the workspace).
 * A task not started that waits for another reads "Waiting · FOR-65".
 */
export function stageOf(task, engine = null) {
  const held = holdStage(task);
  if (task.status === "blocked") {
    if (task.awaiting_human_gate) {
      if (held) return { ...held, word: atStep(held.word, task), group: GROUPS.needsYou };
      const word =
        task.gate_policy === MERGE_APPROVAL
          ? "Waiting for merge approval"
          : task.gate_policy === PLAN_APPROVAL
            ? "Waiting for plan approval"
            : "Waiting for approval";
      return { tone: "attention", word, group: GROUPS.needsYou };
    }
    if (task.blocked_kind === "question") {
      if (held) return { ...held, word: atStep(held.word, task), group: GROUPS.needsYou };
      return { tone: "attention", word: "Waiting for an answer", group: GROUPS.needsYou };
    }
    return { tone: "attention", word: atStep("Blocked", task), group: GROUPS.needsYou };
  }
  if (task.status === "triage") {
    // In the backlog a request waits for a person only where Foreman would
    // otherwise start it (ADR-0028); elsewhere it is backlog work like any other.
    if (task.in_backlog) {
      return task.foreman_starts_backlog_work
        ? { tone: "attention", word: "A request, not accepted", group: GROUPS.needsYou }
        : { tone: "idle", word: "In the backlog", group: GROUPS.queued };
    }
    return { tone: "attention", word: "Waiting to be accepted", group: GROUPS.needsYou };
  }
  if (task.status === "in_progress") {
    if (held) return { ...held, word: atStep(held.word, task), group: GROUPS.running };
    const onIt = engine?.task_id === task.id;
    if (task.step_running || (onIt && engine.state === ENGINE_STATES.running)) {
      return { tone: "running", word: atStep("Running", task), group: GROUPS.running };
    }
    if (task.run_next) return { tone: "idle", word: atStep("Runs next", task), group: GROUPS.running };
    const after = engine?.task_key || engine?.task_id;
    const noWorker = engine && engine.state !== ENGINE_STATES.running;
    return {
      tone: "idle",
      word: atStep("Waiting", task),
      title: noWorker ? "No worker runs this project." : after ? `Foreman runs it after ${after}` : "",
      group: GROUPS.running,
    };
  }
  if (task.status === "done") return { tone: "passed", word: "Done", group: GROUPS.finished };
  if (task.status === "cancelled") return { tone: "idle", word: "Cancelled", group: GROUPS.finished };
  // In the backlog nothing is queued: it runs once it is in a sprint.
  if (task.in_backlog) return { tone: "idle", word: "In the backlog", group: GROUPS.queued };
  if (held) return { ...held, group: GROUPS.queued };
  if (task.run_next) return { tone: "idle", word: "Runs next", group: GROUPS.queued };
  const waits = task.waits_for ?? [];
  if (waits.length) {
    return {
      tone: "idle",
      word: `Waiting · ${waits[0]}`,
      title: `Starts when ${waits.join(", ")} ${waits.length === 1 ? "is" : "are"} done.`,
      group: GROUPS.queued,
    };
  }
  return { tone: "idle", word: "Queued", group: GROUPS.queued };
}

/** Waiting for a person, running, queued in run order, then finished. The API lists tasks in run order. */
export function orderTasks(tasks) {
  return tasks
    .map((task, index) => ({ task, index, group: stageOf(task).group }))
    .sort((a, b) => a.group - b.group || a.index - b.index)
    .map((entry) => entry.task);
}

const GOOD_REVIEWS = new Set(["approve", "approved", "pass", "passed"]);

/**
 * The checks a task carries, from its completion evidence: `[{ key, tone,
 * text }]` for tests and review, and the commit as `commit`. Checks that did
 * not run are left out.
 */
export function checksOf(task) {
  const checks = task.checks;
  const parts = [];
  if (checks?.tests === "passed") parts.push({ key: "tests", tone: "passed", text: "tests" });
  else if (checks?.tests === "failed") parts.push({ key: "tests", tone: "failed", text: "tests failed" });
  else if (checks?.tests === "stale") parts.push({ key: "tests", tone: "attention", text: "tests stale" });
  if (checks?.review) {
    parts.push(
      GOOD_REVIEWS.has(checks.review)
        ? { key: "review", tone: "passed", text: "review" }
        : { key: "review", tone: "attention", text: `review ${humanize(checks.review).toLowerCase()}` },
    );
  }
  // A task at the merge gate shows the commit an Approve names: the one its
  // checks ran on, else the branch's head.
  const commit = waitsForMerge(task) ? shownCommit(checks?.commit, task.gate_version) : (checks?.commit ?? null);
  return { parts, commit };
}

/** The version a row's Approve names: the commit the row shows (`checksOf`). */
export function approvalVersion(task) {
  return checksOf(task).commit;
}

/**
 * The board's columns: Queued first, one per step of the workflow, Done
 * last. The workflow's own closing step (the one that marks a task done) is
 * the Done column, so it is not repeated. Tasks that are running at a step the
 * workflow does not list go in a last column, "Elsewhere", shown only then.
 *
 * Returns `[{ key, label, tasks, needsYou }]`.
 */
export function boardColumns(tasks, workflow) {
  const steps = (workflow?.steps ?? []).filter((step) => step.role !== "_builtin:mark_done");
  const byKey = new Map([["queued", []]]);
  for (const step of steps) byKey.set(`step:${step.id}`, []);
  byKey.set("done", []);
  const elsewhere = [];

  for (const task of tasks) {
    if (task.status === "todo" || task.status === "triage") byKey.get("queued").push(task);
    else if (task.status === "done") byKey.get("done").push(task);
    else if (task.status === "in_progress" || task.status === "blocked") {
      const column = byKey.get(`step:${task.workflow_current_step}`);
      (column ?? elsewhere).push(task);
    }
  }

  const columns = [
    { key: "queued", label: "Queued", tasks: byKey.get("queued") },
    ...steps.map((step) => ({ key: `step:${step.id}`, label: humanize(step.id), tasks: byKey.get(`step:${step.id}`) })),
  ];
  if (elsewhere.length > 0) columns.push({ key: "elsewhere", label: "Elsewhere", tasks: elsewhere });
  columns.push({ key: "done", label: "Done", tasks: byKey.get("done") });
  return columns.map((column) => ({ ...column, needsYou: column.tasks.some(needsPerson) }));
}
