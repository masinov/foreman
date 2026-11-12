import { segment } from "./client";

// The manager: one conversation per project. History is read from the API;
// a message streams its reply as lines of `{type, ...}`:
//   text_delta {text}   a piece of the reply, in order
//   tool_use   {name}   the manager ran something
//   proposal   {proposal_id}   the manager proposed a change (ADR-0022)
//   done       {session_id}
//   error      {message}   the turn stopped; what arrived is kept

export const HISTORY_PAGE = 30;

/** A page of the conversation, oldest first: `{ turns, has_more }`. `before` is a turn id. */
export function getManagerHistory(client, projectId, { before, limit = HISTORY_PAGE } = {}, options) {
  const search = new URLSearchParams({ limit: String(limit) });
  if (before) search.set("before", before);
  return client.get(`/projects/${segment(projectId)}/meta/history?${search}`, options);
}

/**
 * Send a message with where the person is (`context`: `page`, and `sprint_id`
 * or `task_id` when on one). Returns an async generator of the reply's lines.
 */
export function sendManagerMessage(client, projectId, message, context, options) {
  return client.postLines(`/projects/${segment(projectId)}/meta/message`, { message, context }, options);
}

/** Forget the project's conversation: the next message starts a new one. */
export function clearManagerSession(client, projectId, options) {
  return client.delete(`/projects/${segment(projectId)}/meta/session`, options);
}
