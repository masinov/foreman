// What a run recorded, said in words. The API gives each event's kind and
// facts; nothing here is invented, and an event this file does not know is
// shown by its name with its facts beside it, never dropped.

import { formatDuration, formatMoney, formatTokens, humanize, plural, shortSha } from "../../ui/format";
import { outcomeTone, outcomeWord } from "./taskWords";

/** Bookkeeping the engine records for itself; it tells a reader nothing. */
const SILENT = new Set([
  "engine.context_write",
  "agent.session",
  "agent.cost_update",
  "policy.resolved",
  // The engine records the same task as `engine.task_created`.
  "signal.task_created",
]);

const MODEL_SOURCE = {
  role: "named by the role",
  project_default: "the project's default",
  task_override: "set for this task",
  ladder: "the next model on the role's ladder",
};

const ASKED_AGAIN = {
  missing_completion_marker: "The answer did not end with the completion marker. Asked again.",
  decision_format: "The decision was not in the required form. Asked again.",
  approved_unread: "It approved a change it was shown only part of, without opening a file. Asked to read it.",
};

const NEXT_ATTEMPT = {
  resume: "Continuing the same session",
  replay: "Sending the prompt again",
  session_dropped: "Starting a new session",
};

const BY_HAND = {
  "human.task_completed": "Marked done by hand",
  "human.task_reopened": "Reopened",
  "human.task_cancelled": "Cancelled",
  "human.task_blocked": "Blocked",
  "human.task_unblocked": "Unblocked",
  "human.task_accepted": "Accepted",
  "human.task_declined": "Declined",
  "human.task_planned": "Planned into a sprint",
  "human.task_unplanned": "Moved back to the backlog",
  "human.task_deleted": "Deleted",
};

const FILE_VERB = { Read: "Read", Write: "Wrote", Edit: "Edited", NotebookEdit: "Edited" };

/** A path inside a task's working copy, without the working copy in front of it. */
export function shortPath(path) {
  const text = String(path ?? "");
  const cut = text.match(/\/worktrees\/[^/]+\/(.+)$/);
  return cut ? cut[1] : text;
}

function clip(text, length = 200) {
  const value = String(text ?? "");
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

function compact(value) {
  if (value === null || value === undefined) return "";
  if (typeof value !== "object") return String(value);
  return Object.keys(value).length ? clip(JSON.stringify(value)) : "";
}

function join(parts, separator = " · ") {
  return parts.filter(Boolean).join(separator);
}

function toolUse(d) {
  const input = d.input ?? {};
  if (d.tool === "Grep") {
    return { says: "Searched for", mono: join([input.pattern, input.path ? `in ${shortPath(input.path)}` : ""], " ") };
  }
  if (d.tool === "Glob") return { says: "Looked for files", mono: String(input.pattern ?? "") };
  return { says: `Used ${d.tool || "a tool"}`, mono: compact(input) };
}

/**
 * One line of a run's story as `{ says, mono, body, tone, prose }`, or null
 * for bookkeeping. `says` is a sentence; `mono` a command, path or pattern
 * shown beside it; `body` longer text under it (`prose` when it is the
 * agent's own words, not output).
 */
export function sayEntry(entry) {
  const kind = entry.kind;
  const d = entry.data ?? {};
  if (SILENT.has(kind)) return null;
  switch (kind) {
    case "workflow.step_started": {
      const again = d.retry_attempt ? ", asked again" : d.visit_count > 1 ? `, attempt ${d.visit_count}` : "";
      return { says: `Started ${humanize(d.step)}${again}` };
    }
    case "workflow.model_selected": {
      const source = MODEL_SOURCE[d.source] ?? (d.source ? humanize(d.source).toLowerCase() : "");
      return { says: join([`Model: ${d.model || "the runner's default"}`, source], ", ") };
    }
    case "engine.role_policy": {
      if (d.allowed_tools?.length) return { says: `May use: ${d.allowed_tools.join(", ")}` };
      if (d.disallowed_tools?.length) return { says: `May use every tool except ${d.disallowed_tools.join(", ")}` };
      return { says: "May use every tool" };
    }
    case "agent.started":
      return { says: "Agent started", mono: d.command };
    case "agent.message":
      return d.text ? { body: d.text, prose: true } : null;
    case "agent.command":
      return { says: "Ran", mono: d.command };
    case "agent.file_change":
      return { says: FILE_VERB[d.tool] ?? `${d.tool || "Changed"}`, mono: shortPath(d.path) };
    case "agent.tool_use":
      return toolUse(d);
    case "agent.tool_result":
      // What came back follows the line that asked for it; only a failure
      // needs saying.
      if (!d.is_error && !d.preview) return null;
      return {
        says: d.is_error ? "It failed" : "",
        // Blank lines before the first line of output say nothing.
        body: String(d.preview || "").replace(/^(\s*\n)+/, "").trimEnd(),
        tone: d.is_error ? "failed" : null,
        clamp: true,
      };
    case "agent.completed":
      return {
        says: join([
          d.duration_ms ? `Finished in ${formatDuration(d.duration_ms / 1000)}` : "Finished",
          d.token_count ? `${formatTokens(d.token_count)} tokens` : "",
          d.cost_usd ? formatMoney(d.cost_usd) : "",
        ]),
      };
    case "agent.error":
      return {
        says: d.quota_exhausted ? "Stopped by the account's usage limit" : "Failed",
        body: d.error || "",
        tone: "failed",
      };
    case "agent.infra_error":
      return {
        says: join(
          [
            "Interrupted",
            NEXT_ATTEMPT[d.next_attempt] ? `${NEXT_ATTEMPT[d.next_attempt]} in ${d.retry_in_seconds} s` : "",
          ],
          ". ",
        ),
        body: d.error || "",
        tone: "failed",
      };
    case "agent.killed":
      return { says: `Stopped: ${d.reason || "by the engine"}`, tone: "failed" };
    case "agent.rate_limit":
      return { says: join([`Usage limit${d.rate_limit_type ? ` (${humanize(d.rate_limit_type).toLowerCase()})` : ""}`, d.status], ": ") };
    case "engine.test_started":
      return { says: "Running the tests", mono: d.command };
    case "engine.test_run": {
      const passed = d.exit_code === 0;
      return {
        says: join(
          [
            passed ? "Tests passed" : `Tests failed${d.exit_code === null || d.exit_code === undefined ? "" : ` (exit code ${d.exit_code})`}`,
            d.duration_seconds !== undefined && d.duration_seconds !== null ? `in ${formatDuration(d.duration_seconds)}` : "",
            d.head_sha ? `at ${shortSha(d.head_sha)}` : "",
          ],
          " ",
        ),
        tone: passed ? "passed" : "failed",
      };
    }
    case "engine.review_recorded":
      return { says: join([`Review recorded: ${outcomeWord(d.outcome)}`, d.head_sha ? `at ${shortSha(d.head_sha)}` : ""], " "), tone: outcomeTone(d.outcome) };
    case "engine.merge":
      return { says: join([`Merged into ${d.target}`, d.sha ? `at ${shortSha(d.sha)}` : ""], " "), mono: d.branch, tone: "passed" };
    case "engine.push":
      return { says: `Pushed ${d.branch} to ${d.remote}` };
    case "engine.push_failed":
      return { says: `Merged, but not pushed to ${d.remote}`, body: d.error || "", tone: "failed" };
    case "engine.merge_conflict":
      return { says: `Merge conflict with ${d.target}`, body: d.error || "", tone: "failed", clamp: true };
    case "engine.merge_failed":
      return { says: "The merge failed", body: d.error || "", tone: "failed", clamp: true };
    case "engine.branch_sync":
      return {
        says: join(["Brought the branch up to date", d.commits_behind ? `it was ${plural(d.commits_behind, "commit")} behind` : ""], ": "),
        body: d.detail || "",
        clamp: true,
      };
    case "engine.branch_sync_conflict":
      return { says: "Could not bring the branch up to date: conflict", body: d.detail || "", tone: "failed", clamp: true };
    case "workflow.step_completed":
      return { says: `${humanize(d.step)} ended: ${outcomeWord(d.outcome)}`, tone: outcomeTone(d.outcome) };
    case "workflow.transition":
      return { says: `Next step: ${humanize(d.to_step)}` };
    case "workflow.paused":
      return {
        says: d.reason === "human_gate" ? `Waiting for a person: ${humanize(d.policy || d.step).toLowerCase()}` : `Paused: ${humanize(d.reason).toLowerCase()}`,
      };
    case "workflow.resumed":
      return {
        says: `A person ${d.decision === "approve" ? "approved" : "sent it back"}. Next step: ${humanize(d.next_step)}`,
      };
    case "workflow.no_transition":
      return { says: `Nothing follows "${d.outcome}" at ${humanize(d.step)}. The task stopped.`, tone: "failed" };
    case "workflow.step_visit_reset":
      return { says: `Attempts at ${humanize(d.to_step)} are counted from the start again` };
    case "engine.output_contract_retry":
      return { says: ASKED_AGAIN[d.reason] ?? `Asked again: ${humanize(d.reason).toLowerCase()}` };
    case "engine.quota_exhausted":
      return { says: "Stopped by the account's usage limit. The task keeps its place.", body: d.error || "", tone: "failed" };
    case "engine.worktree_removed":
      return { says: "Working copy removed" };
    case "engine.attention_needed":
      return { says: `Needs a person: ${humanize(d.trigger).toLowerCase()}` };
    case "engine.task_created":
      return { says: "Filed a task", body: d.title || "", prose: true };
    case "signal.progress":
      return { says: "Reported progress", body: d.message || "", prose: true };
    case "signal.blocker":
      return { says: "Reported a blocker", body: d.message || "", prose: true, tone: "failed" };
    case "human.message":
      return { says: "A person wrote guidance", body: d.text || "", prose: true };
    case "human.message_delivered":
      return { says: "The guidance reached the agent" };
    case "engine.command_applied":
    case "engine.command_rejected":
      return {
        says: `Engine command ${humanize(d.command).toLowerCase()} ${kind.endsWith("applied") ? "applied" : "refused"}`,
        body: d.detail || "",
        prose: true,
      };
    case "task.completed":
      return { says: "Task done", tone: "passed" };
    default:
      if (BY_HAND[kind]) {
        return { says: join([BY_HAND[kind], d.by ? `by ${d.by}` : ""], " "), body: d.reason || "", prose: true };
      }
      // Not known here: its name and what it recorded, as recorded.
      return { says: humanize(kind.replace(".", " ")), mono: compact(entry.data) || entry.text || "" };
  }
}

/**
 * A run's story, oldest first: one line per event worth reading, consecutive
 * lines of test output gathered into one block, and the closing message
 * dropped when it only repeats the one before it.
 */
export function narrate(transcript) {
  const lines = [];
  let lastMessage = null;
  for (const entry of transcript ?? []) {
    if (entry.kind === "engine.test_output" || entry.kind === "agent.raw_output") {
      const previous = lines[lines.length - 1];
      if (previous?.output && previous.kind === entry.kind) previous.body += `\n${entry.text}`;
      else if (entry.text.trim()) lines.push({ at: entry.at, kind: entry.kind, output: true, body: entry.text });
      continue;
    }
    if (entry.kind === "agent.message") {
      const text = entry.data?.text ?? "";
      if (text && text === lastMessage) continue;
      lastMessage = text;
    }
    const said = sayEntry(entry);
    if (said) lines.push({ at: entry.at, kind: entry.kind, ...said });
  }
  return lines;
}
