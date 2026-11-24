import React from "react";

import { Caret } from "./Caret";

/**
 * A section heading: the title, an optional count beside it (gold only when
 * `attention` says it counts things that wait for a person), an optional
 * quiet note, and optional actions at the right. It sits on a rule that spans
 * the section, so the title reads as the head of what is under it; `plain`
 * drops the rule for a heading above a tinted surface, which is its own
 * container.
 *
 * A heading that folds what is under it gets `expanded` and `onToggle`: the
 * title, count and note become one button with a caret, carrying
 * aria-expanded (and aria-controls when `controls` names the folded part).
 * The caller shows or hides the section; the heading looks the same either
 * way, so a folded heading and an open one are told apart by the caret only.
 */
export function SectionHeading({
  title,
  count,
  attention = false,
  note,
  actions,
  level = 2,
  id,
  plain = false,
  expanded,
  onToggle,
  controls,
}) {
  const Heading = `h${level}`;
  const foldable = typeof onToggle === "function";
  const countNode =
    count !== undefined && count !== null ? (
      <>
        <span className="visually-hidden"> </span>
        <span className={attention && count > 0 ? "section-heading__count section-heading__count--attention" : "section-heading__count"}>
          {count}
        </span>
      </>
    ) : null;
  const noteNode = note ? <span className="section-heading__note">{note}</span> : null;
  return (
    <div className={plain ? "section-heading section-heading--plain" : "section-heading"}>
      {foldable ? (
        <Heading className="section-heading__title section-heading__title--fold" id={id}>
          <button
            type="button"
            className="section-heading__fold"
            aria-expanded={Boolean(expanded)}
            aria-controls={controls}
            onClick={() => onToggle(!expanded)}
          >
            <Caret direction={expanded ? "down" : "right"} />
            {title}
            {countNode}
            {note ? (
              <>
                <span className="visually-hidden"> </span>
                {noteNode}
              </>
            ) : null}
          </button>
        </Heading>
      ) : (
        <>
          <Heading className="section-heading__title" id={id}>
            {title}
            {countNode}
          </Heading>
          {noteNode}
        </>
      )}
      {actions ? <div className="section-heading__actions">{actions}</div> : null}
    </div>
  );
}
