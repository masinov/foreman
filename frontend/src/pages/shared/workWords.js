import { formatDay, humanize } from "../../ui/format";

// The status line of a sprint's work (ADR-0043 §6): one line, the same on
// every page that shows it, with no name in it. Fixed words, task keys,
// steps and times; who, why and the full time are in `detail`.

const clockFormat = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

/** "14:02" on the day it was set, "24 Nov" after it. */
export function whenSet(timestamp, now = new Date()) {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  return sameDay ? clockFormat.format(date) : formatDay(timestamp, now);
}

function step(name) {
  return name ? humanize(name) : "";
}

function joined(...parts) {
  return parts.filter(Boolean).join(" · ");
}

/**
 * `{ tone, text, detail }` for a sprint's `work` (the API's status line), or
 * for no active sprint (`null`). `detail` is who, why and when, for a hover
 * or a tap.
 */
export function workWords(work, now = new Date()) {
  const state = work?.state ?? "not_started";
  const at = whenSet(work?.at, now);
  const who = work?.by ? `by ${work.by}` : "";
  let result;
  switch (state) {
    case "blocked":
      result = {
        tone: "attention",
        text: work.scope === "workspace" ? "Blocked · workspace" : joined("Blocked", work.ready_to_finish ? "ready to finish" : at),
        detail: joined(`Blocked ${who}`.trim(), work.reason),
      };
      break;
    case "stopping":
      result = { tone: "running", text: joined("Stopping", step(work.step)), detail: work.task_key || "" };
      break;
    case "pausing":
      result = { tone: "running", text: joined("Pausing", `${step(work.step)} finishing`.trim()), detail: work.task_key || "" };
      break;
    case "stopped":
      result = {
        tone: "idle",
        text: joined("Stopped", at),
        detail: joined(`Stopped ${who}`.trim(), "the cut step runs again on Resume"),
      };
      break;
    case "paused":
      result = { tone: "idle", text: joined("Paused", at), detail: `Paused ${who}`.trim() };
      break;
    case "working":
      result = {
        tone: "running",
        text: joined("Working", `${work.task_key || ""} ${step(work.step)}`.trim(), work.paused ? `${work.paused} paused` : ""),
        detail: "",
      };
      break;
    case "some_paused":
      result = { tone: "idle", text: `${work.paused} paused`, detail: "" };
      break;
    case "ready_to_finish":
      result = { tone: "attention", text: "Ready to finish", detail: "Every task is done or cancelled." };
      break;
    case "waiting":
      result = { tone: "idle", text: "Waiting", detail: "" };
      break;
    default:
      result = { tone: "idle", text: "Not started", detail: "" };
  }
  if (work?.no_worker) {
    result = { ...result, text: joined(result.text, "no worker"), detail: joined(result.detail, "No worker runs this project.") };
  }
  return result;
}

/** Which controls apply to a sprint's work: Pause, Stop, Resume, Block, Unblock. */
export function workControls(work, { planned = false } = {}) {
  const blocked = work?.state === "blocked";
  const blockedHere = blocked && work?.scope === "sprint";
  const paused = work?.paused ?? 0;
  const unfinished = work?.unfinished ?? 0;
  return {
    pause: !blocked && unfinished - paused > 0,
    stop: !blocked && Boolean(work?.step_running) && work?.state !== "stopping",
    resume: paused > 0 && !blocked,
    block: !blocked && (planned || work?.state !== "ready_to_finish"),
    unblock: blockedHere,
  };
}

/** A toast for what a Pause, Stop or Resume changed, by task key. */
export function changedSentence(verb, keys = []) {
  if (!keys.length) return `${verb}.`;
  const shown = keys.slice(0, 3);
  const more = keys.length - shown.length;
  const list = shown.length === 1 ? shown[0] : `${shown.slice(0, -1).join(", ")} and ${shown[shown.length - 1]}`;
  return more > 0 ? `${verb} ${shown.join(", ")} and ${more} more.` : `${verb} ${list}.`;
}
