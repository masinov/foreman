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

/** One line of the story: when, what happened in words, and what it ran, said or printed. */
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
        {/* What someone wrote (an agent, a user) is shown whole: it is what
            the run is about. Code and what a program printed (a command the
            agent ran, a tool's result, test output, an error) show their
            first lines, with Show all. */}
        {line.mono ? (
          <LongText brief className="run-line__head">
            {line.says ? <span className={`run-line__says${tone}`}>{line.says}</span> : null}
            {line.says ? " " : null}
            <Mono className="run-line__mono">{line.mono}</Mono>
          </LongText>
        ) : line.says ? (
          <p className="run-line__head">
            <span className={`run-line__says${tone}`}>{line.says}</span>
          </p>
        ) : null}
        {line.body ? (
          line.prose ? <p className="run-line__words">{line.body}</p> : <LongText output>{line.body}</LongText>
        ) : null}
      </div>
    </li>
  );
}
