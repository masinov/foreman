import React from "react";

/**
 * A section heading: the title, an optional count beside it, an optional
 * quiet note, and optional actions at the right.
 */
export function SectionHeading({ title, count, note, actions, level = 2, id }) {
  const Heading = `h${level}`;
  return (
    <div className="section-heading">
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
