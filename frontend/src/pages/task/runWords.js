// What a run recorded, said in words. The API gives each event's kind and
// facts; nothing here is invented. A run's story is one kind of line: a
// time, what happened, and what it ran, wrote or printed (owner, 2026-11-22).
// What the step's facts say (model, tools, how it ended, the next step) and
// events this file has no words for are left out of the story; the
// transcript a person can download keeps everything.

import { formatDuration, humanize, plural, shortSha } from "../../ui/format";
import { modelSourceWords, outcomeTone, outcomeWord, testRunSentence } from "../shared/activityWords";

/** Bookkeeping the engine records for itself; it tells a reader nothing. */
const SILENT = new Set([
  "engine.context_write",
  "agent.session",
  "agent.cost_update",
  "policy.resolved",
  // The engine records the same task as `engine.task_created`.
  "signal.task_created",
  // What the step's facts say: its model, what it may use, how it was
  // started, how it ended, how long it took, what came next.
  "workflow.step_started",
  "workflow.model_selected",
  "engine.role_policy",
  "agent.started",
  "agent.completed",
  "engine.review_recorded",
  // What the step changed is said in its facts.
  "engine.step_changes",
  "engine.step_reads",
  "workflow.step_completed",
  "workflow.transition",
]);

/** The words a role answers with so Foreman can read it: a decision first, a completion marker last. */
const DECISION = /^\s*(?:(?:Decision|Verdict):\s*)?(?:APPROVE|DENY|STEER|ESCALATE)(?![A-Za-z])[:.\s-]*/;
const MARKER = /^[A-Z][A-Z0-9_]{2,}$/;

/** What an agent wrote, without the decision word it opens with or the marker it ends with. */
export function ownWords(text) {
  const lines = String(text ?? "").replace(/\s+$/, "").split("\n");
  if (lines.length && MARKER.test(lines[lines.length - 1].trim())) lines.pop();
  return lines.join("\n").replace(DECISION, "").trim();
}

/** What a tool says when the role was not given it: "No such tool available: Bash". */
const REFUSED_TOOL = /No such tool available:\s*([\w-]+)/;

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
  // A user's holds (ADR-0043).
  "human.task_paused": "Paused",
  "human.task_stopped": "Stopped",
  "human.task_resumed": "Resumed",
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

/** What a tool was given, as its values: never as JSON. */
function compact(value) {
  if (value === null || value === undefined) return "";
  if (typeof value !== "object") return String(value);
  const values = Object.values(value).filter((item) => typeof item === "string" || typeof item === "number");
  return clip(values.join(" "));
}

/** The headings a document change names, after its path: ", 6" or ", 6 and 7"; nothing for the whole file. */
function documentHeadings(d) {
  const headings = (Array.isArray(d.headings) ? d.headings : [d.heading]).filter(Boolean);
  if (!headings.length) return "";
  return `, ${headings.length > 1 ? `${headings.slice(0, -1).join(", ")} and ${headings[headings.length - 1]}` : headings[0]}`;
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
 * when it is not a line. `says` is what happened; `mono` a command, path or
 * pattern it ran or opened; `body` longer text under it: someone's own
 * words (`prose`), or what a program printed.
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
      const source = modelSourceWords(d);
      return { says: join([`Model: ${d.model || "the runner's default"}`, source], ", ") };
    }
    case "engine.role_policy": {
      if (d.no_tools) return { says: "May use no tool" };
      if (d.allowed_tools?.length) return { says: `May use: ${d.allowed_tools.join(", ")}` };
      if (d.disallowed_tools?.length) return { says: `May use every tool except ${d.disallowed_tools.join(", ")}` };
      return { says: "May use every tool" };
    }
    case "agent.started":
      return { says: "Agent started", mono: d.command };
    case "agent.message": {
      const words = ownWords(d.text);
      return words ? { body: words, prose: true } : null;
    }
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
      if (d.is_error && REFUSED_TOOL.test(d.preview || "")) {
        return { says: `Not run: this role may not use ${(d.preview || "").match(REFUSED_TOOL)[1]}` };
      }
      return {
        says: d.is_error ? "It failed" : "",
        // Blank lines before the first line of output say nothing.
        body: String(d.preview || "").replace(/^(\s*\n)+/, "").trimEnd(),
        tone: d.is_error ? "failed" : null,
      };
    case "agent.completed":
      return {
        says: d.duration_ms ? `Finished in ${formatDuration(d.duration_ms / 1000)}` : "Finished",
        spend: { amount: d.cost_usd, tokens: d.token_count },
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
      // "allowed" and "allowed_warning" only say the account may go on.
      if (String(d.status || "").startsWith("allowed")) return null;
      return { says: `Stopped by the account's usage limit${d.rate_limit_type ? ` (${humanize(d.rate_limit_type).toLowerCase()})` : ""}`, tone: "failed" };
    case "engine.test_started":
      return { says: "Ran", mono: d.command };
    case "engine.test_run": {
      const passed = d.exit_code === 0;
      return {
        says: testRunSentence({ passed, exitCode: d.exit_code, report: d.report, seconds: d.duration_seconds, sha: d.head_sha }),
        tone: passed ? "passed" : "failed",
      };
    }
    case "engine.review_recorded":
      return { says: join([`Review recorded: ${outcomeWord(d.outcome)}`, d.head_sha ? `at ${shortSha(d.head_sha)}` : ""], " "), tone: outcomeTone(d.outcome) };
    case "engine.merge":
      return { says: join([`Merged into ${d.target}`, d.sha ? `at ${shortSha(d.sha)}` : ""], " "), mono: d.branch, tone: "passed" };
    case "engine.push":
      return { says: `Pushed ${d.tag ? `the tag ${d.tag}` : d.branch} to ${d.remote}` };
    case "engine.push_failed":
      return d.tag
        ? { says: `Tagged, but the tag ${d.tag} was not pushed to ${d.remote}`, body: d.error || "", tone: "failed" }
        : { says: `Merged, but not pushed to ${d.remote}`, body: d.error || "", tone: "failed" };
    case "engine.checkout_updated":
      return { says: `Brought the project's folder to ${d.branch} at ${shortSha(d.sha)}`, mono: d.path };
    case "engine.checkout_behind":
      return { says: `The project's folder still shows an older ${d.branch}`, mono: d.path, body: d.reason || "", tone: "failed" };
    case "engine.merge_conflict":
      return { says: `Merge conflict with ${d.target}`, body: d.error || "", tone: "failed" };
    case "engine.merge_failed":
      return { says: "The merge failed", body: d.error || "", tone: "failed" };
    case "engine.branch_sync":
      return {
        says: join(["Brought the branch up to date", d.commits_behind ? `it was ${plural(d.commits_behind, "commit")} behind` : ""], ": "),
        body: d.detail || "",
      };
    case "engine.branch_sync_conflict":
      return { says: "Could not bring the branch up to date: conflict", body: d.detail || "", tone: "failed" };
    case "workflow.step_completed":
      return { says: `${humanize(d.step)} ended: ${outcomeWord(d.outcome)}`, tone: outcomeTone(d.outcome) };
    case "workflow.transition":
      return { says: `Next step: ${humanize(d.to_step)}` };
    case "workflow.paused":
      return {
        says: d.reason === "human_gate" ? `Waiting for a user: ${humanize(d.policy || d.step).toLowerCase()}` : `Paused: ${humanize(d.reason).toLowerCase()}`,
      };
    case "workflow.resumed":
      return { says: `A user ${d.decision === "approve" ? "approved" : "sent it back"}` };
    case "workflow.gate_auto_approved":
      return { says: "Approved without asking anyone" };
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
      return { says: `Needs a user: ${humanize(d.trigger).toLowerCase()}` };
    case "engine.document_changed":
      return {
        says: `${d.path}${documentHeadings(d)} changed in ${d.merged_task_key ? `${d.merged_task_key}'s` : "another task's"} merge (${shortSha(d.merge_sha)}) since this task named it at ${(Array.isArray(d.named_commits) && d.named_commits.length ? d.named_commits : [d.named_commit]).map(shortSha).join(" and ")}`,
      };
    case "engine.task_created":
      return { says: "Filed a task", body: d.title || "", prose: true };
    case "signal.progress":
      return { says: "Reported progress", body: d.message || "", prose: true };
    case "signal.blocker":
      return { says: "Reported a blocker", body: d.message || "", prose: true, tone: "failed" };
    case "human.message":
      return { says: "A user wrote guidance", body: d.text || "", prose: true };
    case "human.message_delivered":
      return { says: "The guidance reached the agent" };
    case "engine.command_applied":
    case "engine.command_rejected":
      return {
        says: `Engine command ${humanize(d.command).toLowerCase()} ${kind.endsWith("applied") ? "applied" : "refused"}`,
        body: d.detail || "",
        prose: true,
      };
    case "engine.task_stopped":
      return { says: join(["The step was cut", d.requested_by ? `on a Stop by ${d.requested_by}` : ""], " ") };
    case "task.completed":
      return { says: "Task done", tone: "passed" };
    default:
      if (BY_HAND[kind]) {
        return { says: join([BY_HAND[kind], d.by ? `by ${d.by}` : ""], " "), body: d.reason || "", prose: true };
      }
      // Not known here: not a line. The downloaded transcript keeps it.
      return null;
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
