import React, { useId, useState } from "react";

import { Caret } from "../../ui/Caret";
import { LongText } from "../../ui/LongText";
import { Markdown } from "../../ui/Markdown";
import { Mono } from "../../ui/Mono";
import { formatClock, formatDay } from "../../ui/format";
import { Spend, spendWords } from "../../ui/Spend";

/** How many lines of what a program printed show before Show all. */
export const PRINTED_LINES = 3;

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

/** The last lines of a text, where a program says how it ended; blank lines at the end do not count. */
export function lastLines(text, count = PRINTED_LINES) {
  const lines = String(text ?? "").replace(/\s+$/, "").split("\n");
  return { text: lines.slice(-count).join("\n"), more: lines.length > count };
}

/**
 * What a program printed: its last lines, where the result is, with Show all
 * when there is more. Quieter than what someone wrote.
 */
function Printed({ text }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const tail = lastLines(text);
  return (
    <div className="long-text">
      <pre id={id} className="long-text__text long-text__text--output">
        {open ? text : tail.text}
      </pre>
      {tail.more ? (
        <button
          type="button"
          className="long-text__toggle expander"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen(!open)}
        >
          <Caret direction={open ? "up" : "down"} />
          {open ? "Show less" : "Show all"}
        </button>
      ) : null}
    </div>
  );
}

/**
 * One line of the story: when, what happened, and under it what it ran (its
 * first lines), what someone wrote (whole, formatted) or what a program
 * printed (its last lines). Every kind of step tells its story in these.
 */
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
        {line.says ? (
          <p className="run-line__head">
            <span className={`run-line__says${tone}`}>{line.says}</span>
            {line.spend && spendWords(line.spend.amount, line.spend.tokens, "row") ? (
              <>
                {" · "}
                <Spend amount={line.spend.amount} tokens={line.spend.tokens} where="row" />
              </>
            ) : null}
          </p>
        ) : null}
        {line.mono ? (
          <LongText output className="run-line__command">
            {line.mono}
          </LongText>
        ) : null}
        {line.body ? (
          line.prose ? <Markdown text={line.body} className="run-line__words" /> : <Printed text={line.body} />
        ) : null}
      </div>
    </li>
  );
}
