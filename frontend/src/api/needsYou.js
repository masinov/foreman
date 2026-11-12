import { queryString, segment } from "./client";

/**
 * What waits for a person: one list of four kinds (design README, "Needs
 * you"), newest first, across projects or for one.
 */
export const NEEDS_YOU_KINDS = {
  acceptFiledWork: "accept_filed_work",
  approvePlan: "approve_plan",
  approveMerge: "approve_merge",
  unblock: "unblock",
};

/** One page as `{ items, total }`. Without `projectId`, every project. */
export function listNeedsYou(client, { projectId = null, limit, offset, ...options } = {}) {
  const base = projectId ? `/projects/${segment(projectId)}/needs-you` : "/needs-you";
  return client
    .get(`${base}${queryString({ limit, offset })}`, options)
    .then((payload) => ({ items: payload?.items ?? [], total: payload?.total ?? 0 }));
}
