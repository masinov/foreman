import React from "react";

import { MILESTONE_KINDS } from "../../api/milestones";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Mono } from "../../ui/Mono";
import { Table } from "../../ui/Table";
import { formatDay, formatDayTime, formatDuration, formatMoney, humanize, plural, splitTitle } from "../../ui/format";
import { FOREMAN } from "./activityWords";

const K = MILESTONE_KINDS;

const clock = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

/** "21:33", or "19 Nov, 21:33" when it is another day than `from`. */
function timeOf(timestamp, from = null) {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  if (from && formatDay(from) !== formatDay(timestamp)) return formatDayTime(timestamp);
  return clock.format(date);
}

function secondsBetween(start, end) {
  const a = new Date(start).getTime();
  const b = new Date(end).getTime();
  return Number.isNaN(a) || Number.isNaN(b) ? null : Math.max(0, (b - a) / 1000);
}

/** The first sentence of a reason, which is what fits beside a milestone. */
function firstSentence(text) {
  const line = String(text || "").trim().split("\n")[0].trim();
  const end = line.search(/[.!?](\s|$)/);
  return end > 0 ? line.slice(0, end + 1) : line;
}

/** "ASS-16", the task's key or, without one, its id. */
const keyOf = (m) => m.task_key || m.task_id || "a task";

/** "Sprint 2". */
function sprintName(m) {
  return splitTitle(m.sprint_title || m.sprint_id || "a sprint")[0];
}

/** "Sprint 2 started", and with `full` the title's subtitle after it: "Sprint 2 started: weight of evidence". */
function sprintEvent(m, verb, full) {
  const [head, rest] = splitTitle(m.sprint_title || m.sprint_id || "a sprint");
  return `${head} ${verb}${rest && full ? `: ${rest}` : ""}`;
}

// What sent a task back, as the project's log says it to anyone reading.
const CAUSE_WORDS = { review: "review", tests: "tests", person: "a person", merge_conflict: "merge conflict", other: "other" };

/** A merge's story: "after 1 send-back (review) · 15 min · $0.45", or "first time · …". */
function mergeDetail(merge) {
  if (!merge) return null;
  const causes = Object.entries(merge.send_back_causes ?? {})
    .map(([cause, count]) => {
      const word = CAUSE_WORDS[cause] ?? humanize(cause).toLowerCase();
      return count > 1 ? `${word} ${count}` : word;
    })
    .join(", ");
  const how = merge.send_backs ? `after ${plural(merge.send_backs, "send-back")}${causes ? ` (${causes})` : ""}` : "first time";
  const took = merge.minutes_to_merge !== null && merge.minutes_to_merge !== undefined ? formatDuration(merge.minutes_to_merge * 60) : "";
  return [how, took, merge.cost_usd ? formatMoney(merge.cost_usd) : ""].filter(Boolean).join(" · ");
}

/** Why a task was blocked, said by what blocked it. */
function blockDetail(m) {
  const detail = firstSentence(m.detail);
  switch (m.how) {
    case "agent":
      return detail ? `The agent: ${detail}` : "The agent said it cannot go on";
    case "loop_limit":
      return `${humanize(m.detail || "A step")} ran as many times as the workflow allows`;
    case "no_transition":
      return `The workflow has no way on from ${humanize(m.detail || "the step").toLowerCase()}`;
    default:
      return detail || null;
  }
}

/** An engine's time: "Engine ran 21:33–21:59 (26 min), stopped by masis". */
function engineText(m) {
  const start = timeOf(m.at);
  if (m.kind === K.engineRun && !m.ended_at) return `Engine running since ${start}`;
  const took = formatDuration(secondsBetween(m.at, m.ended_at));
  const span = `${start}–${timeOf(m.ended_at, m.at)}${took ? ` (${took})` : ""}`;
  if (m.kind === K.engineLost) return `Engine stopped without a word after ${span}`;
  return `Engine ran ${span}${m.actor ? `, stopped by ${m.actor}` : ""}`;
}

/**
 * What a milestone says: `{ kind, text, detail, sha, tone, href }`. `kind` is
 * the one-word group shown in its column; `short` drops what only fits in a
 * full row (a sprint's subtitle, a task's title, the detail).
 */
export function describeMilestone(milestone, { short = false } = {}) {
  const m = milestone;
  const taskHref = m.task_id ? paths.task(m.task_id) : null;
  const titled = (text) => (short || !m.task_title ? text : `${text}: ${m.task_title}`);
  switch (m.kind) {
    case K.sprintStarted:
      return { kind: "Sprint", text: sprintEvent(m, "started", !short), href: m.sprint_id ? paths.sprint(m.sprint_id) : null };
    case K.sprintFinished:
      return {
        kind: "Sprint",
        text: sprintEvent(m, "finished", !short),
        detail: m.merged_count === null || m.merged_count === undefined ? null : `${plural(m.merged_count, "task")} merged`,
        href: m.sprint_id ? paths.sprint(m.sprint_id) : null,
      };
    case K.planConfirmed:
      return {
        kind: "Plan",
        text: `Plan${m.sprint_id ? ` for ${sprintName(m)}` : ""} confirmed${m.actor ? ` by ${m.actor}` : ""}`,
        detail: firstSentence(m.detail) || null,
        href: m.sprint_id ? paths.sprint(m.sprint_id) : null,
      };
    case K.taskMerged:
      return { kind: "Merge", text: titled(`${keyOf(m)} merged`), detail: mergeDetail(m.merge), sha: m.sha, href: taskHref };
    case K.taskBlocked:
      return { kind: "Problem", tone: "attention", text: titled(`${keyOf(m)} blocked`), detail: blockDetail(m), href: taskHref };
    case K.taskUnblocked:
      return { kind: "Person", text: `${keyOf(m)} unblocked by ${m.actor || "a person"}`, detail: firstSentence(m.detail) || null, href: taskHref };
    case K.taskClosed:
      return { kind: "Person", text: `${keyOf(m)} closed by hand by ${m.actor || "a person"}`, detail: firstSentence(m.detail) || null, href: taskHref };
    case K.taskCancelled:
      return { kind: "Person", text: `${keyOf(m)} cancelled by ${m.actor || "a person"}`, detail: firstSentence(m.detail) || null, href: taskHref };
    case K.decisionMade: {
      const decision = m.how === "approve" ? "approved" : m.how === "deny" ? "sent back" : humanize(m.how).toLowerCase();
      return { kind: "Person", text: `${keyOf(m)} ${humanize(m.detail || "gate").toLowerCase()}: ${decision} by a person`, href: taskHref };
    }
    case K.engineRun:
      return { kind: "Engine", text: engineText(m), href: null };
    case K.engineLost:
      return { kind: "Problem", tone: "attention", text: engineText(m), detail: "The engine died or was killed; whatever it was doing stopped there.", href: null };
    case K.enginePaused:
    case K.engineResumed:
      return {
        kind: "Engine",
        text: `Engine ${m.kind === K.enginePaused ? "paused" : "resumed"}${m.actor ? ` by ${m.actor}` : ""}`,
        href: null,
      };
    default:
      return { kind: FOREMAN, text: humanize(m.kind), href: null };
  }
}

export function MilestoneText({ milestone, short = false }) {
  const { text, href, detail, sha, tone } = describeMilestone(milestone, { short });
  const label = href ? (
    <Link className={`row-link${tone ? ` tone-${tone}` : ""}`} href={href}>
      {text}
    </Link>
  ) : (
    <span className={tone ? `tone-${tone}` : undefined}>{text}</span>
  );
  if (short || (!detail && !sha)) return label;
  return (
    <>
      {label}
      {sha ? (
        <>
          {" "}
          <Mono quiet title="Merge commit">
            {sha.slice(0, 7)}
          </Mono>
        </>
      ) : null}
      {detail ? (
        <>
          {" "}
          <span className="milestones__detail" title={detail}>
            {detail}
          </span>
        </>
      ) : null}
    </>
  );
}

/**
 * Milestones, newest first: when, (project,) kind, what happened. The whole
 * row leads to what it is about: the sprint, or the task.
 */
export function MilestoneTable({ caption, items, showProject = false, placeholderRows = null }) {
  const columns = [
    {
      key: "when",
      header: "When",
      className: "milestones__when",
      render: (m) => <Mono quiet>{formatDayTime(m.at)}</Mono>,
    },
    showProject
      ? {
          key: "project",
          header: "Project",
          className: "milestones__project",
          render: (m) => (
            <Link className="row-link" href={paths.project(m.project_id)}>
              {m.project_name}
            </Link>
          ),
        }
      : null,
    {
      key: "kind",
      header: "Kind",
      className: "milestones__kind",
      render: (m) => describeMilestone(m).kind,
    },
    { key: "what", header: "What happened", className: "milestones__what", render: (m) => <MilestoneText milestone={m} /> },
  ].filter(Boolean);
  return (
    <Table
      caption={caption}
      columns={columns}
      rows={items ?? []}
      rowKey={(m) => `${m.kind}:${m.at}:${m.sprint_id ?? ""}:${m.task_id ?? ""}`}
      rowHref={(m) => describeMilestone(m).href}
      placeholderRows={placeholderRows}
      className="milestones"
    />
  );
}
