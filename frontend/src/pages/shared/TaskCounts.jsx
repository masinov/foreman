import React from "react";

import { describeTaskCounts } from "./words";

/**
 * A sprint's task counts in words. The part that waits for a person is gold,
 * wherever the counts appear.
 */
export function TaskCounts({ counts }) {
  const needYou = (counts?.blocked || 0) + (counts?.triage || 0);
  const words = describeTaskCounts(counts);
  if (needYou === 0) return words;
  const [first, ...rest] = words.split(" · ");
  return (
    <>
      <span className="attention">{first}</span>
      {rest.length ? ` · ${rest.join(" · ")}` : ""}
    </>
  );
}
