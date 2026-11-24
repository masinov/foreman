import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { GATE_RESOLUTIONS, resolveGate } from "../../api/gates";
import { listNeedsYou, NEEDS_YOU_KINDS } from "../../api/needsYou";
import { SPRINT_STATUSES, transitionSprint } from "../../api/sprints";
import { approveTask, unblockTask } from "../../api/tasks";
import { useDelayedFlag } from "../../api/useResource";
import { usePagedList } from "../../api/usePagedList";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Caret } from "../../ui/Caret";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Surface } from "../../ui/Surface";
import { Table } from "../../ui/Table";
import { humanize, plural, shortSha } from "../../ui/format";
import { useNotice } from "../../ui/Toast";
import { decisionSentence } from "./decisionWords";
import { describeTaskCounts } from "./words";

// Design README: Needs you shows at most 5, with a way to see the rest.
export const NEEDS_YOU_CAP = 5;
// The most the API returns in one page.
const MAX_PAGE = 200;

const KIND_WORDS = {
  [NEEDS_YOU_KINDS.acceptFiledWork]: "Accept filed work",
  [NEEDS_YOU_KINDS.answerRequests]: "Answer requests",
  [NEEDS_YOU_KINDS.approvePlan]: "Approve plan",
  [NEEDS_YOU_KINDS.approveMerge]: "Approve merge",
  [NEEDS_YOU_KINDS.unblock]: "Blocked",
  [NEEDS_YOU_KINDS.settleOrder]: "Settle sprint order",
  [NEEDS_YOU_KINDS.finishSprint]: "Finish sprint",
};

const itemId = (item) =>
  item.gate?.id ?? item.task_id ?? (item.kind === NEEDS_YOU_KINDS.finishSprint ? `finish:${item.sprint_id}` : `${item.kind}:${item.project_id}`);
const itemName = (item) => item.task_key || item.task_title || "the sprint order";

// The same words and colours as a task's checks in the sprint list: a word
// alone in green passed; anything else says what is wrong.
const TESTS_PARTS = {
  passed: { tone: "passed", text: "tests" },
  failed: { tone: "failed", text: "tests failed" },
  stale: { tone: "attention", text: "tests stale" },
  not_run: { tone: "attention", text: "tests not run" },
};
const GOOD_REVIEWS = new Set(["approve", "approved", "pass", "passed"]);

/** The facts a person weighs at the merge gate (ADR-0018), as words. */
function MergeFacts({ evidence }) {
  if (!evidence) return <span className="quiet">Nothing checked yet</span>;
  const words = [];
  if (TESTS_PARTS[evidence.tests_status]) words.push({ key: "tests", ...TESTS_PARTS[evidence.tests_status] });
  if (evidence.review_outcome) {
    words.push(
      GOOD_REVIEWS.has(evidence.review_outcome)
        ? { key: "review", tone: "passed", text: "review" }
        : { key: "review", tone: "attention", text: `review ${humanize(evidence.review_outcome).toLowerCase()}` },
    );
  }
  const sha = shortSha(evidence.head_sha);
  return (
    <span className="checks">
      {words.map((word, index) => (
        <React.Fragment key={word.key}>
          {index > 0 ? " · " : ""}
          <span className={`checks__${word.tone}`}>{word.text}</span>
        </React.Fragment>
      ))}
      {sha ? (
        <>
          {words.length ? " · " : ""}
          <Mono quiet>{sha}</Mono>
        </>
      ) : null}
    </span>
  );
}

/** The order a manager proposes for the sprints, and why. */
function OrderProposal({ gate }) {
  const order = gate.suggested_order.map((entry) => entry.title || entry.sprint_id).join(" → ");
  return (
    <span className="quiet">
      {order ? `Proposed: ${order}` : "No order proposed"}
      {gate.suggested_reason ? ` · ${gate.suggested_reason}` : ""}
    </span>
  );
}

/** Why a task is blocked and the step it stopped at: what a person weighs before unblocking it. */
function BlockedFacts({ blocked }) {
  const reason = blocked?.reason || "No reason recorded";
  const step = blocked?.step ? ` · at ${humanize(blocked.step)}` : "";
  return (
    <span className="needs-you__blocked" title={`${reason}${step}`}>
      <span className="needs-you__reason">{reason}</span>
      {step ? <span className="quiet">{step}</span> : null}
    </span>
  );
}

function Detail({ item }) {
  if (item.gate) return <OrderProposal gate={item.gate} />;
  if (item.kind === NEEDS_YOU_KINDS.approveMerge) return <MergeFacts evidence={item.evidence} />;
  if (item.kind === NEEDS_YOU_KINDS.unblock) return <BlockedFacts blocked={item.blocked} />;
  if (item.kind === NEEDS_YOU_KINDS.answerRequests) return <span className="quiet">Backlog</span>;
  if (item.kind === NEEDS_YOU_KINDS.finishSprint) return <span className="quiet">{describeTaskCounts(item.task_counts ?? {})}</span>;
  return <span className="quiet">{item.sprint_title || ""}</span>;
}

/**
 * Needs you: the one tinted surface. Without `projectId` it spans every
 * project and names each item's project.
 *
 * A row carries the main button of its task's decision when the row can show
 * what that decision weighs (ADR-0030): a merge shows its tests, review and
 * commit and has Approve; a blocked task shows why it is blocked and where
 * it stopped and has Unblock; a proposed sprint order shows the order and
 * has Accept and Reject. A plan has to be read, and requests are several, so
 * those rows only link to where they are decided.
 *
 * `onChanged` runs after a decision, for whatever else on the page counts
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
  const [notice, setNotice] = useNotice();

  async function decide(item, settle) {
    setApprovingId(itemId(item));
    setNotice(null);
    try {
      const result = await settle();
      setNotice({ error: false, text: result.text });
      setExpanded(false);
      list.reload();
      onChanged?.();
    } catch (error) {
      setNotice({ error: true, text: errorSentence(error) });
    } finally {
      setApprovingId(null);
    }
  }

  const approve = (item) =>
    decide(item, async () => {
      const result = await approveTask(client, item.task_id);
      return { text: decisionSentence(itemName(item), result) };
    });

  const unblock = (item) =>
    decide(item, async () => {
      await unblockTask(client, item.task_id, null);
      return { text: `Unblocked ${itemName(item)}. It is back in the queue.` };
    });

  const settleOrder = (item, resolution) =>
    decide(item, async () => {
      await resolveGate(client, item.gate.id, resolution);
      return {
        text:
          resolution === GATE_RESOLUTIONS.accept
            ? "Sprint order accepted. The sprints now run in the proposed order."
            : "Sprint order rejected. The sprints keep their order.",
      };
    });

  // Finishing tags the repository as the sprint page's Finish sprint does
  // (ADR-0036); the sprint page says the tag.
  const finishSprint = (item) =>
    decide(item, async () => {
      await transitionSprint(client, item.sprint_id, SPRINT_STATUSES.completed);
      return { text: `Finished ${item.sprint_title || "the sprint"}.` };
    });

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
      render: (item) =>
        item.kind === NEEDS_YOU_KINDS.answerRequests ? (
          <Link className="row-link" href={paths.projectBacklog(item.project_id)}>
            {plural(item.count ?? 0, "request")} from agents and other systems
          </Link>
        ) : item.kind === NEEDS_YOU_KINDS.finishSprint ? (
          <Link className="row-link" href={paths.sprint(item.sprint_id)}>
            {item.sprint_title}
          </Link>
        ) : item.gate ? (
          <Link className="row-link" href={paths.sprint(item.sprint_id)}>
            {item.gate.conflict_description}
          </Link>
        ) : (
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
      render: (item) => {
        if (item.gate) {
          const busy = approvingId === item.gate.id;
          return (
            <span className="needs-you__decide">
              <Button
                variant="gold-outline"
                inRow
                disabled={approvingId !== null}
                aria-label="Accept the proposed sprint order"
                onClick={() => settleOrder(item, GATE_RESOLUTIONS.accept)}
              >
                {busy ? "Saving…" : "Accept"}
              </Button>
              <Button
                variant="quiet"
                inRow
                disabled={approvingId !== null}
                aria-label="Reject the proposed sprint order"
                onClick={() => settleOrder(item, GATE_RESOLUTIONS.reject)}
              >
                Reject
              </Button>
            </span>
          );
        }
        if (item.kind === NEEDS_YOU_KINDS.approveMerge) {
          return (
            <Button
              variant="gold-outline"
              inRow
              disabled={approvingId !== null}
              aria-label={`Approve ${itemName(item)}`}
              onClick={() => approve(item)}
            >
              {approvingId === item.task_id ? "Approving…" : "Approve"}
            </Button>
          );
        }
        if (item.kind === NEEDS_YOU_KINDS.finishSprint) {
          return (
            <Button
              variant="gold-outline"
              inRow
              disabled={approvingId !== null}
              aria-label={`Finish ${item.sprint_title || "the sprint"}`}
              onClick={() => finishSprint(item)}
            >
              {approvingId === itemId(item) ? "Finishing…" : "Finish"}
            </Button>
          );
        }
        if (item.kind === NEEDS_YOU_KINDS.unblock) {
          return (
            <Button
              variant="gold-outline"
              inRow
              disabled={approvingId !== null}
              aria-label={`Unblock ${itemName(item)}`}
              onClick={() => unblock(item)}
            >
              {approvingId === item.task_id ? "Unblocking…" : "Unblock"}
            </Button>
          );
        }
        return null;
      },
    },
  ].filter(Boolean);

  const headingId = projectId ? `needs-you-${projectId}` : "needs-you-title";
  return (
    <section className="needs-you" aria-labelledby={headingId}>
      <SectionHeading id={headingId} title="Needs you" count={total} attention note={note} plain />
      {notice ? (
        <p className="notice notice--error" role="alert">
          {notice.text}
        </p>
      ) : null}
      {list.error ? (
        <p className="notice notice--error" role="alert">
          {list.error}
        </p>
      ) : null}
      {/* The heading stays outside the tinted surface; the surface is always
          there, so the section looks the same whether or not something is
          waiting. Empty, it holds the sentence that says so. */}
      {placeholder ? (
        <Surface className="needs-you__surface">
          <Table caption="Needs you" columns={columns} tinted hideHeader placeholderRows={3} />
        </Surface>
      ) : null}
      {items && items.length === 0 ? (
        <Surface className="needs-you__surface needs-you__surface--empty">
          <p className="empty">{empty}</p>
        </Surface>
      ) : null}
      {items && items.length > 0 ? (
        <Surface className="needs-you__surface">
          <Table caption="Needs you" columns={columns} rows={visible} rowKey={itemId} tinted hideHeader />
          {total > NEEDS_YOU_CAP ? (
            <Button
              variant="quiet"
              className="needs-you__more expander"
              disabled={list.loadingMore}
              onClick={() => (expanded ? setExpanded(false) : showAll())}
            >
              <Caret direction={expanded ? "up" : "down"} />
              {expanded ? "Show fewer" : `Show all ${total}`}
            </Button>
          ) : null}
        </Surface>
      ) : null}
    </section>
  );
}
