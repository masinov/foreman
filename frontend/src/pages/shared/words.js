import { ENGINE_STATES } from "../../api/workspace";

// Words shared by the pages that show engines and sprints. Plain words, no
// engine jargon (design README, Words).

// "Running" only while the engine has a task in hand: an engine that is up
// with nothing to do is "Waiting", and its dot stays still (owner,
// 2026-11-25: "Running gives the impression that the engine is actually
// working").
export const ENGINE_WORDS = {
  [ENGINE_STATES.running]: { tone: "running", word: "Running" },
  waiting: { tone: "idle", word: "Waiting" },
  [ENGINE_STATES.paused]: { tone: "idle", word: "Paused" },
  [ENGINE_STATES.notRunning]: { tone: "idle", word: "Not running" },
};

/** The word and tone for a project's engine (`{ state, task_id }`, or null). */
export function engineWords(engine) {
  const state = engine?.state;
  if (state === ENGINE_STATES.running && !engine.task_id) return ENGINE_WORDS.waiting;
  return ENGINE_WORDS[state] ?? ENGINE_WORDS[ENGINE_STATES.notRunning];
}

/**
 * Whether the project gives its engine anything to do: a task in hand, or an
 * active sprint that has tasks. Without it, Pause and Stop have nothing to
 * act on and are not offered.
 */
export function engineHasWork(engine, project) {
  if (engine?.task_id) return true;
  return Boolean(project?.active_sprint) && !activeSprintIsEmpty(project);
}

/** The project's active sprint exists and has no task at all. */
export function activeSprintIsEmpty(project) {
  const counts = project?.active_sprint?.task_counts;
  if (!counts) return false;
  return Object.values(counts).reduce((sum, value) => sum + (Number(value) || 0), 0) === 0;
}

// The order a person reads a sprint in: what waits for them, what is
// moving, what is waiting to start, what is finished. Every blocked or filed
// task waits for a person (to approve, to unblock, to accept), so those two
// counts are "need you".
const COUNT_WORDS = [
  ["in_progress", "in progress"],
  ["todo", "to do"],
  ["done", "done"],
  // Cancelled tasks are still rows in the sprint's list, so the counts say
  // so: the parts add up to the number of rows.
  ["cancelled", "cancelled"],
];

export function describeTaskCounts(counts) {
  const needYou = (counts?.blocked || 0) + (counts?.triage || 0);
  const parts = needYou > 0 ? [`${needYou} need you`] : [];
  for (const [status, word] of COUNT_WORDS) {
    if ((counts?.[status] || 0) > 0) parts.push(`${counts[status]} ${word}`);
  }
  return parts.length ? parts.join(" · ") : "no tasks";
}
