import React from "react";

import { LongText } from "../../ui/LongText";
import { Mono } from "../../ui/Mono";
import { formatClock, formatDay } from "../../ui/format";

/** The story with a line naming the day wherever it changes from the day the run started. */
export function withDays(lines, startedAt) {
  const out = [];
  let day = formatDay(startedAt);
  for (const line of lines) {
    const lineDay = formatDay(line.at);
    if (lineDay && day && lineDay !== day) out.push({ day: lineDay });
    if (lineDay) day = lineDay;
    out.push(line);
  }
  return out;
}

/** One line of the story: when, what happened in words, and what it ran or said. */
export function RunLine({ line }) {
  const tone = line.tone ? ` tone-${line.tone}` : "";
  if (line.day) {
    // A run can be touched again on a later day; the times alone would not say so.
    return <li className="run-line run-line--day">{line.day}</li>;
  }
  return (
    <li className="run-line">
      <Mono quiet className="run-line__at">
        {formatClock(line.at)}
      </Mono>
      <div className="run-line__what">
        {line.says || line.mono ? (
          <p className="run-line__head">
            {line.says ? <span className={`run-line__says${tone}`}>{line.says}</span> : null}
            {line.says && line.mono ? " " : null}
            {line.mono ? <Mono className="run-line__mono">{line.mono}</Mono> : null}
          </p>
        ) : null}
        {line.body ? (
          line.output ? (
            <pre className="run-output__text run-line__output">{line.body}</pre>
          ) : line.prose ? (
            <LongText>{line.body}</LongText>
          ) : (
            <pre className={line.clamp ? "run-output__text run-line__result" : "run-output__text"}>{line.body}</pre>
          )
        ) : null}
      </div>
    </li>
  );
}
