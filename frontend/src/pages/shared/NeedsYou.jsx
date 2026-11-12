import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { listNeedsYou, NEEDS_YOU_KINDS } from "../../api/needsYou";
import { approveTask } from "../../api/tasks";
import { useDelayedFlag } from "../../api/useResource";
import { usePagedList } from "../../api/usePagedList";
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
// The most the API returns in one page.
const MAX_PAGE = 200;

const KIND_WORDS = {
  [NEEDS_YOU_KINDS.acceptFiledWork]: "Accept filed work",
  [NEEDS_YOU_KINDS.approvePlan]: "Approve plan",
  [NEEDS_YOU_KINDS.approveMerge]: "Approve merge",
  [NEEDS_YOU_KINDS.unblock]: "Unblock",
};

const TESTS_WORDS = {
  passed: "tests passed",
  failed: "tests failed",
  stale: "tests stale",
  not_run: "tests not run",
};

/** The facts a person weighs at the merge gate (ADR-0018), as words. */
function MergeFacts({ evidence }) {
  if (!evidence) return <span className="quiet">Nothing checked yet</span>;
  const words = [];
  if (TESTS_WORDS[evidence.tests_status]) words.push(TESTS_WORDS[evidence.tests_status]);
  if (evidence.review_outcome) words.push(`review ${humanize(evidence.review_outcome).toLowerCase()}`);
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

function Detail({ item }) {
  if (item.kind === NEEDS_YOU_KINDS.approveMerge) return <MergeFacts evidence={item.evidence} />;
  return <span className="quiet">{item.sprint_title || ""}</span>;
}

/**
 * Needs you: the one tinted surface. Without `projectId` it spans every
 * project and names each item's project. An approve-merge item has an
 * outlined Approve; every other kind links to its task.
 *
 * `onChanged` runs after an approval, for whatever else on the page counts
 * what waits.
 */
export function NeedsYou({ projectId = null, note, empty, onChanged }) {
  const client = useApiClient();
  const list = usePagedList(
    ["needs-you", projectId],
    (apiClient, options) => listNeedsYou(apiClient, { projectId, ...options }),
    { pageSize: NEEDS_YOU_CAP },
  );
  const placeholder = useDelayedFlag(list.loading && !list.items);
  const [expanded, setExpanded] = useState(false);
  const [approvingId, setApprovingId] = useState(null);
  const [notice, setNotice] = useState(null);

  async function approve(item) {
    setApprovingId(item.task_id);
    setNotice(null);
    try {
      const result = await approveTask(client, item.task_id);
      setNotice({ error: false, text: result?.message || `Approved ${item.task_key || item.task_title}.` });
      setExpanded(false);
      list.reload();
      onChanged?.();
    } catch (error) {
      setNotice({ error: true, text: errorSentence(error) });
    } finally {
      setApprovingId(null);
    }
  }

  function showAll() {
    const missing = (list.total ?? 0) - (list.items?.length ?? 0);
    if (missing > 0) list.loadMore(Math.min(missing, MAX_PAGE));
    setExpanded(true);
  }

  const items = list.items;
  const total = list.total;
  const visible = items ? (expanded ? items : items.slice(0, NEEDS_YOU_CAP)) : [];

  const columns = [
    projectId
      ? null
      : { key: "project", header: "Project", className: "needs-you__project", render: (item) => item.project_name },
    { key: "kind", header: "Kind", className: "needs-you__kind", render: (item) => KIND_WORDS[item.kind] ?? humanize(item.kind) },
    {
      key: "key",
      header: "Task",
      className: "needs-you__key",
      render: (item) => (item.task_key ? <Mono>{item.task_key}</Mono> : null),
    },
    {
      key: "title",
      header: "Title",
      className: "needs-you__title",
      render: (item) => (
        <Link className="row-link" href={paths.task(item.task_id)}>
          {item.task_title}
        </Link>
      ),
    },
    { key: "detail", header: "What was checked", className: "needs-you__checked", render: (item) => <Detail item={item} /> },
    {
      key: "action",
      header: "Action",
      className: "needs-you__action",
      render: (item) =>
        item.kind === NEEDS_YOU_KINDS.approveMerge ? (
          <Button
            variant="gold-outline"
            inRow
            disabled={approvingId !== null}
            aria-label={`Approve ${item.task_key || item.task_title}`}
            onClick={() => approve(item)}
          >
            {approvingId === item.task_id ? "Approving…" : "Approve"}
          </Button>
        ) : null,
    },
  ].filter(Boolean);

  const headingId = projectId ? `needs-you-${projectId}` : "needs-you-title";
  return (
    <Surface as="section" className="needs-you" aria-labelledby={headingId}>
      <SectionHeading id={headingId} title="Needs you" count={total} note={note} />
      {notice ? (
        <p className={notice.error ? "notice notice--error" : "notice"} role={notice.error ? "alert" : "status"}>
          {notice.text}
        </p>
      ) : null}
      {list.error ? (
        <p className="notice notice--error" role="alert">
          {list.error}
        </p>
      ) : null}
      {placeholder ? <Table caption="Needs you" columns={columns} tinted hideHeader placeholderRows={3} /> : null}
      {items && items.length === 0 ? <p className="empty">{empty}</p> : null}
      {items && items.length > 0 ? (
        <>
          <Table caption="Needs you" columns={columns} rows={visible} rowKey={(item) => item.task_id} tinted hideHeader />
          {total > NEEDS_YOU_CAP ? (
            <Button
              variant="quiet"
              className="needs-you__more"
              disabled={list.loadingMore}
              onClick={() => (expanded ? setExpanded(false) : showAll())}
            >
              {expanded ? "Show fewer" : `Show all ${total}`}
            </Button>
          ) : null}
        </>
      ) : null}
    </Surface>
  );
}
