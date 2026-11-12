import { humanize } from "../../ui/format";

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

/** `{ tone, word, group }` for a task. */
export function stageOf(task) {
  if (task.status === "blocked") {
    if (task.awaiting_human_gate) {
      const word =
        task.gate_policy === MERGE_APPROVAL
          ? "Waiting for merge approval"
          : task.gate_policy === PLAN_APPROVAL
            ? "Waiting for plan approval"
            : "Waiting for approval";
      return { tone: "attention", word, group: GROUPS.needsYou };
    }
    return { tone: "attention", word: "Blocked", group: GROUPS.needsYou };
  }
  if (task.status === "triage") {
    return { tone: "attention", word: "Waiting to be accepted", group: GROUPS.needsYou };
  }
  if (task.status === "in_progress") {
    const step = task.workflow_current_step ? humanize(task.workflow_current_step).toLowerCase() : null;
    return { tone: "running", word: step ? `Running, ${step}` : "Running", group: GROUPS.running };
  }
  if (task.status === "done") return { tone: "passed", word: "Done", group: GROUPS.finished };
  if (task.status === "cancelled") return { tone: "idle", word: "Cancelled", group: GROUPS.finished };
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
  return { parts, commit: checks?.commit ?? null };
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
