import React from "react";

import { MILESTONE_KINDS } from "../../api/milestones";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Mono } from "../../ui/Mono";
import { Table } from "../../ui/Table";
import { formatDay, splitTitle } from "../../ui/format";

const ENGINE_VERBS = {
  [MILESTONE_KINDS.engineStarted]: "started",
  [MILESTONE_KINDS.enginePaused]: "paused",
  [MILESTONE_KINDS.engineResumed]: "resumed",
  [MILESTONE_KINDS.engineStopped]: "stopped",
};

// A finished sprint says how many tasks it merged; a sprint without a count
// says nothing rather than guess.
function sprintDetail(milestone) {
  if (milestone.kind !== MILESTONE_KINDS.sprintFinished) return null;
  const count = milestone.merged_count;
  if (count === null || count === undefined) return null;
  return `${count} ${count === 1 ? "task" : "tasks"} merged`;
}

/**
 * What a milestone says: `{ kind, text, href }`. `kind` is the one-word
 * group (Sprint, Merge, Engine); `short` drops a sprint title's subtitle.
 */
export function describeMilestone(milestone, { short = false } = {}) {
  switch (milestone.kind) {
    case MILESTONE_KINDS.sprintStarted:
    case MILESTONE_KINDS.sprintFinished: {
      const [head, rest] = splitTitle(milestone.sprint_title || milestone.sprint_id);
      const verb = milestone.kind === MILESTONE_KINDS.sprintStarted ? "started" : "finished";
      return {
        kind: "Sprint",
        text: `${head} ${verb}${rest && !short ? `: ${rest}` : ""}`,
        detail: sprintDetail(milestone),
        mono: false,
        href: milestone.sprint_id ? paths.sprint(milestone.sprint_id) : null,
      };
    }
    case MILESTONE_KINDS.taskMerged: {
      const key = milestone.task_key || milestone.task_id;
      return {
        kind: "Merge",
        text: short || !milestone.task_title ? `${key} merged` : `${key} merged: ${milestone.task_title}`,
        detail: milestone.sha ? milestone.sha.slice(0, 7) : null,
        mono: true,
        href: milestone.task_id ? paths.task(milestone.task_id) : null,
      };
    }
    default: {
      const verb = ENGINE_VERBS[milestone.kind] ?? "changed";
      return {
        kind: "Engine",
        text: `Engine ${verb}${milestone.actor ? ` by ${milestone.actor}` : ""}`,
        detail: null,
        mono: false,
        href: null,
      };
    }
  }
}

export function MilestoneText({ milestone, short = false }) {
  const { text, href, detail, mono } = describeMilestone(milestone, { short });
  const label = href ? (
    <Link className="row-link" href={href}>
      {text}
    </Link>
  ) : (
    <span>{text}</span>
  );
  if (short || !detail) return label;
  return (
    <>
      {label}{" "}
      {mono ? (
        <Mono quiet title="Merge commit">
          {detail}
        </Mono>
      ) : (
        <span className="milestones__detail">{detail}</span>
      )}
    </>
  );
}

/** Milestones, newest first: when, (project,) kind, what happened. */
export function MilestoneTable({ caption, items, showProject = false, placeholderRows = null }) {
  const columns = [
    {
      key: "when",
      header: "When",
      className: "milestones__when",
      render: (m) => <Mono quiet>{formatDay(m.at)}</Mono>,
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
    { key: "what", header: "Milestone", render: (m) => <MilestoneText milestone={m} /> },
  ].filter(Boolean);
  return (
    <Table
      caption={caption}
      columns={columns}
      rows={items ?? []}
      rowKey={(m) => `${m.kind}:${m.at}:${m.sprint_id ?? ""}:${m.task_id ?? ""}`}
      hideHeader
      placeholderRows={placeholderRows}
      className="milestones"
    />
  );
}
