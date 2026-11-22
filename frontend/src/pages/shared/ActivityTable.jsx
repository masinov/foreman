import React from "react";

import { Link } from "../../app/router";
import { Mono } from "../../ui/Mono";
import { Table } from "../../ui/Table";
import { formatDayTime } from "../../ui/format";

import "../../styles/activity.css";

/**
 * Every activity list on the dashboard, one shape (owner, 2026-11-21):
 *
 *   When · (Project) · (Key) · Subject · What happened · By · (numbers)
 *
 * One line per row, the same column widths on every page. The subject is
 * what the level lists (a sprint or the engine on a project, a task on a
 * sprint, a step on a task). Where the level has keys (a task's, a sprint's
 * name) they have their own column, as in the task list, and the subject is
 * the title, cut with "…" at the column's width, all of it on hover. What happened is a short phrase in its
 * colour; why (a reviewer's reason, a failure, a person's reason) is on hover
 * and on the page the row leads to, never under the row. At phone width the
 * project, who and the numbers give way; what happened stays.
 *
 * `describe(item)` returns `{ at, project, subject: { key, title, note }, event:
 * { word, tone, why }, by, byTitle, commit, took, spend, href }`; By names
 * a role, and `byTitle` (the model) is on hover. `keyHeader`, when
 * given, puts the key in a column of its own (a task's key, as narrow as
 * the task list's; `wideKey` for a sprint's name); `subjectHeader` names
 * the subject column. `numbers` lists which of commit, took and spend
 * this level shows. A row leads to `href`, or `onRowClick` picks it, with
 * `selected` marking the picked one.
 */
export function ActivityTable({
  caption,
  items,
  describe,
  subjectHeader,
  keyHeader = null,
  wideKey = false,
  showProject = false,
  numbers = [],
  rowKey,
  onRowClick = null,
  selected = null,
  arrived = null,
  placeholderRows = null,
}) {
  const rows = (items ?? []).map((item) => ({ item, row: describe(item) }));
  const columns = [
    {
      key: "when",
      header: "When",
      className: "activity-table__when",
      render: ({ row }) => <Mono quiet>{formatDayTime(row.at)}</Mono>,
    },
    showProject
      ? { key: "project", header: "Project", className: "activity-table__project", render: ({ row }) => row.project }
      : null,
    keyHeader
      ? {
          key: "key",
          header: keyHeader,
          className: wideKey ? "activity-table__key activity-table__key--wide" : "activity-table__key",
          render: ({ row }) => <Mono quiet>{row.subject.key || ""}</Mono>,
        }
      : null,
    {
      key: "subject",
      header: subjectHeader,
      className: keyHeader ? "activity-table__subject activity-table__subject--titled" : "activity-table__subject",
      render: ({ item, row }) => (
        <Subject
          row={row}
          withKey={!keyHeader}
          pick={onRowClick ? () => onRowClick(item) : null}
          pressed={selected ? selected(item) : false}
        />
      ),
    },
    {
      key: "event",
      header: "What happened",
      className: "activity-table__event",
      render: ({ row }) => (
        <span className={`tone-${row.event.tone ?? "idle"}`} title={row.event.why || undefined}>
          {row.event.word}
        </span>
      ),
    },
    {
      key: "by",
      header: "By",
      className: "activity-table__by",
      render: ({ row }) => (row.byTitle ? <span title={row.byTitle}>{row.by}</span> : row.by || ""),
    },
    numbers.includes("commit")
      ? { key: "commit", header: "Commit", className: "activity-table__commit", render: ({ row }) => (row.commit ? <Mono quiet>{row.commit}</Mono> : "") }
      : null,
    numbers.includes("took")
      ? { key: "took", header: "Took", numeric: true, className: "activity-table__took", render: ({ row }) => <Mono quiet>{row.took || ""}</Mono> }
      : null,
    numbers.includes("spend")
      ? { key: "spend", header: "Spend", numeric: true, className: "activity-table__spend", render: ({ row }) => <Mono quiet>{row.spend || ""}</Mono> }
      : null,
  ].filter(Boolean);
  return (
    <Table
      caption={caption}
      columns={columns}
      rows={rows}
      rowKey={({ item }) => rowKey(item)}
      rowHref={onRowClick ? null : ({ row }) => row.href ?? null}
      onRowClick={onRowClick ? ({ item }) => onRowClick(item) : null}
      selected={selected ? ({ item }) => selected(item) : null}
      arrived={arrived ? ({ item }) => arrived(item) : null}
      placeholderRows={placeholderRows}
      className="activity-table"
    />
  );
}

/**
 * The subject in one line: its key, then its title, all of it on hover. In a
 * list whose rows pick (a task's runs), it is the row's button.
 */
function Subject({ row, withKey, pick, pressed }) {
  const { title, note } = row.subject;
  const key = withKey ? row.subject.key : null;
  const full = [row.subject.key, title, note].filter(Boolean).join(" · ");
  // A note (a step's attempt) follows the title, quieter.
  const text = (
    <>
      {key ? <Mono quiet>{key}</Mono> : null}
      {key && title ? " · " : null}
      {title || null}
      {note ? <span className="activity-table__note">{note}</span> : null}
    </>
  );
  if (pick) {
    return (
      <button type="button" className="file-pick activity-table__subject-text" aria-pressed={pressed} title={full} onClick={pick}>
        {text}
      </button>
    );
  }
  return row.href ? (
    <Link className="row-link activity-table__subject-text" href={row.href} title={full}>
      {text}
    </Link>
  ) : (
    <span className="activity-table__subject-text" title={full}>
      {text}
    </span>
  );
}
