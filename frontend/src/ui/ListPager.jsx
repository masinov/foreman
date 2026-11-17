import React, { useRef } from "react";

import { Button } from "./Button";
import { Caret } from "./Caret";

/**
 * Under a list that is shown a page at a time: the control that shows more
 * of it (`more` is its words) and, once more than the first page is shown,
 * the one that goes back to the first page. Both are there in the middle of
 * the list; at its end only the way back is. `children` are further
 * controls of the same kind, placed between the two.
 *
 * Going back makes the list above shorter, so the pager is brought back
 * into the window if that left it above it.
 */
export function ListPager({ more, fewer = "Show fewer", loading = false, hasMore, expanded, onMore, onFewer, children }) {
  const root = useRef(null);
  if (!hasMore && !expanded) return null;

  function goBack() {
    onFewer();
    window.requestAnimationFrame?.(() => root.current?.scrollIntoView?.({ block: "nearest" }));
  }

  return (
    <div className="list-pager" ref={root}>
      {hasMore ? (
        <Button variant="quiet" className="expander" disabled={loading} onClick={onMore}>
          <Caret />
          {more}
        </Button>
      ) : null}
      {hasMore ? children : null}
      {expanded ? (
        <Button variant="quiet" className="expander" disabled={loading} onClick={goBack}>
          <Caret direction="up" />
          {fewer}
        </Button>
      ) : null}
    </div>
  );
}
