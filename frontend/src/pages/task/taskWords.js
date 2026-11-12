import { formatDuration, humanize, plural, shortSha } from "../../ui/format";

// How the task page puts what the API says into words (design 05, 12, 13,
// 14). Pure functions, so each sentence is tested on its own.

const HUMAN_GATE = "_builtin:human_gate";
const MARK_DONE = "_builtin:mark_done";
const BUILTIN = "_builtin:";

/** The kinds of decision a task can wait for (design README, "Needs you"). */
export const DECISIONS = {
  merge: "merge",
  plan: "plan",
  gate: "gate",
  accept: "accept",
  unblock: "unblock",
};

/** The default branch a task merges into, as the checks name it. */
export function defaultBranchOf(checks) {
  return checks?.facts?.branch?.default_branch || "the default branch";
}

/**
 * What the task waits for a person to decide, or null when it waits for
 * nobody: `{ kind, question, approve, sendBack }`. `approve` and `sendBack`
 * are the two buttons' words; `sendBack.ask` is what the dialog asks for.
 */
export function decisionOf(task, checks) {
  if (task.status === "triage") {
    return {
      kind: DECISIONS.accept,
      question: "Accept this task?",
      approve: "Accept",
      sendBack: {
        label: "Decline",
        title: "Decline this task",
        ask: "Why it is declined",
        hint: "Optional. Kept with the task in the backlog.",
        required: false,
        effect: "The task stays in the backlog, marked declined. Nothing runs it.",
      },
    };
  }
  if (task.status !== "blocked") return null;
  if (task.blocked_kind === "gate" || task.awaiting_human_gate) {
    const sendBack = {
      label: "Send back",
      title: "Send back",
      ask: "Guidance for the agent",
      hint: "What should change. The agent reads it on its next step.",
      required: true,
      effect: "The task goes back to the step the workflow names for a refusal, with this guidance.",
    };
    if (task.gate_policy === "merge_approval") {
      return {
        kind: DECISIONS.merge,
        question: `Approve the merge into ${defaultBranchOf(checks)}?`,
        approve: "Approve merge",
        sendBack,
      };
    }
    if (task.gate_policy === "plan_approval") {
      return { kind: DECISIONS.plan, question: "Approve this plan?", approve: "Approve plan", sendBack };
    }
    const step = task.workflow_current_step ? humanize(task.workflow_current_step).toLowerCase() : "this step";
    return { kind: DECISIONS.gate, question: `Approve ${step}?`, approve: "Approve", sendBack };
  }
  const reason = (task.blocked_reason || "").trim();
  return {
    kind: DECISIONS.unblock,
    question: reason ? `Blocked: ${reason}` : "Blocked, and no reason was recorded",
    approve: "Unblock",
    sendBack: {
      label: "Send back",
      title: "Send back with guidance",
      ask: "Guidance for the agent",
      hint: "What should change. The agent reads it on its next step.",
      required: true,
      effect: "The task goes back to the queue and its workflow starts again from the first step, with this guidance.",
    },
  };
}

// ── Runs ─────────────────────────────────────────────────────────────────

const PEOPLE = new Set(["human", "dashboard", "cli"]);

/** Who did a run: the model, "engine" for the engine's own steps, "a person". */
export function runBy(run) {
  const backend = run.backend ?? run.agent_backend;
  if (backend === "builtin" || String(run.role_id || "").startsWith(BUILTIN)) return "engine";
  if (PEOPLE.has(backend) || run.role_id === "human") return "a person";
  return run.model || backend || "";
}

const GOOD = new Set(["done", "pass", "passed", "approve", "approved", "merged", "committed", "success", "succeeded", "completed", "complete", "accepted"]);
const BAD = new Set(["fail", "failed", "failure", "error", "errored", "reject", "rejected", "deny", "denied", "changes_requested", "request_changes", "timeout", "timed_out", "cancelled", "killed", "stopped"]);

/** `passed`, `failed` or `idle`: the colour an outcome is shown in. Its word says it too. */
export function outcomeTone(outcome) {
  const value = String(outcome || "").toLowerCase();
  if (GOOD.has(value)) return "passed";
  if (BAD.has(value)) return "failed";
  return "idle";
}

// Outcomes as a person says them once they happened.
const OUTCOME_WORDS = {
  approve: "Approved",
  reject: "Rejected",
  deny: "Sent back",
  denied: "Sent back",
  request_changes: "Changes requested",
  changes_requested: "Changes requested",
  pass: "Passed",
  fail: "Failed",
};

/** An outcome or a review decision in words: "approve" is "Approved". */
export function outcomeWord(outcome) {
  return OUTCOME_WORDS[String(outcome || "").toLowerCase()] ?? humanize(outcome);
}

/** A run's result in words: its outcome, or what it is doing if it has none. */
export function runResult(run) {
  if (run.outcome) return { tone: outcomeTone(run.outcome), word: outcomeWord(run.outcome) };
  if (run.status === "running") return { tone: "running", word: "Running" };
  if (run.status) return { tone: outcomeTone(run.status), word: humanize(run.status) };
  return { tone: "idle", word: "" };
}

export function runSeconds(run) {
  return run.duration_ms === null || run.duration_ms === undefined ? null : run.duration_ms / 1000;
}

function runTime(run) {
  return run.started_at || run.created_at || "";
}

/**
 * The steps table on Overview: one row per step of the workflow (the step
 * that only marks a task done is left out), from the task's runs.
 * `[{ id, label, result: { tone, word }, by, runs }]`.
 */
export function stepRows(task, workflow) {
  const runs = [...(task.runs ?? [])].sort((a, b) => runTime(a).localeCompare(runTime(b)));
  const steps = (workflow?.steps ?? []).filter((step) => step.role !== MARK_DONE);
  return steps.map((step) => {
    const mine = runs.filter((run) => run.workflow_step === step.id);
    const last = mine[mine.length - 1] ?? null;
    const here = task.workflow_current_step === step.id;
    let result;
    if (here && task.status === "blocked" && (task.blocked_kind === "gate" || step.role === HUMAN_GATE)) {
      result = { tone: "attention", word: "Waiting for you" };
    } else if (here && task.status === "blocked") {
      result = { tone: "attention", word: "Blocked here" };
    } else if (here && task.status === "in_progress") {
      result = { tone: "running", word: "Running" };
    } else if (last) {
      const { tone, word } = runResult(last);
      const took = formatDuration(runSeconds(last));
      result = { tone, word: took && word ? `${word} in ${took}` : word };
    } else {
      result = { tone: "idle", word: "Not reached" };
    }
    let by = last ? runBy(last) : "";
    if (!by && step.role === HUMAN_GATE) by = "a person";
    if (!by && step.role.startsWith(BUILTIN)) by = "engine";
    return { id: step.id, label: humanize(step.id), result, by, runs: mine.length };
  });
}

// ── Checks: facts and claims ─────────────────────────────────────────────

/** The tests fact as `{ tone, word, detail }`. */
export function testsWords(tests) {
  const sha = shortSha(tests?.commit);
  const took = formatDuration(tests?.duration_seconds);
  const where = [took ? `in ${took}` : "", sha ? `at ${sha}` : ""].filter(Boolean).join(" ");
  switch (tests?.status) {
    case "passed":
      return { tone: "passed", word: "Passed", detail: where };
    case "failed":
      return {
        tone: "failed",
        word: "Failed",
        detail: [where, tests.exit_code !== null && tests.exit_code !== undefined ? `exit code ${tests.exit_code}` : ""]
          .filter(Boolean)
          .join(", "),
      };
    case "stale":
      return { tone: "attention", word: "Out of date", detail: `${where}; the branch has moved since` };
    default:
      return { tone: "idle", word: "Not run", detail: "" };
  }
}

/** The branch fact against the default branch, as `{ tone, word }`. */
export function branchWords(branch) {
  const target = branch?.default_branch || "the default branch";
  if (!branch || branch.state === "no_branch") return { tone: "idle", word: "No branch to compare" };
  if (branch.state === "behind") {
    return { tone: "attention", word: `${plural(branch.behind ?? 0, "commit")} behind ${target}` };
  }
  return { tone: "passed", word: `Up to date with ${target}` };
}

/** "3 files, +118 −7". */
export function sizeWords(size) {
  if (!size) return "";
  return `${plural(size.files ?? 0, "file")}, +${size.added ?? 0} −${size.deleted ?? 0}`;
}

/** The latest code review among the claims, if any. */
export function codeReview(checks) {
  const reviews = checks?.claims?.reviews ?? [];
  return reviews.find((review) => review.kind === "code") ?? reviews[0] ?? null;
}

/** A review claim as `{ tone, word, detail }`. */
export function reviewWords(review) {
  const word = review.decision ? outcomeWord(review.decision) : "No decision";
  const parts = [review.model ? `by ${review.model}` : "", review.duration_seconds ? `in ${formatDuration(review.duration_seconds)}` : ""];
  const sha = shortSha(review.commit);
  if (sha) parts.push(`at ${sha}`);
  if (review.current === false) parts.push("(the branch has moved since)");
  return {
    tone: outcomeTone(review.decision),
    word: review.kind === "security" ? `Security review: ${word.toLowerCase()}` : word,
    detail: parts.filter(Boolean).join(" "),
  };
}

const CRITERION_WORDS = {
  passed: { tone: "passed", word: "Met" },
  partial: { tone: "attention", word: "Partly met" },
  failed: { tone: "failed", word: "Not met" },
  unverified: { tone: "idle", word: "Not judged" },
};

export function criterionWords(status) {
  return CRITERION_WORDS[status] ?? { tone: "idle", word: humanize(status) };
}

/** "2 of 3 acceptance criteria marked met by sonnet-5-5", or what is true instead. */
export function criteriaSummary(claims) {
  const criteria = claims?.criteria ?? [];
  if (criteria.length === 0) return "No acceptance criteria were filed";
  if (!claims.judged_by || claims.judged_by === "none") {
    return `${plural(criteria.length, "acceptance criterion", "acceptance criteria")}, not judged yet`;
  }
  const met = criteria.filter((item) => item.status === "passed").length;
  return `${met} of ${criteria.length} acceptance criteria marked met by ${claims.judged_by}`;
}

// ── Details ──────────────────────────────────────────────────────────────

const POLICY_SOURCES = {
  task_override: "this task",
  task_type_rule: "rule for its type",
  project_default: "project setting",
  built_in_default: "default",
};

const GATE_WORDS = {
  plan_approval: { human: "A person approves plans", auto: "Foreman approves plans" },
  merge_approval: { human: "A person approves merges", auto: "Foreman approves merges" },
};

/**
 * Who decides at the gates this task's workflow has, as
 * `[{ key, text, source }]`. Without the workflow, both gates are named.
 */
export function whoDecides(task, workflow) {
  const policies = task.policy ?? {};
  const gates = workflow
    ? (workflow.steps ?? []).filter((step) => step.role === HUMAN_GATE && step.policy).map((step) => step.policy)
    : Object.keys(GATE_WORDS);
  return [...new Set(gates)]
    .filter((gate) => GATE_WORDS[gate] && policies[gate])
    .map((gate) => ({
      key: gate,
      text: GATE_WORDS[gate][policies[gate].value] ?? `${humanize(gate)}: ${policies[gate].value}`,
      source: POLICY_SOURCES[policies[gate].source] ?? humanize(policies[gate].source),
    }));
}

/** Who filed the task: a reporter and a system, else who created it. */
export function filedBy(task) {
  const source = task.source;
  if (source && (source.reporter || source.system)) {
    return [source.reporter, source.system ? `via ${source.system}` : null].filter(Boolean).join(" ");
  }
  if (!task.created_by) return "";
  return task.created_by === "human" ? "a person" : humanize(task.created_by).toLowerCase();
}

// ── Overrides for this task ──────────────────────────────────────────────

const GATE_CHOICES = [
  { value: "human", word: "A person decides" },
  { value: "auto", word: "Foreman decides" },
];

/** The two answers a gate override can take, as `[{ value, word }]`. */
export const gateChoices = () => GATE_CHOICES;

/** The human gates of a workflow that name a policy, as `[{ id, policy, label }]`. */
export function overrideGates(workflow) {
  return (workflow?.steps ?? [])
    .filter((step) => step.role === HUMAN_GATE && GATE_WORDS[step.policy])
    .filter((step, index, all) => all.findIndex((other) => other.policy === step.policy) === index)
    .map((step) => ({ id: step.id, policy: step.policy, label: humanize(step.policy) }));
}

/** The agent steps of a workflow, which a model can be chosen for, as `[{ id, label }]`. */
export function overrideSteps(workflow) {
  return (workflow?.steps ?? [])
    .filter((step) => !String(step.role).startsWith(BUILTIN))
    .map((step) => ({ id: step.id, label: humanize(step.id) }));
}

/** What the task overrides for a gate now: `"human"`, `"auto"` or `""` for nothing. */
export function currentGateOverride(task, policy) {
  const overrides = task.executor_overrides ?? {};
  return overrides.policy?.[policy] ?? overrides.gates?.[policy] ?? "";
}

/**
 * The `executor_overrides` object to send: what the task has now, with the
 * given gates (`{ policy: "human" | "auto" | "" }`) and step models
 * (`{ step: "model" | "" }`) set, or removed when empty. Everything else the
 * task carries (a ladder start, other decisions) is kept as it is.
 */
export function applyOverrides(current, { gates = {}, models = {} }) {
  const next = { ...(current ?? {}) };
  const policy = { ...(next.policy ?? {}) };
  const older = { ...(next.gates ?? {}) };
  for (const [name, value] of Object.entries(gates)) {
    // `policy` wins over the older `gates`, so a change is written to one place.
    delete older[name];
    if (value) policy[name] = value;
    else delete policy[name];
  }
  const modelMap = { ...(next.models ?? {}) };
  for (const [step, value] of Object.entries(models)) {
    const model = String(value ?? "").trim();
    if (model) modelMap[step] = model;
    else delete modelMap[step];
  }
  for (const [key, value] of [["policy", policy], ["gates", older], ["models", modelMap]]) {
    if (Object.keys(value).length) next[key] = value;
    else delete next[key];
  }
  return next;
}
