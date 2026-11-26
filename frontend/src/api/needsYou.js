import { queryString, segment } from "./client";

/**
 * What waits for a person: one list of four kinds (design README, "Needs
 * you"), newest first, across projects or for one.
 */
export const NEEDS_YOU_KINDS = {
  acceptFiledWork: "accept_filed_work",
  // Not a task: the requests waiting in a project's backlog, counted (`count`).
  answerRequests: "answer_requests",
  approvePlan: "approve_plan",
  approveMerge: "approve_merge",
  unblock: "unblock",
  // Not a task: a proposed sprint order, settled by accepting or rejecting it.
  settleOrder: "settle_order",
  // Not a task: an active sprint whose every task is finished, where a user
  // finishes sprints (`task_counts`).
  finishSprint: "finish_sprint",
  // Not a task: a sprint a user blocked (ADR-0043), with why (`blocked`).
  unblockSprint: "unblock_sprint",
};

/** One page as `{ items, total }`. Without `projectId`, every project. */
export function listNeedsYou(client, { projectId = null, limit, offset, ...options } = {}) {
  const base = projectId ? `/projects/${segment(projectId)}/needs-you` : "/needs-you";
  return client
    .get(`${base}${queryString({ limit, offset })}`, options)
    .then((payload) => ({ items: payload?.items ?? [], total: payload?.total ?? 0 }));
}
