import { queryString, segment } from "./client";

/** The milestone kinds the API reports: what happened to a project's sprints and its engine. */
export const MILESTONE_KINDS = {
  sprintStarted: "sprint_started",
  sprintFinished: "sprint_finished",
  planConfirmed: "plan_confirmed",
  engineStopped: "engine_stopped",
  engineLost: "engine_lost",
  enginePaused: "engine_paused",
  engineResumed: "engine_resumed",
};

const K = MILESTONE_KINDS;

/** The Activity tab's filters: which kinds each asks the server for. */
export const MILESTONE_FILTERS = [
  { key: "all", label: "All", kinds: [] },
  { key: "sprints", label: "Sprints", kinds: [K.sprintStarted, K.sprintFinished, K.planConfirmed] },
  { key: "engine", label: "Engine", kinds: [K.engineStopped, K.engineLost, K.enginePaused, K.engineResumed] },
];

/** One page of milestones, newest first, as `{ items, total }`. */
export function listMilestones(client, { projectId = null, kinds = [], limit, offset, ...options } = {}) {
  const base = projectId ? `/projects/${segment(projectId)}/milestones` : "/milestones";
  return client
    .get(`${base}${queryString({ kind: kinds, limit, offset })}`, options)
    .then((payload) => ({ items: payload?.milestones ?? [], total: payload?.total ?? 0 }));
}
