import { queryString, segment } from "./client";

// Proposals: changes the manager proposes; nothing happens until a person
// confirms (ADR-0022). A proposal is
//   { id, project_id, state, proposed_by, reason, operations, leaves, names,
//     created_at, decided_by, decided_at, outcome }
// with `state` one of proposed, confirmed, declined, failed, and `outcome`
// (once decided) carrying a `sentence` that says what happened.

export function getProposal(client, proposalId, options) {
  return client.get(`/proposals/${segment(proposalId)}`, options);
}

/** A page of a project's proposals, newest first: `{ proposals, total }`. */
export function listProposals(client, projectId, { state, limit, offset } = {}, options) {
  return client.get(`/projects/${segment(projectId)}/proposals${queryString({ state, limit, offset })}`, options);
}

/** Apply it as the person confirming. Answers the proposal, `confirmed` or `failed`. */
export function confirmProposal(client, proposalId, options) {
  return client.post(`/proposals/${segment(proposalId)}/confirm`, {}, options);
}

/** Decline it; nothing changes. Answers the proposal, `declined`. */
export function declineProposal(client, proposalId, options) {
  return client.post(`/proposals/${segment(proposalId)}/decline`, {}, options);
}
