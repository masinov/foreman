import React from "react";

import "../../styles/activity.css";

/**
 * A run's result in a table cell: the word in its tone and, under it, why
 * (a reviewer's reason for sending it back, a failure's message), at most two
 * lines with the whole of it on hover.
 */
export function ResultCell({ result }) {
  return (
    <div className="activity-result">
      <span className={`tone-${result.tone}`}>{result.word}</span>
      {result.note ? (
        <span className="activity-result__note" title={result.note}>
          {result.note}
        </span>
      ) : null}
    </div>
  );
}
