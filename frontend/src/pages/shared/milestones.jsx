import React from "react";

import { MILESTONE_KINDS } from "../../api/milestones";
import { paths } from "../../app/paths";
import { plural, shortSha, splitTitle } from "../../ui/format";
import { ActivityTable } from "./ActivityTable";
import { userName } from "./activityWords";

const K = MILESTONE_KINDS;

// What happened, per kind: the phrase, its colour, and why when there is one.
const EVENTS = {
  [K.sprintStarted]: () => ({ word: "Started", tone: "idle" }),
  [K.sprintFinished]: (m) => finishedEvent(m),
  [K.planConfirmed]: (m) => ({ word: "Plan confirmed", tone: "idle", why: m.detail || "" }),
  [K.engineStarted]: () => ({ word: "Started", tone: "idle" }),
  [K.engineStopped]: () => ({ word: "Stopped", tone: "idle" }),
  [K.engineLost]: () => ({
    word: "Died",
    tone: "failed",
    why: "It stopped without a word: killed, crashed, or the machine went down. Whatever it was doing stopped there.",
  }),
  [K.enginePaused]: () => ({ word: "Paused", tone: "idle" }),
  [K.engineResumed]: () => ({ word: "Resumed", tone: "idle" }),
};

/**
 * A finished sprint: "Finished", or "Finished, not tagged" when its tag could
 * not be made (spec 6.4, ADR-0036). On hover, how many tasks it merged and its
 * tag ("3 tasks merged, tagged checkpoint-20261120-sprint-2 at 6f79f4a") or
 * why there is none. A sprint finished before tagging existed says only what
 * it merged.
 */
function finishedEvent(m) {
  const merged = m.merged_count === null || m.merged_count === undefined ? "" : `${plural(m.merged_count, "task")} merged`;
  const checkpoint = m.checkpoint ?? null;
  const said = (more) => [merged, more].filter(Boolean).join(", ");
  if (checkpoint?.problem) {
    return { word: "Finished, not tagged", tone: "failed", why: said(`not tagged: ${checkpoint.problem}`) };
  }
  const tagged = checkpoint?.tag ? `tagged ${checkpoint.tag} at ${shortSha(checkpoint.sha)}` : "";
  return { word: "Finished", tone: "passed", why: said(tagged) };
}

const isEngine = (m) => String(m.kind).startsWith("engine_");

/** A milestone as a row of the activity table: a sprint or the engine, and what happened to it. */
export function describeMilestone(m) {
  const [name, rest] = splitTitle(m.sprint_title || m.sprint_id || "");
  const event = (EVENTS[m.kind] ?? (() => ({ word: m.kind, tone: "idle" })))(m);
  return {
    at: m.at,
    project: m.project_name,
    subject: isEngine(m) ? { key: "Engine", title: "" } : { key: name, title: rest },
    event,
    by: m.actor ? userName(m.actor) : "",
    href: !isEngine(m) && m.sprint_id ? paths.sprint(m.sprint_id) : null,
  };
}

/** A milestone in a few words, for the workspace's Last change: "Sprint 2 finished", "Engine stopped". */
export function milestoneSentence(m) {
  const { event } = describeMilestone(m);
  const [name] = splitTitle(m.sprint_title || m.sprint_id || "");
  if (m.kind === K.planConfirmed) return `Plan for ${name} confirmed`;
  return `${isEngine(m) ? "Engine" : name} ${event.word.toLowerCase()}`;
}

/** Milestones, newest first, as every activity list shows them. */
export function MilestoneTable({ caption, items, showProject = false, placeholderRows = null }) {
  return (
    <ActivityTable
      caption={caption}
      items={items}
      describe={describeMilestone}
      keyHeader="About"
      wideKey
      subjectHeader="Title"
      showProject={showProject}
      rowKey={(m) => `${m.kind}:${m.at}:${m.project_id}:${m.sprint_id ?? ""}`}
      placeholderRows={placeholderRows}
    />
  );
}
