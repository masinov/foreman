import { ENGINE_STATES } from "../../api/workspace";

// Words shared by the pages that show engines and sprints. Plain words, no
// engine jargon (design README, Words).

export const ENGINE_WORDS = {
  [ENGINE_STATES.running]: { tone: "running", word: "Running" },
  [ENGINE_STATES.paused]: { tone: "idle", word: "Paused" },
  [ENGINE_STATES.notRunning]: { tone: "idle", word: "Not running" },
};

export function engineWords(state) {
  return ENGINE_WORDS[state] ?? ENGINE_WORDS[ENGINE_STATES.notRunning];
}

// The order a person reads a sprint in: what waits for them, what is
// moving, what is waiting to start, what is finished. Every blocked or filed
// task waits for a person (to approve, to unblock, to accept), so those two
// counts are "need you".
const COUNT_WORDS = [
  ["in_progress", "in progress"],
  ["todo", "to do"],
  ["done", "done"],
];

export function describeTaskCounts(counts) {
  const needYou = (counts?.blocked || 0) + (counts?.triage || 0);
  const parts = needYou > 0 ? [`${needYou} need you`] : [];
  for (const [status, word] of COUNT_WORDS) {
    if ((counts?.[status] || 0) > 0) parts.push(`${counts[status]} ${word}`);
  }
  return parts.length ? parts.join(" · ") : "no tasks";
}
