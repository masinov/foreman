import React, { useState } from "react";

import { NEEDS_YOU_KINDS } from "../../api/workspace";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Surface } from "../../ui/Surface";
import { Table } from "../../ui/Table";
import { humanize, shortSha } from "../../ui/format";

// Design README: Needs you shows at most 5, with a way to see the rest.
export const NEEDS_YOU_CAP = 5;

const TESTS_WORDS = {
  passed: "tests passed",
  failed: "tests failed",
  stale: "tests stale",
  not_run: "tests not run",
};

function kindLabel(item) {
  switch (item.kind) {
    case NEEDS_YOU_KINDS.approval:
      // The task's human-gate step, by name. The API does not yet say whether
      // a gate approves a plan or a merge.
      return humanize(item.step) || "Approval";
    case NEEDS_YOU_KINDS.unblock:
      return "Unblock";
    case NEEDS_YOU_KINDS.accept:
      return "Accept filed work";
    case NEEDS_YOU_KINDS.sprintOrder:
      return "Sprint order";
    default:
      return humanize(item.kind);
  }
}

function Checked({ item }) {
  if (item.kind === NEEDS_YOU_KINDS.approval) {
    const evidence = item.evidence;
    if (!evidence) return <span className="quiet">Nothing checked yet</span>;
    const words = [];
    if (TESTS_WORDS[evidence.tests_status]) words.push(TESTS_WORDS[evidence.tests_status]);
    if (evidence.review_outcome) words.push(`review ${humanize(evidence.review_outcome).toLowerCase()}`);
    if (evidence.security_review_outcome) {
      words.push(`security review ${humanize(evidence.security_review_outcome).toLowerCase()}`);
    }
    const sha = shortSha(evidence.head_sha);
    return (
      <span className="quiet">
        {words.join(" · ")}
        {sha ? (
          <>
            {words.length ? " · " : ""}
            <Mono quiet>{sha}</Mono>
          </>
        ) : null}
      </span>
    );
  }
  if (item.kind === NEEDS_YOU_KINDS.unblock) {
    return <span className="quiet">{item.reason || "No reason recorded"}</span>;
  }
  if (item.kind === NEEDS_YOU_KINDS.accept) {
    return <span className="quiet">{item.source?.system ? `Filed by ${item.source.system}` : "Filed by a person"}</span>;
  }
  return <span className="quiet">{item.reason || ""}</span>;
}

function itemHref(item) {
  return item.taskId ? paths.task(item.taskId) : paths.project(item.projectId);
}

/**
 * Needs you, across every project: the one tinted surface on the page.
 */
export function NeedsYou({ items, placeholder, onApprove, approvingId, notice }) {
  const [expanded, setExpanded] = useState(false);
  const total = items ? items.length : null;
  const visible = items ? (expanded ? items : items.slice(0, NEEDS_YOU_CAP)) : [];

  const columns = [
    { key: "project", header: "Project", className: "needs-you__project", render: (item) => item.projectName },
    { key: "kind", header: "Kind", className: "needs-you__kind", render: (item) => kindLabel(item) },
    {
      key: "key",
      header: "Task",
      className: "needs-you__key",
      render: (item) => (item.taskKey ? <Mono>{item.taskKey}</Mono> : null),
    },
    {
      key: "title",
      header: "Title",
      className: "needs-you__title",
      render: (item) => (
        <Link className="row-link" href={itemHref(item)}>
          {item.title}
        </Link>
      ),
    },
    { key: "checked", header: "What was checked", className: "needs-you__checked", render: (item) => <Checked item={item} /> },
    {
      key: "action",
      header: "Action",
      className: "needs-you__action",
      render: (item) =>
        item.kind === NEEDS_YOU_KINDS.approval ? (
          <Button
            variant="gold-outline"
            inRow
            disabled={approvingId !== null}
            aria-label={`Approve ${item.taskKey || item.title}`}
            onClick={() => onApprove(item)}
          >
            {approvingId === item.id ? "Approving…" : "Approve"}
          </Button>
        ) : null,
    },
  ];

  return (
    <Surface as="section" className="needs-you" aria-labelledby="needs-you-title">
      <SectionHeading id="needs-you-title" title="Needs you" count={total} note="across all projects" />
      {notice ? (
        <p className={notice.error ? "notice notice--error" : "notice"} role={notice.error ? "alert" : "status"}>
          {notice.text}
        </p>
      ) : null}
      {placeholder ? (
        <Table caption="Needs you" columns={columns} tinted hideHeader placeholderRows={3} />
      ) : null}
      {items && items.length === 0 ? (
        <p className="empty">Nothing needs you. When a task waits for a decision in any project, it appears here.</p>
      ) : null}
      {items && items.length > 0 ? (
        <>
          <Table caption="Needs you" columns={columns} rows={visible} tinted hideHeader />
          {total > NEEDS_YOU_CAP ? (
            <Button variant="quiet" className="needs-you__more" onClick={() => setExpanded((open) => !open)}>
              {expanded ? "Show fewer" : `Show all ${total}`}
            </Button>
          ) : null}
        </>
      ) : null}
    </Surface>
  );
}
