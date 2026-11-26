import { queryString, segment } from "./client";

/**
 * The milestone kinds the API reports: what happened to a project's sprints,
 * the holds a user put on its work (ADR-0043), and its worker (the engine).
 */
export const MILESTONE_KINDS = {
  sprintStarted: "sprint_started",
  sprintFinished: "sprint_finished",
  planConfirmed: "plan_confirmed",
  engineStarted: "engine_started",
  engineStopped: "engine_stopped",
  engineLost: "engine_lost",
  enginePaused: "engine_paused",
  engineResumed: "engine_resumed",
  workPaused: "work_paused",
  workStopped: "work_stopped",
  workResumed: "work_resumed",
  workBlocked: "work_blocked",
  workUnblocked: "work_unblocked",
};

const K = MILESTONE_KINDS;

/** The Activity tab's filters: which kinds each asks the server for. */
export const MILESTONE_FILTERS = [
  { key: "all", label: "All", kinds: [] },
  { key: "sprints", label: "Sprints", kinds: [K.sprintStarted, K.sprintFinished, K.planConfirmed] },
  { key: "holds", label: "Pauses and blocks", kinds: [K.workPaused, K.workStopped, K.workResumed, K.workBlocked, K.workUnblocked] },
  { key: "worker", label: "Worker", kinds: [K.engineStarted, K.engineStopped, K.enginePaused, K.engineResumed, K.engineLost] },
];

/** One page of milestones, newest first, as `{ items, total }`. */
export function listMilestones(client, { projectId = null, kinds = [], limit, offset, ...options } = {}) {
  const base = projectId ? `/projects/${segment(projectId)}/milestones` : "/milestones";
  return client
    .get(`${base}${queryString({ kind: kinds, limit, offset })}`, options)
    .then((payload) => ({ items: payload?.milestones ?? [], total: payload?.total ?? 0 }));
}
