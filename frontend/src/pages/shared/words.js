// Words shared by the pages that show sprints. Plain words, no engine
// jargon (design README, Words). A sprint's work has its own words
// (workWords.js).

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
