import React from "react";

/**
 * A section heading: the title, an optional count beside it, an optional
 * quiet note, and optional actions at the right. It sits on a rule that spans
 * the section, so the title reads as the head of what is under it; `plain`
 * drops the rule for a heading above a tinted surface, which is its own
 * container.
 */
export function SectionHeading({ title, count, note, actions, level = 2, id, plain = false }) {
  const Heading = `h${level}`;
  return (
    <div className={plain ? "section-heading section-heading--plain" : "section-heading"}>
      <Heading className="section-heading__title" id={id}>
        {title}
        {count !== undefined && count !== null ? (
          <>
            <span className="visually-hidden"> </span>
            <span className="section-heading__count">{count}</span>
          </>
        ) : null}
      </Heading>
      {note ? <span className="section-heading__note">{note}</span> : null}
      {actions ? <div className="section-heading__actions">{actions}</div> : null}
    </div>
  );
}
