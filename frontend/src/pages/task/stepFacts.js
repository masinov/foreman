import { formatDuration, formatMoney, formatTokens, humanize, shortSha } from "../../ui/format";
import { RULE_DECISIONS } from "../settings/settingsWords";
import { FOREMAN, outcomeTone, runResult, runRole, runSeconds, SENT_BACK, stepOf, stepOutcome } from "../shared/activityWords";

// The facts of one step, the column beside its story (owner, 2026-11-22):
// the same labels for every kind of step, each shown only where it applies.
// What the story would otherwise repeat line by line (the model, what the
// role may use, how it ended, what came next) is said here once.

const HUMAN_GATE = "_builtin:human_gate";

const MODEL_SOURCE = {
  role: "set by the role",
  project_default: "the project's default",
  task_override: "set for this task",
  ladder: "the next model on the role's ladder",
};

/** The data of the last event of a kind in a transcript, or null. */
function last(transcript, kind) {
  const entries = (transcript ?? []).filter((entry) => entry.kind === kind);
  return entries.length ? (entries[entries.length - 1].data ?? {}) : null;
}

/** "Read, Grep and Glob". */
function listWords(items) {
  return items.length > 1 ? `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}` : items[0];
}

/** Which attempt at its step a run was: as the runs list says, else from the step's own record; 1 when neither says. */
export function attemptOf(run, transcript) {
  return Number(run?.attempt) || Number(last(transcript, "workflow.step_started")?.visit_count) || 1;
}

/** What a role may use, in words, from the policy the step ran under. */
export function toolsWords(policy) {
  if (!policy) return "";
  if (policy.no_tools) return "No tools";
  if (policy.allowed_tools?.length) return listWords(policy.allowed_tools);
  if (policy.disallowed_tools?.length) return `Every tool except ${listWords(policy.disallowed_tools)}`;
  return "Every tool";
}

/** The commit a step was about, with what it was to that step. */
function commitFact(run, transcript) {
  const merged = last(transcript, "engine.merge");
  if (merged?.sha) return { term: "Merge commit", sha: merged.sha };
  const tested = last(transcript, "engine.test_run");
  if (tested?.head_sha) return { term: "Tested", sha: tested.head_sha };
  const reviewed = last(transcript, "engine.review_recorded");
  if (reviewed?.head_sha) return { term: "Reviewed", sha: reviewed.head_sha };
  return run.commit_sha ? { term: "Commit", sha: run.commit_sha } : null;
}

/** Who decided at a gate: a user, or the project's setting (by its name on the settings page). */
function decidedBy(run, transcript) {
  if (String(run.role_id ?? "") !== HUMAN_GATE) return null;
  const auto = last(transcript, "workflow.gate_auto_approved");
  if ((run.backend ?? run.agent_backend) === "human") return { text: "A user" };
  if (!auto && !run.outcome) return null;
  const policy = auto?.policy ?? last(transcript, "workflow.paused")?.policy ?? stepOf(run);
  const label = RULE_DECISIONS.find((entry) => entry.key === policy)?.label ?? humanize(policy);
  return { text: `The project's setting “${label}”: ${FOREMAN}`, settings: true };
}

/** Why a step ended as it did, where its story does not already say it in someone's words. */
function why(run, gate) {
  const outcome = String(run.outcome || "").toLowerCase();
  const detail = String(run.outcome_detail || "").trim();
  if (!detail) return "";
  if (gate) return SENT_BACK.has(outcome) ? detail : "";
  const failed = run.status === "failed" || run.status === "killed" || outcomeTone(outcome) === "failed";
  return failed || outcome === "conflict" || outcome === "blocked" ? detail.split("\n")[0] : "";
}

/**
 * The facts of a run, in the order the column lists them. Each is
 * `{ key, term, text, tone?, sha?, run?, settings? }`: `sha` is a commit,
 * `run` a run to pick (the one before or after it), `settings` a link to
 * the project's settings.
 *
 * `previous` and `next` are the runs just before and after it on the task.
 */
export function stepFacts(run, transcript, { previous = null, next = null, task = null } = {}) {
  const facts = [];
  // The same words as the step's row.
  const result = stepOutcome(run, previous);
  const gate = decidedBy(run, transcript);
  facts.push({ key: "result", term: "Result", text: result.word, tone: result.tone });
  const reason = why(run, Boolean(gate));
  if (reason) facts.push({ key: "why", term: "Why", text: reason });
  if (gate) facts.push({ key: "decided", term: "Decided by", text: gate.text, settings: Boolean(gate.settings) });
  // The step just before it sent the task back or failed: this one answers it.
  if (previous) {
    const before = runResult(previous);
    if (before.tone === "attention" || before.tone === "failed") {
      facts.push({ key: "after", term: "After", text: `${humanize(stepOf(previous))}, ${before.word.toLowerCase()}`, run: previous.id });
    }
  }
  const commit = commitFact(run, transcript) ?? (run.step_commit ? { term: "Commit", sha: run.step_commit } : null);
  if (commit) facts.push({ key: "commit", term: commit.term, text: shortSha(commit.sha), sha: commit.sha });
  const by = runRole(run, task);
  if (by.text) facts.push({ key: "by", term: "By", text: by.text });
  const chosen = last(transcript, "workflow.model_selected");
  const model = chosen?.model || run.model;
  if (model) {
    const source = MODEL_SOURCE[chosen?.source] ?? "";
    facts.push({ key: "model", term: "Model", text: source ? `${model}, ${source}` : model });
  }
  const tools = toolsWords(last(transcript, "engine.role_policy"));
  if (tools) facts.push({ key: "tools", term: "May use", text: tools });
  const seconds = runSeconds(run);
  if (seconds !== null && seconds >= 1) facts.push({ key: "took", term: "Took", text: formatDuration(seconds) });
  const tokens = Number(run.tokens ?? run.token_count ?? 0);
  if (run.cost_usd || tokens) {
    facts.push({ key: "spend", term: "Spend", text: [run.cost_usd ? formatMoney(run.cost_usd) : "", tokens ? `${formatTokens(tokens)} tokens` : ""].filter(Boolean).join(" · ") });
  }
  if (next) facts.push({ key: "next", term: "Next", text: humanize(stepOf(next)), run: next.id });
  else {
    const transition = last(transcript, "workflow.transition");
    if (transition?.to_step) facts.push({ key: "next", term: "Next", text: humanize(transition.to_step) });
  }
  return facts;
}
