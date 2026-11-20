import { queryString, segment } from "./client";

/** The milestone kinds the API reports. */
export const MILESTONE_KINDS = {
  sprintStarted: "sprint_started",
  sprintFinished: "sprint_finished",
  planConfirmed: "plan_confirmed",
  taskMerged: "task_merged",
  taskBlocked: "task_blocked",
  taskUnblocked: "task_unblocked",
  taskClosed: "task_closed",
  taskCancelled: "task_cancelled",
  decisionMade: "decision_made",
  engineRun: "engine_run",
  engineLost: "engine_lost",
  enginePaused: "engine_paused",
  engineResumed: "engine_resumed",
};

const K = MILESTONE_KINDS;

/**
 * The Activity tab's filters: which kinds each asks the server for. A
 * person's decisions, unblocking, closing and cancelling are under All.
 */
export const MILESTONE_FILTERS = [
  { key: "all", label: "All", kinds: [] },
  { key: "sprints", label: "Sprints", kinds: [K.sprintStarted, K.sprintFinished, K.planConfirmed] },
  { key: "merges", label: "Merges", kinds: [K.taskMerged] },
  { key: "problems", label: "Problems", kinds: [K.taskBlocked, K.engineLost] },
  { key: "engine", label: "Engine", kinds: [K.engineRun, K.engineLost, K.enginePaused, K.engineResumed] },
];

/** One page of milestones, newest first, as `{ items, total }`. */
export function listMilestones(client, { projectId = null, kinds = [], limit, offset, ...options } = {}) {
  const base = projectId ? `/projects/${segment(projectId)}/milestones` : "/milestones";
  return client
    .get(`${base}${queryString({ kind: kinds, limit, offset })}`, options)
    .then((payload) => ({ items: payload?.milestones ?? [], total: payload?.total ?? 0 }));
}
