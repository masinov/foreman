import { formatDuration, humanize } from "../../ui/format";

// One vocabulary for what happened, used wherever activity is shown: the
// task's Activity tab, its Agent side bar and Overview, the decision box and
// the sprint's Activity. The same run reads the same everywhere.
//
// A run reaches the page in two shapes: the runs list (`step`, `backend`)
// and the task's own record (`workflow_step`, `agent_backend`). Both are read.

/** Who acts when no agent and no person does: the engine, by the product's name. */
export const FOREMAN = "Foreman";

const BUILTIN = "_builtin:";
const HUMAN_GATE = "_builtin:human_gate";
const MARK_DONE = "_builtin:mark_done";
const TESTS = "_builtin:run_tests";
const MERGE = "_builtin:merge";
const ORCHESTRATOR = "_builtin:orchestrator";
const PEOPLE = new Set(["human", "dashboard", "cli"]);
const ENGINE_BACKENDS = new Set(["builtin", "orchestrator", "engine"]);

const backendOf = (run) => run.backend ?? run.agent_backend ?? "";
const roleOf = (run) => String(run.role_id ?? "");

/** The step a run belongs to. */
export const stepOf = (run) => run.step ?? run.workflow_step ?? "";

// What Foreman records as who asked when no name was given: the channel, not a user.
const CHANNELS = new Set(["", "human", "dashboard", "cli", "api", "unknown"]);

/** A recorded actor as the page names them: their name, or "a user" when only the channel was recorded. */
export function userName(actor) {
  const value = String(actor ?? "").trim();
  return CHANNELS.has(value.toLowerCase()) ? "a user" : value;
}

/** Who did a run: a model, Foreman, a user (by name where the task records it). */
export function runBy(run, task = null) {
  // What a person did by hand names them.
  if (run.source === "event") return userName(run.actor);
  const backend = backendOf(run);
  const role = roleOf(run);
  if (role === HUMAN_GATE) return backend === "human" ? "a user" : FOREMAN;
  if (backend === "api") return task?.source?.system ? `${task.source.system}, through the API` : "the API";
  if (PEOPLE.has(backend) || role === "human") {
    const name = task?.created_by;
    if (run.outcome === "file" && name && name !== "human") return name;
    return "a user";
  }
  if (run.outcome === "file") return "an agent";
  if (ENGINE_BACKENDS.has(backend) || role.startsWith(BUILTIN)) return FOREMAN;
  return run.model || backend;
}

/**
 * Who did a run, by role: an agent's run names its role ("Developer",
 * "Code reviewer"), with the model in `title` for the hover; everyone else
 * is named as `runBy` names them. `{ text, title }`.
 */
export function runRole(run, task = null) {
  const by = runBy(run, task);
  const role = roleOf(run);
  const agent = run.source !== "event" && role && !role.startsWith(BUILTIN) && (by === run.model || by === backendOf(run));
  return agent ? { text: humanize(role), title: run.model || backendOf(run) } : { text: by, title: "" };
}

/** Who did it, as the activity's By filter names them (`who` from the API): a role, Foreman, users. */
export function whoWord(who) {
  if (who === "foreman") return FOREMAN;
  if (who === "user") return "Users";
  return humanize(who);
}

const GOOD = new Set(["done", "pass", "passed", "approve", "approved", "merged", "committed", "success", "succeeded", "completed", "complete", "accepted"]);
const BAD = new Set(["fail", "failed", "failure", "error", "errored", "reject", "rejected", "timeout", "timed_out", "cancelled", "cancel", "killed", "stopped"]);
const BACK = new Set(["steer", "deny", "denied", "changes_requested", "request_changes", "conflict", "blocked", "paused"]);

/** The colour an outcome is shown in: `passed`, `failed`, `attention` or `idle`. Its word says it too. */
export function outcomeTone(outcome) {
  const value = String(outcome || "").toLowerCase();
  if (GOOD.has(value)) return "passed";
  if (BAD.has(value)) return "failed";
  if (BACK.has(value)) return "attention";
  return "idle";
}

// Outcomes as a person says them once they happened.
const OUTCOME_WORDS = {
  approve: "Approved",
  reject: "Rejected",
  steer: "Sent back",
  deny: "Sent back",
  denied: "Sent back",
  request_changes: "Changes requested",
  changes_requested: "Changes requested",
  pass: "Passed",
  fail: "Failed",
  failure: "Failed",
  error: "Failed",
  conflict: "Merge conflict",
  updated: "Brought up to date",
  paused: "Asked a user",
  file: "Filed",
  created: "Filed",
  cancel: "Cancelled",
};

/** An outcome or a review decision in words: "approve" is "Approved", "steer" is "Sent back". */
export function outcomeWord(outcome) {
  return OUTCOME_WORDS[String(outcome || "").toLowerCase()] ?? humanize(outcome);
}

/** The outcomes that send a task back to be worked on again. */
export const SENT_BACK = new Set(["steer", "deny", "denied", "changes_requested", "request_changes"]);

/** What a step's success is called: tests pass, a merge merges, the last step closes the task. */
function successWord(role) {
  if (role === TESTS) return "Passed";
  if (role === MERGE) return "Merged";
  if (role === MARK_DONE) return "Closed";
  return "Done";
}

/** The first sentence of a long reason, which is what fits in a row. */
function firstSentence(text) {
  const value = String(text || "").trim();
  if (!value) return "";
  const line = value.split("\n")[0].trim();
  const end = line.search(/[.!?](\s|$)/);
  return end > 0 ? line.slice(0, end + 1) : line;
}

/**
 * Why a run ended as it did, when that is worth a line: a reviewer's or a
 * person's reason for sending it back, a failure's message, a merge conflict,
 * a gate decided by the project setting. Empty when the result says it all.
 */
export function runNote(run) {
  const detail = String(run.outcome_detail || "").trim();
  const outcome = String(run.outcome || "").toLowerCase();
  const role = roleOf(run);
  if (role === HUMAN_GATE) {
    if (outcome === "approve" && backendOf(run) !== "human") return "By the project setting";
    if (SENT_BACK.has(outcome)) return detail;
    return "";
  }
  if (SENT_BACK.has(outcome) || role === ORCHESTRATOR) return detail;
  if (BAD.has(outcome) || run.status === "failed" || run.status === "killed") return detail;
  if (outcome === "conflict" || outcome === "updated" || outcome === "blocked") return firstSentence(detail);
  return "";
}

/**
 * A run's result: `{ tone, word, note }`. The word is its outcome as a
 * person says it; the note, when there is one, is why (see `runNote`).
 */
export function runResult(run) {
  const outcome = String(run.outcome || "").toLowerCase();
  const role = roleOf(run);
  const note = runNote(run);
  if (role === ORCHESTRATOR && outcome === "success") {
    // A record the engine kept: of stopping or pausing the step under way,
    // of resuming, or of something about the sprint or the engine itself.
    if (/^Engine resumed/i.test(note)) return { tone: "idle", word: "Resumed", note: "" };
    if (/^(Shut down|Paused|Stopped task)/i.test(note)) return { tone: "idle", word: "Interrupted", note: firstSentence(note) };
    return { tone: "idle", word: "Recorded", note: firstSentence(note) };
  }
  if (run.status === "killed") return { tone: "failed", word: "Stopped", note };
  if (outcome === "success") return { tone: "passed", word: successWord(role), note };
  if (outcome) return { tone: outcomeTone(outcome), word: outcomeWord(outcome), note };
  if (run.status === "running") return { tone: "running", word: "Running", note: "" };
  if (run.status) return { tone: outcomeTone(run.status), word: humanize(run.status), note };
  return { tone: "idle", word: "", note: "" };
}

export function runSeconds(run) {
  return run.duration_ms === null || run.duration_ms === undefined ? null : run.duration_ms / 1000;
}

/** How long a run took, said only when it was long enough to matter (a second or more). */
export function runTook(run) {
  const seconds = runSeconds(run);
  return seconds !== null && seconds >= 1 ? formatDuration(seconds) : "";
}

// What a person did to a task by hand, as a sprint's activity lists it.
const BY_HAND = {
  closed: { tone: "idle", word: "Closed by hand" },
  cancelled: { tone: "failed", word: "Cancelled" },
  unblocked: { tone: "idle", word: "Unblocked" },
};

const REVIEWER = /review/;

/**
 * What happened, in a sprint's activity: a short phrase that names its step,
 * so a row needs no step column. "Developed", "Tests passed", "Approved",
 * "Sent back", "Merged", "Merge conflict", "Blocked", "Closed by hand".
 * `{ tone, word, why }`; `why` is the reason, shown on hover.
 */
export function stepEvent(item) {
  if (item.source === "event") {
    const hand = BY_HAND[item.outcome] ?? { tone: "idle", word: humanize(item.outcome) };
    return { ...hand, why: String(item.outcome_detail || "").trim() };
  }
  const result = runResult(item);
  const outcome = String(item.outcome || "").toLowerCase();
  const role = roleOf(item);
  const step = stepOf(item);
  const why = result.note;
  const as = (word) => ({ tone: result.tone, word, why });
  if (role === TESTS) {
    if (outcome === "success") return as("Tests passed");
    if (BAD.has(outcome)) return as("Tests failed");
  }
  if (REVIEWER.test(role) || REVIEWER.test(step)) {
    if (BAD.has(outcome) || item.status === "failed") return as("Review failed");
    return as(result.word);
  }
  if (role === MERGE || role === HUMAN_GATE || role === ORCHESTRATOR) return as(result.word);
  if (outcome === "done") return as("Developed");
  return as(result.word);
}
