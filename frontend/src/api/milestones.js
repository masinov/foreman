import { queryString, segment } from "./client";

/** The milestone kinds the API reports. */
export const MILESTONE_KINDS = {
  sprintStarted: "sprint_started",
  sprintFinished: "sprint_finished",
  taskMerged: "task_merged",
  engineStarted: "engine_started",
  enginePaused: "engine_paused",
  engineResumed: "engine_resumed",
  engineStopped: "engine_stopped",
};

/** The Activity tab's filters: which kinds each asks the server for. */
export const MILESTONE_FILTERS = [
  { key: "all", label: "All", kinds: [] },
  { key: "sprints", label: "Sprints", kinds: [MILESTONE_KINDS.sprintStarted, MILESTONE_KINDS.sprintFinished] },
  { key: "merges", label: "Merges", kinds: [MILESTONE_KINDS.taskMerged] },
  {
    key: "engine",
    label: "Engine",
    kinds: [
      MILESTONE_KINDS.engineStarted,
      MILESTONE_KINDS.enginePaused,
      MILESTONE_KINDS.engineResumed,
      MILESTONE_KINDS.engineStopped,
    ],
  },
];

/** One page of milestones, newest first, as `{ items, total }`. */
export function listMilestones(client, { projectId = null, kinds = [], limit, offset, ...options } = {}) {
  const base = projectId ? `/projects/${segment(projectId)}/milestones` : "/milestones";
  return client
    .get(`${base}${queryString({ kind: kinds, limit, offset })}`, options)
    .then((payload) => ({ items: payload?.milestones ?? [], total: payload?.total ?? 0 }));
}
